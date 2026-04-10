from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func
from pydantic import BaseModel
from app import models, auth
from app.database import get_db
from app.logger import logger

router = APIRouter(prefix="/api/admin", tags=["admin"])


class ChangeRoleRequest(BaseModel):
    role_code: str


@router.get("/users")
def get_all_users(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.organizer_required),
):
    """GET /api/admin/users — все пользователи системы."""
    users = db.query(models.User).options(
        joinedload(models.User.role)
    ).all()

    return [
        {
            "id":        u.id,
            "name":      u.name,
            "email":     u.email,
            "phone":     u.phone,
            "city":      u.city,
            "role_code": u.role.code if u.role else "—",
            "role_name": u.role.name if u.role else "—",
            "is_active": u.is_active,
        }
        for u in users
    ]


@router.post("/users/{user_id}/toggle-active")
def toggle_user_active(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.organizer_required),
):
    """POST /api/admin/users/{user_id}/toggle-active — блокировка/разблокировка."""
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(404, "Пользователь не найден")

    user.is_active = not user.is_active
    db.commit()

    action = "разблокирован" if user.is_active else "заблокирован"
    logger.warning(f"[TOGGLE_USER] organizer={current_user.email} user={user.email} action={action}")

    return {
        "success":   True,
        "user_id":   user_id,
        "is_active": user.is_active,
        "message":   f"Пользователь {user.email} {action}",
    }


@router.post("/users/{user_id}/change-role")
def change_user_role(
    user_id: int,
    data: ChangeRoleRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.organizer_required),
):
    """POST /api/admin/users/{user_id}/change-role — сменить роль пользователя."""
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(404, "Пользователь не найден")

    role = db.query(models.Role).filter(models.Role.code == data.role_code).first()
    if not role:
        raise HTTPException(404, f"Роль '{data.role_code}' не найдена")

    old_role = user.role.code if user.role else "—"
    user.role_id = role.id
    db.commit()

    logger.info(
        f"[CHANGE_ROLE] organizer={current_user.email} "
        f"user={user.email} {old_role} -> {data.role_code}"
    )

    return {
        "success":  True,
        "user_id":  user_id,
        "old_role": old_role,
        "new_role": data.role_code,
        "message":  f"Роль изменена на {data.role_code}",
    }


@router.get("/stats")
def get_admin_stats(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.organizer_required),
):
    """GET /api/admin/stats — полная статистика системы (UC-18)."""
    total_users      = db.query(models.User).count()
    active_users     = db.query(models.User).filter(models.User.is_active == True).count()
    total_volunteers = db.query(models.User).join(models.Role).filter(models.Role.code == "volunteer").count()
    total_curators   = db.query(models.User).join(models.Role).filter(models.Role.code == "curator").count()
    total_projects   = db.query(models.Project).count()
    active_projects  = db.query(models.Project).filter(models.Project.status == "active").count()
    total_tasks      = db.query(models.Task).count()
    open_tasks       = db.query(models.Task).filter(models.Task.status == "open").count()
    total_reports    = db.query(models.TaskReport).count()
    approved_reports = db.query(models.TaskReport).filter(models.TaskReport.is_approved == True).count()
    pending_reports  = db.query(models.TaskReport).filter(models.TaskReport.is_approved == False).count()
    total_hours      = db.query(func.sum(models.TaskReport.hours)).filter(
        models.TaskReport.is_approved == True
    ).scalar() or 0

    logger.info(f"[ADMIN_STATS] organizer={current_user.email}")

    return {
        "users": {
            "total":      total_users,
            "active":     active_users,
            "volunteers": total_volunteers,
            "curators":   total_curators,
        },
        "projects": {
            "total":  total_projects,
            "active": active_projects,
        },
        "tasks": {
            "total": total_tasks,
            "open":  open_tasks,
        },
        "reports": {
            "total":    total_reports,
            "approved": approved_reports,
            "pending":  pending_reports,
        },
        "total_volunteer_hours": float(total_hours),
    }
