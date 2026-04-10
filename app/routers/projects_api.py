from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload
from pydantic import BaseModel
from typing import Optional
from datetime import date
from app import models, auth
from app.database import get_db
from app.logger import logger

router = APIRouter(prefix="/api/projects", tags=["projects"])


class ProjectCreate(BaseModel):
    title:       str
    description: Optional[str] = None


class TaskCreate(BaseModel):
    project_id:    int
    title:         str
    description:   Optional[str]  = None
    event_date:    date
    location:      Optional[str]  = None
    needed_people: int = 5
    difficulty:    Optional[str]  = "medium"  # easy / medium / hard


@router.get("/")
def get_projects(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user),
):
    """GET /api/projects — список всех проектов."""
    projects = db.query(models.Project).options(
        joinedload(models.Project.creator)
    ).all()

    return [
        {
            "id":          p.id,
            "title":       p.title,
            "description": p.description,
            "status":      p.status,
            "created_by":  p.created_by,
            "creator":     p.creator.name if p.creator else "—",
            "created_at":  p.created_at,
        }
        for p in projects
    ]


@router.post("/create", status_code=201)
def create_project(
    data: ProjectCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.organizer_required),
):
    """POST /api/projects/create — создать проект (UC-10)."""
    project = models.Project(
        title=data.title,
        description=data.description,
        created_by=current_user.id,
        status="active",
    )
    db.add(project)
    db.commit()
    db.refresh(project)

    logger.info(f"[PROJECT] organizer={current_user.email} project={project.id} title={data.title}")

    return {"success": True, "id": project.id, "title": project.title}


@router.post("/tasks/create", status_code=201)
def create_task(
    data: TaskCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.organizer_required),
):
    """POST /api/tasks/create — создать задачу (UC-11)."""
    project = db.query(models.Project).filter(models.Project.id == data.project_id).first()
    if not project:
        raise HTTPException(404, "Проект не найден")

    task = models.Task(
        project_id=data.project_id,
        title=data.title,
        description=data.description,
        event_date=data.event_date,
        location=data.location,
        needed_people=data.needed_people,
        status="open",
    )
    db.add(task)
    db.commit()
    db.refresh(task)

    logger.info(f"[TASK] organizer={current_user.email} task={task.id} project={data.project_id}")

    return {"success": True, "id": task.id, "title": task.title}
