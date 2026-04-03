from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from pydantic import BaseModel, EmailStr
from typing import Optional

from app.database import get_db
from app.services import register_user, login_user

router = APIRouter(prefix="/auth", tags=["auth"])


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str
    name: str
    role: str = "volunteer"
    phone: Optional[str] = None
    city: Optional[str] = None


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


@router.post("/register", status_code=201)
def register(data: RegisterRequest, db: Session = Depends(get_db)):
    user = register_user(
        db=db,
        email=data.email,
        password=data.password,
        name=data.name,
        role_code=data.role,
        phone=data.phone,
        city=data.city,
    )
    return {
        "message": "Регистрация успешна",
        "user": {
            "id":    user.id,
            "email": user.email,
            "name":  user.name,
            "role":  user.role.code,
        },
    }


@router.post("/login")
def login(data: LoginRequest, db: Session = Depends(get_db)):
    return login_user(db=db, email=data.email, password=data.password)