from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app import models
from app.auth import curator_required, volunteer_required
from app.services import change_application_status, ApplicationStatus

router = APIRouter(prefix="/applications", tags=["applications"])


@router.post("/{app_id}/approve")
def approve(
    app_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(curator_required),
):
    application = change_application_status(db, app_id, ApplicationStatus.APPROVED, current_user)

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

    return {"success": True, "message": "Заявка одобрена, волонтёр назначен"}


@router.post("/{app_id}/reject")
def reject(
    app_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(curator_required),
):
    change_application_status(db, app_id, ApplicationStatus.REJECTED, current_user)
    return {"success": True, "message": "Заявка отклонена"}


@router.post("/{app_id}/cancel")
def cancel(
    app_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(volunteer_required),
):
    change_application_status(db, app_id, ApplicationStatus.CANCELLED, current_user)
    return {"success": True, "message": "Заявка отменена"}