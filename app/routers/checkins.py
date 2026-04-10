from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional
from datetime import datetime
from app import models, auth
from app.database import get_db
from app.logger import logger

router = APIRouter(prefix="/checkins", tags=["checkins"])


class CheckinCreate(BaseModel):
    task_id: int
    qr_code: str
    lat: Optional[float] = None
    lng: Optional[float] = None




@router.post("/")
def create_checkin(
    data: CheckinCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.volunteer_required),
):
    task = db.query(models.Task).filter(models.Task.id == data.task_id).first()
    if not task:
        raise HTTPException(404, "Задача не найдена")

    assignment = db.query(models.TaskAssignment).filter(
        models.TaskAssignment.task_id == data.task_id,
        models.TaskAssignment.user_id == current_user.id,
    ).first()
    if not assignment:
        raise HTTPException(403, "Вы не назначены на эту задачу")

    assignment.status = "checked_in"
    db.commit()

    logger.info(
        f"[CHECKIN] volunteer={current_user.email} "
        f"task={data.task_id} qr={data.qr_code} "
        f"lat={data.lat} lng={data.lng}"
    )

    return {
        "success":    True,
        "message":    "Check-in выполнен",
        "volunteer":  current_user.name,
        "task":       task.title,
        "checked_at": datetime.utcnow().isoformat(),
    }


@router.get("/")
def get_checkins(
    task_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.curator_required),
):
    query = db.query(models.TaskAssignment).filter(
        models.TaskAssignment.status == "checked_in"
    )
    if task_id:
        query = query.filter(models.TaskAssignment.task_id == task_id)

    checkins = query.all()

    return [
        {
            "task_id":    c.task_id,
            "task_title": c.task.title if c.task else "—",
            "user_id":    c.user_id,
            "user_name":  c.user.name if c.user else "—",
            "status":     c.status,
            "checked_at": c.assigned_at,
        }
        for c in checkins
    ]


@router.get("/my")
def get_my_checkins(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.volunteer_required),
):
    checkins = db.query(models.TaskAssignment).filter(
        models.TaskAssignment.user_id == current_user.id,
        models.TaskAssignment.status == "checked_in",
    ).all()

    return [
        {
            "task_id":    c.task_id,
            "task_title": c.task.title if c.task else "—",
            "checked_at": c.assigned_at,
        }
        for c in checkins
    ]