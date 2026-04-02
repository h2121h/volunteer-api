from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional
from app.database import get_db
from app import models
from app.auth import curator_required, volunteer_required
from app.services.status_service import ApplicationStatus, can_transition, validate_transition

router = APIRouter(prefix="/applications", tags=["applications"])


@router.get("/my")
def get_my_applications(
        db: Session = Depends(get_db),
        current_user: models.User = Depends(volunteer_required)
):
    applications = db.query(models.TaskApplication).filter(
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


@router.get("/pending")
def get_pending_applications(
        db: Session = Depends(get_db),
        current_user: models.User = Depends(curator_required)
):
    applications = db.query(models.TaskApplication).filter(
        models.TaskApplication.status == ApplicationStatus.CREATED.value
    ).all()

    return [
        {
            "id": a.id,
            "task_id": a.task_id,
            "task_title": a.task.title if a.task else "Неизвестно",
            "user_id": a.user_id,
            "user_name": a.user.name if a.user else "Неизвестно",
            "message": a.message,
            "applied_at": a.applied_at
        }
        for a in applications
    ]


@router.patch("/{application_id}/status")
def change_application_status(
        application_id: int,
        new_status: str,
        db: Session = Depends(get_db),
        current_user: models.User = Depends(curator_required)
):
    application = db.query(models.TaskApplication).filter(
        models.TaskApplication.id == application_id
    ).first()

    if not application:
        raise HTTPException(status_code=404, detail="Заявка не найдена")

    current_status = application.status

    if current_status == new_status:
        return {"success": True, "message": "Статус не изменился"}

    try:
        validate_transition(
            ApplicationStatus(current_status),
            ApplicationStatus(new_status)
        )
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))

    application.status = new_status
    db.commit()

    return {
        "success": True,
        "message": f"Статус изменён с {current_status} на {new_status}",
        "old_status": current_status,
        "new_status": new_status
    }


@router.get("/{application_id}")
def get_application(
        application_id: int,
        db: Session = Depends(get_db),
        current_user: models.User = Depends(volunteer_required)
):
    application = db.query(models.TaskApplication).filter(
        models.TaskApplication.id == application_id
    ).first()

    if not application:
        raise HTTPException(status_code=404, detail="Заявка не найдена")

    if application.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Доступ запрещён")

    return {
        "id": application.id,
        "task_id": application.task_id,
        "task_title": application.task.title if application.task else "Неизвестно",
        "status": application.status,
        "message": application.message,
        "applied_at": application.applied_at
    }