# auth_routes.py (production-ready)

from fastapi import APIRouter, Body, HTTPException, Depends, UploadFile, File
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
from bson import ObjectId
from jose import jwt, JWTError
import os, time, requests

from auth_utils import hash_password, verify_password, create_access_token, decode_access_token
from db import get_user_by_email, create_user_in_db, get_user_by_id, update_user_last_seen, users_coll

# --- Router & auth scheme ---
router = APIRouter()
oauth2_scheme = HTTPBearer()

# --- Config from env ---
GOOGLE_ALLOWED_AUDS = {v for v in [
    os.getenv("GOOGLE_IOS_CLIENT_ID"),
    os.getenv("GOOGLE_EXPO_CLIENT_ID"),
    os.getenv("GOOGLE_ANDROID_CLIENT_ID"),   # add later if/when you ship Android
    os.getenv("GOOGLE_WEB_CLIENT_ID"),       # optional (web)
] if v}

APPLE_BUNDLE_ID = os.getenv("APPLE_BUNDLE_ID")  # e.g., com.hypewave.ai (native iOS)

# --- Models ---
class UserRegister(BaseModel):
    email: str
    password: str
    username: str | None = None
    avatar_url: str | None = None

class UserLogin(BaseModel):
    email: str
    password: str

class IdTokenBody(BaseModel):
    id_token: str

# --- Helpers ---
def _mint_session_for_email(email: str, default_name: str = "User", avatar_url: str = "", login_method: str = "oauth"):
    """Find or create a user, then mint our JWT."""
    user = get_user_by_email(email)
    if not user:
        create_user_in_db(
            email=email,
            password_hash="",  # passwordless for OAuth
            extra={"username": default_name, "avatar_url": avatar_url, "login_method": login_method}
        )
        user = get_user_by_email(email)
    token = create_access_token({"sub": str(user["_id"]), "email": user["email"]})
    return {"access_token": token, "token_type": "bearer"}

# --- Core auth utilities ---
def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(oauth2_scheme)):
    token = credentials.credentials
    payload = decode_access_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid or expired token.")
    user = get_user_by_id(payload["sub"])
    if not user:
        raise HTTPException(status_code=401, detail="User not found.")
    update_user_last_seen(str(user["_id"]))
    return {
        "user_id": str(user["_id"]),
        "email": user["email"],
        "username": user.get("username"),
        "avatar_url": user.get("avatar_url"),
        "login_method": user.get("login_method")
    }

# --- Email/password ---
@router.post("/register")
def register(user: UserRegister):
    if get_user_by_email(user.email):
        raise HTTPException(status_code=400, detail="Email already registered.")
    hashed_pw = hash_password(user.password)
    create_user_in_db(
        email=user.email,
        password_hash=hashed_pw,
        extra={
            "username": user.username or user.email.split("@")[0],
            "avatar_url": user.avatar_url or "",
            "login_method": "email",
        },
    )
    return {"message": "Account created successfully."}

@router.post("/login")
def login(user: UserLogin):
    db_user = get_user_by_email(user.email)
    if not db_user:
        raise HTTPException(status_code=401, detail="Account does not exist.")
    if not verify_password(user.password, db_user["password_hash"]):
        raise HTTPException(status_code=400, detail="Invalid credentials.")
    token = create_access_token({"sub": str(db_user["_id"]), "email": db_user["email"]})
    return {"access_token": token, "token_type": "bearer"}

# --- Me / profile ---
@router.get("/me")
def get_me(user=Depends(get_current_user)):
    return user

@router.patch("/me")
def update_me(user_update: dict = Body(...), user=Depends(get_current_user)):
    updated_fields = {}
    if "username" in user_update:
        updated_fields["username"] = user_update["username"]
    if updated_fields:
        users_coll.update_one({"_id": ObjectId(user["user_id"])}, {"$set": updated_fields})
    return {"message": "Profile updated successfully."}

@router.patch("/me/password")
def update_password(data: dict = Body(...), user=Depends(get_current_user)):
    old_pw = data.get("old_password")
    new_pw = data.get("new_password")
    confirm_pw = data.get("confirm_password")
    if not old_pw or not new_pw or not confirm_pw:
        raise HTTPException(status_code=400, detail="All fields are required.")
    if new_pw != confirm_pw:
        raise HTTPException(status_code=400, detail="New passwords do not match.")
    user_doc = get_user_by_id(user["user_id"])
    if not verify_password(old_pw, user_doc["password_hash"]):
        raise HTTPException(status_code=401, detail="Incorrect current password.")
    users_coll.update_one({"_id": user_doc["_id"]}, {"$set": {"password_hash": hash_password(new_pw)}})
    return {"message": "Password updated successfully"}

@router.post("/me/avatar")
async def upload_avatar(file: UploadFile = File(...), user: dict = Depends(get_current_user)):
    # Cloudinary is already configured in api.py
    import cloudinary.uploader  # local import to avoid import order issues
    try:
        result = cloudinary.uploader.upload(
            file.file,
            folder="avatars",
            public_id=f"user_{user['user_id']}",
            overwrite=True,
            resource_type="image",
        )
        avatar_url = result.get("secure_url")
        users_coll.update_one({"_id": ObjectId(user["user_id"])}, {"$set": {"avatar_url": avatar_url}})
        return {"avatar_url": avatar_url}
    except Exception as e:
        print("Upload error:", e)
        raise HTTPException(status_code=500, detail="Upload failed.")

@router.delete("/me")
def delete_account(user=Depends(get_current_user)):
    res = users_coll.delete_one({"_id": ObjectId(user["user_id"])})
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="User not found.")
    return {"message": "Account deleted successfully"}

# --- Google Sign-in (ID token flow) ---
@router.post("/login/google")
def google_login(body: IdTokenBody):
    id_token = body.id_token
    # Using Google tokeninfo is OK; you can swap for offline verification later (google-auth)
    r = requests.get("https://oauth2.googleapis.com/tokeninfo", params={"id_token": id_token}, timeout=10)
    if r.status_code != 200:
        raise HTTPException(status_code=401, detail="Invalid Google token.")
    payload = r.json()
    email = payload.get("email")
    aud   = payload.get("aud")
    iss   = payload.get("iss")

    if iss not in ("https://accounts.google.com", "accounts.google.com"):
        raise HTTPException(status_code=401, detail="Invalid token issuer.")
    if GOOGLE_ALLOWED_AUDS and aud not in GOOGLE_ALLOWED_AUDS:
        raise HTTPException(status_code=401, detail="Token audience mismatch.")
    if not email:
        raise HTTPException(status_code=400, detail="Missing email in Google payload.")

    picture = payload.get("picture") or ""
    name = payload.get("name") or email.split("@")[0]
    return _mint_session_for_email(email, default_name=name, avatar_url=picture, login_method="google")

# --- Apple Sign-in (native; identityToken verification via JWKS) ---
_APPLE_JWKS = None
_APPLE_JWKS_AT = 0

def _get_apple_jwks():
    global _APPLE_JWKS, _APPLE_JWKS_AT
    now = time.time()
    if not _APPLE_JWKS or (now - _APPLE_JWKS_AT) > 3600:
        _APPLE_JWKS = requests.get("https://appleid.apple.com/auth/keys", timeout=10).json()
        _APPLE_JWKS_AT = now
    return _APPLE_JWKS

def _apple_key_for_kid(kid: str):
    jwks = _get_apple_jwks()
    for k in jwks.get("keys", []):
        if k.get("kid") == kid:
            return k
    return None

@router.post("/login/apple")
def apple_login(body: IdTokenBody):
    if not APPLE_BUNDLE_ID:
        raise HTTPException(status_code=500, detail="Server missing APPLE_BUNDLE_ID.")
    id_token = body.id_token

    # 1) Get header, choose the right JWK by kid
    try:
        header = jwt.get_unverified_header(id_token)
        jwk = _apple_key_for_kid(header.get("kid", ""))
        if not jwk:
            raise HTTPException(status_code=401, detail="Apple key not found.")
    except JWTError as e:
        raise HTTPException(status_code=401, detail=f"Invalid Apple token header: {e}")

    # 2) Verify signature & claims
    try:
        claims = jwt.decode(
            id_token,
            jwk,  # jose can take a JWK dict directly
            algorithms=[jwk.get("alg", "RS256")],
            audience=APPLE_BUNDLE_ID,                 # native app -> bundle id
            issuer="https://appleid.apple.com",
            options={"verify_at_hash": False},        # not used in native flow
        )
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Invalid Apple token: {e}")

    email = claims.get("email")
    if not email:
        # In rare cases Apple withholds email after first authorization; you can map by sub if you store it.
        raise HTTPException(status_code=400, detail="Email not present in Apple token.")

    name = email.split("@")[0]
    return _mint_session_for_email(email, default_name=name, login_method="apple")
