from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app import models, auth
from app.database import get_db
from pydantic import BaseModel

router = APIRouter(prefix="/projects", tags=["feedback"])


class FeedbackCreate(BaseModel):
    rating: int
    comment: str


@router.post("/{project_id}/feedback")
def create_feedback(
    project_id: int,
    feedback: FeedbackCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.volunteer_required),
):
    project = db.query(models.Project).filter(models.Project.id == project_id).first()
    if not project:
        raise HTTPException(404, "Проект не найден")

    fb = models.ProjectFeedback(
        project_id=project_id,
        user_id=current_user.id,
        rating=feedback.rating,
        comment=feedback.comment,
    )
    db.add(fb)
    db.commit()
    return {"success": True, "message": "Отзыв добавлен"}


@router.patch("/tasks/{task_id}")
def update_task(
    task_id: int,
    task_update: dict,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.organizer_required),
):
    task = db.query(models.Task).filter(models.Task.id == task_id).first()
    if not task:
        raise HTTPException(404, "Задача не найдена")

    if db.query(models.TaskApplication).filter(
        models.TaskApplication.task_id == task_id
    ).first():
        raise HTTPException(400, "Нельзя редактировать задачу после поступления заявок")

    for key, value in task_update.items():
        if hasattr(task, key):
            setattr(task, key, value)

    db.commit()
    return {"success": True, "message": "Задача обновлена"}


@router.post("/tasks/{task_id}/assign/{user_id}")
def direct_assign(
    task_id: int,
    user_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.curator_required),
):
    task = db.query(models.Task).filter(models.Task.id == task_id).first()
    if not task:
        raise HTTPException(404, "Задача не найдена")

    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(404, "Пользователь не найден")

    existing = db.query(models.TaskAssignment).filter(
        models.TaskAssignment.task_id == task_id,
        models.TaskAssignment.user_id == user_id,
    ).first()
    if existing:
        raise HTTPException(400, "Волонтёр уже назначен")

    assignment = models.TaskAssignment(
        task_id=task_id,
        user_id=user_id,
        assigned_by=current_user.id,
        status="assigned",
    )
    db.add(assignment)
    db.commit()
    return {"success": True, "message": "Волонтёр назначен напрямую"}