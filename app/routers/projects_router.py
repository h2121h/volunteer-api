from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional

from app.database import get_db
from app import models
from app.auth import organizer_required
from app.services import create_project_with_task

router = APIRouter(prefix="/projects", tags=["projects"])


class ProjectWithTaskRequest(BaseModel):
    project_title: str
    project_description: Optional[str] = None
    task_title: str
    task_description: Optional[str] = None
    event_date: str
    location: Optional[str] = None
    needed_people: int = 5


@router.post("/create-with-task", status_code=201)
def create_project_and_task(
    data: ProjectWithTaskRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(organizer_required),
):
    return create_project_with_task(
        db=db,
        creator=current_user,
        project_title=data.project_title,
        project_description=data.project_description,
        task_title=data.task_title,
        task_description=data.task_description,
        event_date=data.event_date,
        location=data.location,
        needed_people=data.needed_people,
    )