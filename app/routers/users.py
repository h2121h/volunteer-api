from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from datetime import timedelta
from pydantic import BaseModel, EmailStr
from typing import Optional
from app import models, auth
from app.database import get_db
from app.config import settings

router = APIRouter(prefix="/api", tags=["users"])


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
    existing = db.query(models.User).filter(models.User.email == data.email).first()
    if existing:
        raise HTTPException(status_code=409, detail="Email уже зарегистрирован")

    role = db.query(models.Role).filter(models.Role.code == data.role).first()
    if not role:
        raise HTTPException(status_code=404, detail=f"Роль '{data.role}' не найдена")

    user = models.User(
        email=data.email,
        password_hash=auth.get_password_hash(data.password),
        name=data.name,
        phone=data.phone,
        city=data.city,
        role_id=role.id,
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

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
    user = auth.authenticate_user(db, data.email, data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Неверный email или пароль",
            headers={"WWW-Authenticate": "Bearer"},
        )

    access_token = auth.create_access_token(
        data={"sub": user.email, "user_id": user.id},
        expires_delta=timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
    )
    return {"access_token": access_token, "token_type": "bearer"}


@router.get("/users/me")
def get_me(current_user: models.User = Depends(auth.get_current_active_user)):
    return {
        "id":         current_user.id,
        "email":      current_user.email,
        "name":       current_user.name,
        "role":       current_user.role.code,
        "role_name":  current_user.role.name,
        "is_active":  current_user.is_active,
        "created_at": current_user.created_at,
    }