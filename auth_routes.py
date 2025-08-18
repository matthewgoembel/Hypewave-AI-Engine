# ✅ auth_routes.py (Updated)

from fastapi import APIRouter, Body, HTTPException, Depends, status, UploadFile, File
import cloudinary
import cloudinary.uploader
import os, requests
from bson import ObjectId
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
import requests
from auth_utils import hash_password, verify_password, create_access_token, decode_access_token
from db import get_user_by_email, create_user_in_db, get_user_by_id, update_user_last_seen, users_coll

router = APIRouter()
oauth2_scheme = HTTPBearer()

GOOGLE_ALLOWED_AUDS = {
    os.getenv("GOOGLE_IOS_CLIENT_ID"),
    os.getenv("GOOGLE_ANDROID_CLIENT_ID"),
    os.getenv("GOOGLE_WEB_CLIENT_ID"),
    os.getenv("GOOGLE_EXPO_CLIENT_ID"),
}

class UserRegister(BaseModel):
    email: str
    password: str
    username: str | None = None
    avatar_url: str | None = None

class UserLogin(BaseModel):
    email: str
    password: str

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
            "login_method": "email"
        }
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


def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(oauth2_scheme)):
    token = credentials.credentials
    payload = decode_access_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid or expired token.")
    user = get_user_by_id(payload["sub"])
    if not user:
        raise HTTPException(status_code=401, detail="User not found.")
    update_user_last_seen(str(user["_id"]))  # ✅ log last seen
    return {
        "user_id": str(user["_id"]),
        "email": user["email"],
        "username": user.get("username"),
        "avatar_url": user.get("avatar_url"),
        "login_method": user.get("login_method")
    }

@router.get("/me")
def get_me(user=Depends(get_current_user)):
    return user

@router.patch("/me")
def update_me(user_update: dict = Body(...), user=Depends(get_current_user)):
    from db import db
    updated_fields = {}

    if "username" in user_update:
        updated_fields["username"] = user_update["username"]

    if updated_fields:
        db["users"].update_one({"_id": ObjectId(user["user_id"])}, {"$set": updated_fields})
        print(f"✅ Updated user {user['user_id']} with: {updated_fields}")
    else:
        print("⚠️ No updates provided.")

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

    from db import client
    client["hypewave"]["users"].update_one(
        {"_id": user_doc["_id"]},
        {"$set": {"password_hash": hash_password(new_pw)}}
    )

    return {"message": "Password updated successfully"}

@router.post("/me/avatar")
async def upload_avatar(file: UploadFile = File(...), user: dict = Depends(get_current_user)):
    from bson import ObjectId
    try:
        # Use the string user_id returned by get_current_user
        result = cloudinary.uploader.upload(
            file.file,
            folder="avatars",
            public_id=f"user_{user['user_id']}",
            overwrite=True,
            resource_type="image",
        )
        avatar_url = result.get("secure_url")

        # Convert to ObjectId for the DB update
        users_coll.update_one(
            {"_id": ObjectId(user["user_id"])},
            {"$set": {"avatar_url": avatar_url}}
        )

        return {"avatar_url": avatar_url}
    except Exception as e:
        print("Upload error:", e)
        raise HTTPException(status_code=500, detail="Upload failed.")

@router.delete("/me")
def delete_account(user=Depends(get_current_user)):
    from db import users_coll
    from bson import ObjectId

    result = users_coll.delete_one({"_id": ObjectId(user["user_id"])})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="User not found.")

    return {"message": "Account deleted successfully"}

def _allowed_google_auds():
    # Only iOS for now
    ids = [os.getenv("GOOGLE_IOS_CLIENT_ID")]
    return {i for i in ids if i}

@router.post("/login/google")
def google_login(id_token: str = Body(..., embed=True)):
    r = requests.get("https://oauth2.googleapis.com/tokeninfo", params={"id_token": id_token}, timeout=10)
    if r.status_code != 200:
        raise HTTPException(status_code=401, detail="Invalid Google token.")

    payload = r.json()
    email = payload.get("email")
    aud = payload.get("aud")
    iss = payload.get("iss")

    if iss not in ("https://accounts.google.com", "accounts.google.com"):
        raise HTTPException(status_code=401, detail="Invalid token issuer.")

    allowed = {v for v in [
        os.getenv("GOOGLE_IOS_CLIENT_ID"),
        os.getenv("GOOGLE_EXPO_CLIENT_ID")
    ] if v}

    if allowed and aud not in allowed:
        raise HTTPException(status_code=401, detail="Token audience mismatch.")

    if not email:
        raise HTTPException(status_code=400, detail="Missing email in Google payload.")

    picture = payload.get("picture") or ""
    name = payload.get("name") or email.split("@")[0]

    user = get_user_by_email(email)
    if not user:
        create_user_in_db(
            email=email,
            password_hash="",
            extra={"username": name, "avatar_url": picture, "login_method": "google"}
        )
        user = get_user_by_email(email)

    token = create_access_token({"sub": str(user["_id"]), "email": user["email"]})
    return {"access_token": token, "token_type": "bearer"}

