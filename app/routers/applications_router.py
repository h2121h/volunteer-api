from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload
from app.database import get_db
from app import models
from app.auth import curator_required, volunteer_required
from app.services import change_application_status, ApplicationStatus, send_notification
from app.logger import logger

router = APIRouter(prefix="/applications", tags=["applications"])


@router.get("/my")
def get_my_applications(
        db: Session = Depends(get_db),
        current_user: models.User = Depends(volunteer_required)
):
    applications = db.query(models.TaskApplication).options(
        joinedload(models.TaskApplication.task)
    ).filter(
        models.TaskApplication.user_id == current_user.id
    ).all()

    return [
        {
            "id": a.id,
            "task_id": a.task_id,
            "task_title": a.task.title if a.task else "Неизвестно",
            "status": a.status,
            "message": a.message,
            "applied_at": a.applied_at
        }
        for a in applications
    ]


@router.get("/for-curator")
def get_applications_for_curator(
        db: Session = Depends(get_db),
        current_user: models.User = Depends(curator_required)
):
    # ИСПРАВЛЕНО: убран фильтр .filter(models.Project.created_by == current_user.id)
    # Куратор должен видеть ВСЕ заявки, а не только по своим проектам —
    # проекты создаёт организатор, поэтому старый фильтр давал пустой список.
    applications = db.query(models.TaskApplication).options(
        joinedload(models.TaskApplication.task),
        joinedload(models.TaskApplication.user)
    ).all()

    return [
        {
            "id": a.id,
            "task_id": a.task_id,
            "task_title": a.task.title if a.task else "—",
            "user_id": a.user_id,
            "user_name": a.user.name if a.user else "—",
            "user_email": a.user.email if a.user else "—",  # добавлено — фронтенд отображает
            "message": a.message,
            "status": a.status,  # добавлено — фронтенд фильтрует по статусу
            "applied_at": str(a.applied_at) if a.applied_at else None,
        }
        for a in applications
    ]


@router.post("/{app_id}/approve")
def approve(
        app_id: int,
        db: Session = Depends(get_db),
        current_user: models.User = Depends(curator_required),
):
    application = change_application_status(db, app_id, ApplicationStatus.ACTIVE, current_user)

    logger.info(f"[APPROVE] curator={current_user.email} application={app_id}")

    task_id = send_notification(
        application.user_id,
        f"Ваша заявка на задачу одобрена!"
    )

    assignment = models.TaskAssignment(
        task_id=application.task_id,
        user_id=application.user_id,
        assigned_by=current_user.id,
        status="assigned",
    )
    task = db.query(models.Task).filter(models.Task.id == application.task_id).first()
    if task:
        task.status = "in_progress"
    db.add(assignment)
    db.commit()

    return {
        "success": True,
        "message": "Заявка одобрена, волонтёр назначен",
        "notification_task_id": task_id
    }


@router.post("/{app_id}/reject")
def reject(
        app_id: int,
        db: Session = Depends(get_db),
        current_user: models.User = Depends(curator_required),
):
    change_application_status(db, app_id, ApplicationStatus.CANCELLED, current_user)

    logger.warning(f"[REJECT] curator={current_user.email} application={app_id}")

    return {"success": True, "message": "Заявка отклонена"}


@router.post("/{app_id}/cancel")
def cancel(
        app_id: int,
        db: Session = Depends(get_db),
        current_user: models.User = Depends(volunteer_required),
):
    change_application_status(db, app_id, ApplicationStatus.CANCELLED, current_user)
    return {"success": True, "message": "Заявка отменена"}


@router.get("/task/{task_id}")
def get_task_status(
        task_id: str,
):
    from celery.result import AsyncResult
    from app.celery_worker import celery_app

    result = AsyncResult(task_id, app=celery_app)
    return {
        "task_id": task_id,
        "status": result.status,
        "result": result.result if result.ready() else None
    }
