# auth_routes.py

# All /login /register /me

from fastapi import APIRouter, HTTPException, Depends, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
from auth_utils import hash_password, verify_password, create_access_token, decode_access_token
from db import get_user_by_email, create_user_in_db, get_user_by_id

router = APIRouter()
oauth2_scheme = HTTPBearer()

class UserRegister(BaseModel):
    email: str
    password: str

class UserLogin(BaseModel):
    email: str
    password: str

@router.post("/register")
def register(user: UserRegister):
    if get_user_by_email(user.email):
        raise HTTPException(status_code=400, detail="Email already registered.")
    hashed_pw = hash_password(user.password)
    create_user_in_db(user.email, hashed_pw)
    return {"message": "Account created successfully."}

@router.post("/login")
def login(user: UserLogin):
    db_user = get_user_by_email(user.email)
    if not db_user or not verify_password(user.password, db_user["password_hash"]):
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
    return {"user_id": str(user["_id"]), "email": user["email"]}


@router.get("/me")
def get_me(user=Depends(get_current_user)):
    return user
