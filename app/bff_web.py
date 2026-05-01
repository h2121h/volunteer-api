"""
BFF (Backend for Frontend) — Web клиент (HTML/JS, куратор).

Агрегирует данные специально для веб-интерфейса куратора:
- Заявки только от своих проектов (ownership)
- Отчёты только от своих волонтёров
- Статистика только по своей команде
- WebSocket-ready данные о явке
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session, joinedload, contains_eager
from sqlalchemy import func
from datetime import datetime, timedelta
from app import models, auth
from app.database import get_db
from app.logger import logger

router = APIRouter(prefix="/bff/web", tags=["BFF Web"])

AUTO_APPROVE_HOURS = 72  # BR-03


@router.get("/dashboard")
def web_dashboard(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.curator_required),
):
    """
    Один запрос — куратор получает всё для своей панели.
    Ownership: только данные своих проектов и команды.
    """
    # Заявки только от своих проектов (ownership)
    applications = db.query(models.TaskApplication).options(
        contains_eager(models.TaskApplication.task),  # join уже есть ниже — reuse его
        joinedload(models.TaskApplication.user),
    ).join(models.Task).join(models.Project).filter(
        models.Project.created_by == current_user.id,
        models.TaskApplication.status == "created",
    ).all()

    # Отчёты на проверке (только своих волонтёров)
    # BR-03: автоодобрение через 72ч
    deadline = datetime.utcnow() - timedelta(hours=AUTO_APPROVE_HOURS)
    expired = db.query(models.TaskReport).join(
        models.TaskAssignment
    ).join(
        models.Task
    ).join(
        models.Project
    ).filter(
        models.Project.created_by == current_user.id,
        models.TaskReport.is_approved == False,
        models.TaskReport.submitted_at <= deadline,
    ).all()

    for r in expired:
        r.is_approved = True
        logger.info(f"[BFF_WEB] BR-03 auto-approve: report={r.id}")
    if expired:
        db.commit()

    pending_reports = db.query(models.TaskReport).options(
        joinedload(models.TaskReport.user),
        joinedload(models.TaskReport.assignment),
    ).join(
        models.TaskAssignment
    ).join(
        models.Task
    ).join(
        models.Project
    ).filter(
        models.Project.created_by == current_user.id,
        models.TaskReport.is_approved == False,
    ).all()

    # Явка — кто сделал check-in (UC-14)
    checkins = db.query(models.TaskAssignment).options(
        joinedload(models.TaskAssignment.user),
        joinedload(models.TaskAssignment.task),
    ).join(models.Task).join(models.Project).filter(
        models.Project.created_by == current_user.id,
        models.TaskAssignment.status == "checked_in",
    ).all()

    # Статистика по команде
    total_volunteers = db.query(models.TaskAssignment).join(
        models.Task
    ).join(models.Project).filter(
        models.Project.created_by == current_user.id,
    ).distinct(models.TaskAssignment.user_id).count()

    logger.info(
        f"[BFF_WEB] dashboard: curator={current_user.email} "
        f"applications={len(applications)} reports={len(pending_reports)} "
        f"checkins={len(checkins)}"
    )

    return {
        "curator": {
            "id":    current_user.id,
            "name":  current_user.name,
            "email": current_user.email,
        },
        # Заявки волонтёров на одобрение
        "pending_applications": [
            {
                "id":        a.id,
                "task_id":   a.task_id,
                "task_title": a.task.title if a.task else "—",
                "user_id":   a.user_id,
                "user_name": a.user.name if a.user else "—",
                "user_email": a.user.email if a.user else "—",
                "message":   a.message,
                "applied_at": str(a.applied_at) if a.applied_at else None,
            }
            for a in applications
        ],
        # Отчёты на проверке
        "pending_reports": [
            {
                "id":        r.id,
                "user_id":   r.user_id,
                "user_name": r.user.name if r.user else "—",
                "hours":     float(r.hours or 0),
                "comment":   r.comment,
                "photo_url": r.photo_url,
                "submitted_at": str(r.submitted_at) if r.submitted_at else None,
                "auto_approve_at": str(
                    (r.submitted_at or datetime.utcnow()) + timedelta(hours=AUTO_APPROVE_HOURS)
                ) if r.submitted_at else None,
            }
            for r in pending_reports
        ],
        # Явка в реальном времени (UC-14)
        "checkins": [
            {
                "user_id":   c.user_id,
                "user_name": c.user.name if c.user else "—",
                "task_id":   c.task_id,
                "task_title": c.task.title if c.task else "—",
                "checked_at": str(c.assigned_at) if c.assigned_at else None,
            }
            for c in checkins
        ],
        # Статистика команды
        "team_stats": {
            "total_volunteers":   total_volunteers,
            "pending_applications": len(applications),
            "pending_reports":    len(pending_reports),
            "checked_in_today":   len(checkins),
            "auto_approved":      len(expired),
        },
    }
