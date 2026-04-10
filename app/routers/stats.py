from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func
from pydantic import BaseModel
from app import models, auth
from app.database import get_db
from app.logger import logger

router = APIRouter(prefix="/api", tags=["stats"])


@router.get("/stats")
def get_stats(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user),
):
    """GET /api/stats — общая статистика платформы."""
    volunteers_count = db.query(models.User).join(models.Role).filter(
        models.Role.code == "volunteer"
    ).count()

    active_tasks = db.query(models.Task).filter(
        models.Task.status == "open"
    ).count()

    completed_tasks = db.query(models.Task).filter(
        models.Task.status == "completed"
    ).count()

    approved_reports = db.query(models.TaskReport).filter(
        models.TaskReport.is_approved == True
    ).count()

    total_hours = db.query(func.sum(models.TaskReport.hours)).filter(
        models.TaskReport.is_approved == True
    ).scalar() or 0

    return {
        "volunteers_count":  volunteers_count,
        "active_tasks":      active_tasks,
        "completed_tasks":   completed_tasks,
        "approved_reports":  approved_reports,
        "total_hours":       float(total_hours),
    }


@router.get("/roles")
def get_roles(
    db: Session = Depends(get_db),
):
    """GET /api/roles — список ролей."""
    roles = db.query(models.Role).all()
    return [{"id": r.id, "code": r.code, "name": r.name} for r in roles]


# =============================================================================
# FCM Push Notifications
# =============================================================================

class FCMTokenRequest(BaseModel):
    fcm_token: str
    device_type: str = "android"   # android / ios


@router.post("/fcm/register")
def register_fcm_token(
    data: FCMTokenRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.volunteer_required),
):
    """
    POST /api/fcm/register — зарегистрировать FCM токен устройства.
    Push-уведомления: куратор пишет -> Celery -> FCM -> телефон.
    BR-08: не чаще 1 сообщения в час.
    """
    # Сохраняем токен в профиль пользователя
    # (добавь поле fcm_token в модель User)
    current_user.fcm_token = data.fcm_token
    db.commit()

    logger.info(
        f"[FCM] volunteer={current_user.email} "
        f"device={data.device_type} token={data.fcm_token[:20]}..."
    )

    return {
        "success":     True,
        "message":     "FCM токен зарегистрирован",
        "user_id":     current_user.id,
        "device_type": data.device_type,
    }
