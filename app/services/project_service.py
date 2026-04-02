from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
from app import models
from typing import List, Dict, Any
from datetime import date


def create_project_with_tasks(
        db: Session,
        title: str,
        description: str,
        created_by: int,
        tasks_data: List[Dict[str, Any]]
) -> models.Project:
    """
    Создаёт проект и связанные с ним задачи в одной транзакции.
    Если что-то идёт не так, всё откатывается.
    """
    try:
        new_project = models.Project(
            title=title,
            description=description,
            created_by=created_by,
            status="active"
        )
        db.add(new_project)
        db.flush()

        for task_info in tasks_data:
            task = models.Task(
                project_id=new_project.id,
                title=task_info.get("title"),
                description=task_info.get("description"),
                event_date=task_info.get("event_date"),
                location=task_info.get("location"),
                needed_people=task_info.get("needed_people", 5),
                status="open"
            )
            db.add(task)

        db.commit()
        db.refresh(new_project)

        return new_project

    except SQLAlchemyError as e:
        db.rollback()
        raise Exception(f"Ошибка при создании проекта и задач: {str(e)}")


def create_project_with_single_task(
        db: Session,
        project_title: str,
        project_description: str,
        created_by: int,
        task_title: str,
        task_description: str,
        event_date: date,
        location: str = None
) -> models.Project:
    """
    Упрощённая версия: создаёт проект + одну задачу
    """
    tasks_data = [{
        "title": task_title,
        "description": task_description,
        "event_date": event_date,
        "location": location
    }]

    return create_project_with_tasks(
        db=db,
        title=project_title,
        description=project_description,
        created_by=created_by,
        tasks_data=tasks_data
    )