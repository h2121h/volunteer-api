from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from datetime import timedelta
from app import schemas, models, auth
from app.database import get_db
from app.config import settings

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/refresh", response_model=schemas.Token)
def refresh_token(
        refresh_token: str,
        db: Session = Depends(get_db)
):
    try:
        payload = auth.decode_token(refresh_token)
        if not payload:
            raise HTTPException(status_code=401, detail="Invalid refresh token")

        user = auth.get_user_by_email(db, payload.get("sub"))
        if not user or not user.is_active:
            raise HTTPException(status_code=401, detail="Invalid refresh token")

        new_access = auth.create_access_token(
            data={"sub": user.email},
            expires_delta=timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
        )
        return {"access_token": new_access, "token_type": "bearer"}
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid refresh token")


@router.post("/users/{user_id}/block")
def block_user(
        user_id: int,
        db: Session = Depends(get_db),
        current_user: models.User = Depends(auth.admin_required)
):
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(404, "User not found")

    user.is_active = False
    db.commit()
    return {"success": True, "message": f"Пользователь {user.email} заблокирован"}