from datetime import datetime, timedelta
from typing import Optional, List
from jose import JWTError, jwt
from passlib.context import CryptContext
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from app import models
from app.database import get_db
from app.config import settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="api/login")


def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password):
    return pwd_context.hash(password)


<<<<<<< HEAD
def authenticate_user(db: Session, email: str, password: str):
    user = db.query(models.User).filter(models.User.email == email).first()
=======
def authenticate_user(db: Session, username: str, password: str):
    user = db.query(models.User).filter(models.User.email == username).first()
>>>>>>> b8d686ea9f8dbec9dd58be56eb7d10924e958c6c
    if not user or not verify_password(password, user.password_hash):
        return False
    return user


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return encoded_jwt


async def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Не удалось подтвердить учетные данные",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
<<<<<<< HEAD
        email: str = payload.get("sub")
        if email is None:
            raise credentials_exception
=======
        email: str = payload.get("sub") 
        if email is None:
            raise credentials_exception
        token_data = schemas.TokenData(username=email) 
>>>>>>> b8d686ea9f8dbec9dd58be56eb7d10924e958c6c
    except JWTError:
        raise credentials_exception

    user = db.query(models.User).filter(models.User.email == email).first()
    if user is None:
        raise credentials_exception
    return user


async def get_current_active_user(current_user: models.User = Depends(get_current_user)):
    if not current_user.is_active:
<<<<<<< HEAD
        raise HTTPException(status_code=400, detail="Неактивный пользователь")
    return current_user


def require_roles(allowed_roles: List[str]):
    """
    Декоратор для проверки ролей
    allowed_roles: список кодов ролей, которым разрешён доступ
    """

    async def role_checker(current_user: models.User = Depends(get_current_active_user)):
        if current_user.role.code not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Доступ запрещен. Требуется одна из ролей: {', '.join(allowed_roles)}"
            )
        return current_user

    return role_checker


# Предопределённые проверки для разных уровней доступа
def volunteer_required(current_user: models.User = Depends(get_current_active_user)):
    """Доступ для волонтёров и выше"""
    allowed = ["volunteer", "organizer", "curator", "admin"]
    if current_user.role.code not in allowed:
        raise HTTPException(status_code=403, detail="Требуется роль волонтёра или выше")
    return current_user


def organizer_required(current_user: models.User = Depends(get_current_active_user)):
    """Доступ для организаторов и выше"""
    allowed = ["organizer", "curator", "admin"]
    if current_user.role.code not in allowed:
        raise HTTPException(status_code=403, detail="Требуется роль организатора или выше")
    return current_user


def curator_required(current_user: models.User = Depends(get_current_active_user)):
    """Доступ для кураторов и выше"""
    allowed = ["curator", "admin"]
    if current_user.role.code not in allowed:
        raise HTTPException(status_code=403, detail="Требуется роль куратора или выше")
    return current_user


def admin_required(current_user: models.User = Depends(get_current_active_user)):
    """Доступ только для администраторов"""
    if current_user.role.code != "admin":
        raise HTTPException(status_code=403, detail="Требуется роль администратора")
    return current_user
=======
        raise HTTPException(status_code=400, detail="Inactive user")
    return current_user
>>>>>>> b8d686ea9f8dbec9dd58be56eb7d10924e958c6c
