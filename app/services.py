from sqlalchemy.orm import Session
from fastapi import HTTPException
from app import models
from app.logger import logger
from app.celery_worker import send_notification_task
import uuid


class ApplicationStatus:
    PENDING   = "pending"
    APPROVED  = "approved"
    REJECTED  = "rejected"
    CANCELLED = "cancelled"


ALLOWED_TRANSITIONS: dict[str, list[str]] = {
    ApplicationStatus.PENDING:   [ApplicationStatus.APPROVED, ApplicationStatus.REJECTED],
    ApplicationStatus.APPROVED:  [ApplicationStatus.CANCELLED],
    ApplicationStatus.REJECTED:  [],
    ApplicationStatus.CANCELLED: [],
}


def change_application_status(
    db: Session,
    app_id: int,
    new_status: str,
    current_user: models.User,
) -> models.TaskApplication:
    application = (
        db.query(models.TaskApplication)
        .filter(models.TaskApplication.id == app_id)
        .first()
    )
    if not application:
        raise HTTPException(status_code=404, detail="Заявка не найдена")

    allowed = ALLOWED_TRANSITIONS.get(application.status, [])
    if new_status not in allowed:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Недопустимый переход: '{application.status}' → '{new_status}'. "
                f"Допустимые: {allowed if allowed else 'нет'}"
            ),
        )

    application.status = new_status
    db.commit()
    db.refresh(application)
    return application


def create_project_with_task(
    db: Session,
    creator: models.User,
    project_title: str,
    project_description: str | None,
    task_title: str,
    task_description: str | None,
    event_date: str,
    location: str | None,
    needed_people: int = 5,
) -> dict:
    try:
        project = models.Project(
            title=project_title,
            description=project_description,
            status="active",
            created_by=creator.id,
        )
        db.add(project)
        db.flush()

        task = models.Task(
            project_id=project.id,
            title=task_title,
            description=task_description,
            event_date=event_date,
            location=location,
            needed_people=needed_people,
            status="open",
        )
        db.add(task)

        db.commit()
        db.refresh(project)
        db.refresh(task)

        return {
            "success": True,
            "message": "Проект и первая задача успешно созданы",
            "project": {"id": project.id, "title": project.title},
            "task":    {"id": task.id,    "title": task.title},
        }

    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Ошибка при создании: {exc}")


def register_user(
    db: Session,
    email: str,
    password: str,
    name: str,
    role_code: str = "volunteer",
    phone: str | None = None,
    city: str | None = None,
) -> models.User:
    from app.auth import get_password_hash

    existing = db.query(models.User).filter(models.User.email == email).first()
    if existing:
        raise HTTPException(status_code=409, detail="Пользователь с таким email уже существует")

    role = db.query(models.Role).filter(models.Role.code == role_code).first()
    if not role:
        raise HTTPException(status_code=404, detail=f"Роль '{role_code}' не найдена")

    user = models.User(
        email=email,
        password_hash=get_password_hash(password),
        name=name,
        phone=phone,
        city=city,
        role_id=role.id,
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def login_user(db: Session, email: str, password: str) -> dict:
    from app.auth import authenticate_user, create_access_token

    user = authenticate_user(db, email, password)
    if not user:
        raise HTTPException(
            status_code=401,
            detail="Неверный email или пароль",
            headers={"WWW-Authenticate": "Bearer"},
        )

    access_token = create_access_token(data={"sub": user.email, "user_id": user.id})
    return {"access_token": access_token, "token_type": "bearer"}


def send_notification(user_id: int, message: str):
    """
    Отправка уведомления через Celery (асинхронно)
    """
    task = send_notification_task.delay(user_id, message)
    logger.info(f"[NOTIFICATION_QUEUED] user_id={user_id} message={message} task_id={task.id}")
    return task.id