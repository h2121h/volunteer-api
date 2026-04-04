from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import Optional
from pydantic import BaseModel
from datetime import date
from app import models, auth
from app.database import get_db

router = APIRouter(prefix="/api/tasks", tags=["tasks"])


class TaskCreate(BaseModel):
    project_id: int
    title: str
    description: Optional[str] = None
    event_date: date
    location: Optional[str] = None
    needed_people: int = 5


@router.get("/")
def get_tasks(
        status: Optional[str] = None,
        db: Session = Depends(get_db),
        current_user: models.User = Depends(auth.get_current_active_user),
):
    query = db.query(models.Task)
    if status:
        query = query.filter(models.Task.status == status)
    tasks = query.all()
    return [
        {
            "id": t.id,
            "project_id": t.project_id,
            "title": t.title,
            "description": t.description,
            "event_date": t.event_date,
            "location": t.location,
            "needed_people": t.needed_people,
            "status": t.status,
        }
        for t in tasks
    ]


@router.get("/my-tasks")
def get_my_tasks(
        db: Session = Depends(get_db),
        current_user: models.User = Depends(auth.volunteer_required),
):
    tasks = db.query(models.Task).join(
        models.TaskAssignment
    ).filter(
        models.TaskAssignment.user_id == current_user.id
    ).all()

    return [
        {
            "id": t.id,
            "title": t.title,
            "description": t.description,
            "status": t.status
        }
        for t in tasks
    ]


@router.post("/", status_code=201)
def create_task(
        task: TaskCreate,
        db: Session = Depends(get_db),
        current_user: models.User = Depends(auth.organizer_required),
):
    project = db.query(models.Project).filter(models.Project.id == task.project_id).first()
    if not project:
        raise HTTPException(404, "Проект не найден")

    db_task = models.Task(
        project_id=task.project_id,
        title=task.title,
        description=task.description,
        event_date=task.event_date,
        location=task.location,
        needed_people=task.needed_people,
        status="open",
    )
    db.add(db_task)
    db.commit()
    db.refresh(db_task)
    return {"success": True, "id": db_task.id, "title": db_task.title}


@router.get("/{task_id}")
def get_task(
        task_id: int,
        db: Session = Depends(get_db),
        current_user: models.User = Depends(auth.get_current_active_user),
):
    task = db.query(models.Task).filter(models.Task.id == task_id).first()
    if not task:
        raise HTTPException(404, "Задача не найдена")
    return {
        "id": task.id,
        "project_id": task.project_id,
        "title": task.title,
        "description": task.description,
        "event_date": task.event_date,
        "location": task.location,
        "needed_people": task.needed_people,
        "status": task.status,
    }