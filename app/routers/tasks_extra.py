from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload
from pydantic import BaseModel
from typing import Optional
from datetime import date
from app import models, auth
from app.database import get_db
from app.logger import logger

router = APIRouter(prefix="/api/tasks", tags=["tasks"])


class TaskApply(BaseModel):
    message: Optional[str] = ""


class TaskEdit(BaseModel):
    title:         Optional[str]  = None
    description:   Optional[str]  = None
    event_date:    Optional[date] = None
    location:      Optional[str]  = None
    needed_people: Optional[int]  = None


@router.post("/{task_id}/apply")
def apply_to_task(
    task_id: int,
    data: TaskApply,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.volunteer_required),
):
    """
    POST /api/tasks/{task_id}/apply — записаться на задачу (UC-5).
    BR-01: проверяем лимит участников.
    BR-05: проверяем конфликт расписания.
    """
    task = db.query(models.Task).filter(models.Task.id == task_id).first()
    if not task:
        raise HTTPException(404, "Задача не найдена")

    if task.status != "open":
        raise HTTPException(400, "Задача недоступна для записи")

    # BR-01: проверяем лимит
    current_count = db.query(models.TaskApplication).filter(
        models.TaskApplication.task_id == task_id,
        models.TaskApplication.status.in_(["created", "approved"]),
    ).count()
    if current_count >= task.needed_people:
        raise HTTPException(400, "BR-01: достигнут лимит участников")

    # BR-05: проверяем конфликт расписания
    conflict = db.query(models.TaskApplication).join(models.Task).filter(
        models.TaskApplication.user_id == current_user.id,
        models.TaskApplication.status.in_(["created", "approved"]),
        models.Task.event_date == task.event_date,
        models.Task.id != task_id,
    ).first()
    if conflict:
        raise HTTPException(400, f"BR-05: конфликт расписания с задачей {conflict.task_id}")

    # Проверяем не подавал ли уже
    existing = db.query(models.TaskApplication).filter(
        models.TaskApplication.task_id == task_id,
        models.TaskApplication.user_id == current_user.id,
    ).first()
    if existing:
        raise HTTPException(400, "Вы уже подали заявку на эту задачу")

    application = models.TaskApplication(
        task_id=task_id,
        user_id=current_user.id,
        message=data.message,
        status="created",
    )
    db.add(application)
    db.commit()
    db.refresh(application)

    logger.info(f"[APPLY] volunteer={current_user.email} task={task_id}")

    return {
        "success":    True,
        "id":         application.id,
        "task_title": task.title,
        "status":     application.status,
        "message":    "Заявка подана, ожидайте подтверждения куратора",
    }


@router.patch("/{task_id}/complete")
def complete_task(
    task_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.volunteer_required),
):
    """PATCH /api/tasks/{task_id}/complete — отметить задачу выполненной."""
    assignment = db.query(models.TaskAssignment).filter(
        models.TaskAssignment.task_id == task_id,
        models.TaskAssignment.user_id == current_user.id,
    ).first()
    if not assignment:
        raise HTTPException(403, "Вы не назначены на эту задачу")

    assignment.status = "completed"
    db.commit()

    logger.info(f"[COMPLETE] volunteer={current_user.email} task={task_id}")

    return {"success": True, "message": "Задача отмечена выполненной"}


@router.put("/{task_id}/edit")
def edit_task(
    task_id: int,
    data: TaskEdit,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.organizer_required),
):
    """
    PUT /api/tasks/{task_id}/edit — редактировать задачу.
    BR-10: после первой заявки редактирование заблокировано.
    """
    task = db.query(models.Task).filter(models.Task.id == task_id).first()
    if not task:
        raise HTTPException(404, "Задача не найдена")

    # BR-10: нельзя редактировать после первой заявки
    has_applications = db.query(models.TaskApplication).filter(
        models.TaskApplication.task_id == task_id
    ).first()
    if has_applications:
        raise HTTPException(400, "BR-10: нельзя редактировать задачу после поступления заявок")

    if data.title         is not None: task.title         = data.title
    if data.description   is not None: task.description   = data.description
    if data.event_date    is not None: task.event_date    = data.event_date
    if data.location      is not None: task.location      = data.location
    if data.needed_people is not None: task.needed_people = data.needed_people

    db.commit()
    logger.info(f"[EDIT_TASK] organizer={current_user.email} task={task_id}")

    return {"success": True, "message": "Задача обновлена"}


@router.get("/my-applications")
def get_my_applications(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.volunteer_required),
):
    """GET /api/my-applications — свои заявки."""
    apps = db.query(models.TaskApplication).options(
        joinedload(models.TaskApplication.task)
    ).filter(
        models.TaskApplication.user_id == current_user.id
    ).all()

    return [
        {
            "id":         a.id,
            "task_id":    a.task_id,
            "task_title": a.task.title if a.task else "—",
            "status":     a.status,
            "applied_at": a.applied_at,
        }
        for a in apps
    ]
