# ✅ auth_routes.py (Updated)

from fastapi import APIRouter, Body, HTTPException, Depends, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
import requests
from auth_utils import hash_password, verify_password, create_access_token, decode_access_token
from db import get_user_by_email, create_user_in_db, get_user_by_id, update_user_last_seen

router = APIRouter()
oauth2_scheme = HTTPBearer()

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

@router.post("/login/google")
def google_login(id_token: str = Body(...)):
    response = requests.get(f"https://oauth2.googleapis.com/tokeninfo?id_token={id_token}")
    if response.status_code != 200:
        raise HTTPException(status_code=401, detail="Invalid Google token.")

    payload = response.json()
    email = payload.get("email")
    picture = payload.get("picture")
    name = payload.get("name")

    if not email:
        raise HTTPException(status_code=400, detail="Missing email in Google payload.")

    user = get_user_by_email(email)
    if not user:
        create_user_in_db(
            email=email,
            password_hash="",
            extra={
                "username": name or email.split("@")[0],
                "avatar_url": picture or "",
                "login_method": "google"
            }
        )
        user = get_user_by_email(email)

    token = create_access_token({"sub": str(user["_id"]), "email": user["email"]})
    return {"access_token": token, "token_type": "bearer"}
