from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app import models, schemas, auth
from app.database import get_db
from pydantic import BaseModel
from app.services.project_service import create_project_with_tasks, create_project_with_single_task

router = APIRouter(prefix="/projects", tags=["feedback"])


class FeedbackCreate(BaseModel):
    rating: int
    comment: str


@router.post("/{project_id}/feedback")
def create_feedback(
        project_id: int,
        feedback: FeedbackCreate,
        db: Session = Depends(get_db),
        current_user: models.User = Depends(auth.volunteer_required)
):
    project = db.query(models.Project).filter(models.Project.id == project_id).first()
    if not project:
        raise HTTPException(404, "Project not found")

    fb = models.ProjectFeedback(
        project_id=project_id,
        user_id=current_user.id,
        rating=feedback.rating,
        comment=feedback.comment
    )
    db.add(fb)
    db.commit()
    return {"success": True, "message": "Отзыв добавлен"}


@router.patch("/tasks/{task_id}")
def update_task(
        task_id: int,
        task_update: dict,
        db: Session = Depends(get_db),
        current_user: models.User = Depends(auth.organizer_required)
):
    task = db.query(models.Task).filter(models.Task.id == task_id).first()
    if not task:
        raise HTTPException(404, "Task not found")
    if task.created_by != current_user.id:
        raise HTTPException(403, "Only creator can edit")

    if db.query(models.TaskApplication).filter(models.TaskApplication.task_id == task_id).first():
        raise HTTPException(400, "Cannot edit task after applications")

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
        current_user: models.User = Depends(auth.curator_required)
):
    task = db.query(models.Task).filter(models.Task.id == task_id).first()
    if not task:
        raise HTTPException(404, "Task not found")

    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(404, "User not found")

    existing = db.query(models.TaskAssignment).filter(
        models.TaskAssignment.task_id == task_id,
        models.TaskAssignment.user_id == user_id
    ).first()

    if existing:
        raise HTTPException(400, "User already assigned")

    assignment = models.TaskAssignment(
        task_id=task_id,
        user_id=user_id,
        assigned_by=current_user.id,
        status="assigned"
    )
    db.add(assignment)
    db.commit()
    return {"success": True, "message": "Волонтёр назначен напрямую"}


@router.post("/with-tasks")
def create_project_and_tasks(
        data: dict,
        db: Session = Depends(get_db),
        current_user: models.User = Depends(organizer_required)
):
    """
    Создаёт проект и связанные с ним задачи в одной транзакции.

    Пример тела запроса:
    {
        "title": "Новый проект",
        "description": "Описание проекта",
        "tasks": [
            {
                "title": "Задача 1",
                "description": "Описание задачи 1",
                "event_date": "2025-04-15",
                "location": "Москва",
                "needed_people": 3
            },
            {
                "title": "Задача 2",
                "description": "Описание задачи 2",
                "event_date": "2025-04-16",
                "location": "СПб",
                "needed_people": 2
            }
        ]
    }
    """
    try:
        title = data.get("title")
        description = data.get("description")
        tasks_data = data.get("tasks", [])

        if not title:
            raise HTTPException(status_code=400, detail="Название проекта обязательно")

        if not tasks_data:
            raise HTTPException(status_code=400, detail="Нужно добавить хотя бы одну задачу")

        project = create_project_with_tasks(
            db=db,
            title=title,
            description=description,
            created_by=current_user.id,
            tasks_data=tasks_data
        )

        return {
            "success": True,
            "message": f"Проект '{title}' и {len(tasks_data)} задач созданы",
            "project_id": project.id,
            "project_title": project.title
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/with-single-task")
def create_project_with_one_task(
        data: dict,
        db: Session = Depends(get_db),
        current_user: models.User = Depends(organizer_required)
):
    """
    Создаёт проект и одну задачу в одной транзакции.

    Пример тела запроса:
    {
        "project_title": "Новый проект",
        "project_description": "Описание проекта",
        "task_title": "Первая задача",
        "task_description": "Описание задачи",
        "event_date": "2025-04-15",
        "location": "Москва"
    }
    """
    try:
        from datetime import date

        event_date = data.get("event_date")
        if isinstance(event_date, str):
            from datetime import datetime
            event_date = datetime.strptime(event_date, "%Y-%m-%d").date()

        project = create_project_with_single_task(
            db=db,
            project_title=data.get("project_title"),
            project_description=data.get("project_description"),
            created_by=current_user.id,
            task_title=data.get("task_title"),
            task_description=data.get("task_description"),
            event_date=event_date,
            location=data.get("location")
        )

        return {
            "success": True,
            "message": f"Проект '{project.title}' и задача созданы",
            "project_id": project.id
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))