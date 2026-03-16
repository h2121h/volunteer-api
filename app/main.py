from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime

from app.database import SessionLocal, engine
from app import models
from app.auth import (
    get_password_hash, verify_password, create_access_token,
    get_current_user, get_current_active_user,
    volunteer_required, organizer_required, curator_required, admin_required,
    authenticate_user
)
from app.config import settings

# Создаём таблицы (закомментировано, так как они уже есть)
# models.Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="Волонтёрское API",
    description="API для управления волонтёрскими программами",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ========== ПУБЛИЧНЫЕ ЭНДПОИНТЫ (доступны всем) ==========

@app.get("/")
def root():
    return {"message": "Волонтёрское API работает", "version": "1.0.0"}


@app.get("/api/roles")
def get_roles(db: Session = Depends(get_db)):
    """Получить список всех ролей"""
    roles = db.query(models.Role).all()
    return [
        {
            "id": r.id,
            "code": r.code,
            "name": r.name
        }
        for r in roles
    ]


@app.get("/api/stats")
def get_stats(db: Session = Depends(get_db)):
    """Публичная статистика"""
    volunteers = db.query(models.User).join(models.Role).filter(models.Role.code == "volunteer").count()
    organizers = db.query(models.User).join(models.Role).filter(models.Role.code == "organizer").count()
    curators = db.query(models.User).join(models.Role).filter(models.Role.code == "curator").count()

    tasks_open = db.query(models.Task).filter(models.Task.status == "open").count()
    tasks_completed = db.query(models.Task).filter(models.Task.status == "completed").count()
    projects_count = db.query(models.Project).count()

    return {
        "volunteers_count": volunteers,
        "organizers_count": organizers,
        "curators_count": curators,
        "tasks_open": tasks_open,
        "tasks_completed": tasks_completed,
        "projects_count": projects_count
    }


@app.get("/api/projects")
def get_projects(db: Session = Depends(get_db)):
    """Список проектов (доступно всем)"""
    projects = db.query(models.Project).filter(models.Project.status == "active").all()
    return [
        {
            "id": p.id,
            "name": p.name,
            "description": p.description,
            "status": p.status
        }
        for p in projects
    ]


@app.get("/api/tasks")
def get_tasks(
        db: Session = Depends(get_db),
        status: Optional[str] = None
):
    """Список задач (доступно всем)"""
    query = db.query(models.Task)
    if status:
        query = query.filter(models.Task.status == status)

    tasks = query.all()
    result = []
    for task in tasks:
        creator_name = task.creator.full_name if task.creator else "Неизвестно"
        result.append({
            "id": task.id,
            "title": task.title,
            "description": task.description,
            "location": task.location,
            "status": task.status,
            "created_by": creator_name,
            "created_at": task.created_at,
            "project_id": task.project_id
        })
    return result


# ========== РЕГИСТРАЦИЯ И ВХОД ==========

@app.post("/api/register")
def register(data: dict, db: Session = Depends(get_db)):
    try:
        email = data.get("email")
        password = data.get("password")
        full_name = data.get("full_name", "")
        role_code = data.get("role", "volunteer")  # по умолчанию волонтёр

        if not email or not password:
            return {"success": False, "message": "Email и пароль обязательны"}

        # Проверяем существование пользователя
        existing_user = db.query(models.User).filter(models.User.email == email).first()
        if existing_user:
            return {"success": False, "message": "Пользователь уже существует"}

        # Ищем роль по коду
        role = db.query(models.Role).filter(models.Role.code == role_code).first()
        if not role:
            available_roles = db.query(models.Role).all()
            return {
                "success": False,
                "message": f"Роль '{role_code}' не существует",
                "available_roles": [r.code for r in available_roles]
            }

        # Создаём пользователя
        hashed_password = get_password_hash(password)
        new_user = models.User(
            email=email,
            password_hash=hashed_password,
            full_name=full_name,
            role_id=role.id,
            is_active=True
        )

        db.add(new_user)
        db.commit()
        db.refresh(new_user)

        return {
            "success": True,
            "message": "Регистрация успешна",
            "user": {
                "email": new_user.email,
                "name": new_user.full_name,
                "role": new_user.role.code
            }
        }

    except Exception as e:
        return {"success": False, "message": str(e)}


@app.post("/api/login")
def login(data: dict, db: Session = Depends(get_db)):
    try:
        email = data.get("email")
        password = data.get("password")

        user = authenticate_user(db, email, password)

        if not user:
            return {"success": False, "message": "Неверный email или пароль"}

        access_token = create_access_token(data={"sub": user.email})

        return {
            "success": True,
            "message": "Вход выполнен успешно",
            "token": access_token,
            "user": {
                "id": user.id,
                "email": user.email,
                "name": user.full_name or user.email.split('@')[0],
                "role": user.role.code,
                "role_name": user.role.name
            }
        }

    except Exception as e:
        return {"success": False, "message": str(e)}


@app.get("/api/users/me")
def get_current_user_info(current_user: models.User = Depends(get_current_active_user)):
    """Информация о текущем пользователе"""
    return {
        "id": current_user.id,
        "email": current_user.email,
        "name": current_user.full_name,
        "role": current_user.role.code,
        "role_name": current_user.role.name,
        "is_active": current_user.is_active,
        "created_at": current_user.created_at
    }


# ========== ЭНДПОИНТЫ ДЛЯ ВОЛОНТЁРОВ ==========

@app.post("/api/tasks/{task_id}/apply")
def apply_to_task(
        task_id: int,
        message: Optional[str] = None,
        db: Session = Depends(get_db),
        current_user: models.User = Depends(volunteer_required)
):
    """Волонтёр подаёт заявку на задачу"""
    try:
        task = db.query(models.Task).filter(models.Task.id == task_id).first()
        if not task:
            return {"success": False, "message": "Задача не найдена"}

        # Проверяем, не подавал ли уже заявку
        existing = db.query(models.TaskApplication).filter(
            models.TaskApplication.task_id == task_id,
            models.TaskApplication.user_id == current_user.id
        ).first()

        if existing:
            return {"success": False, "message": "Вы уже подали заявку на эту задачу"}

        application = models.TaskApplication(
            task_id=task_id,
            user_id=current_user.id,
            message=message,
            status="pending"
        )

        db.add(application)
        db.commit()

        return {"success": True, "message": "Заявка отправлена"}

    except Exception as e:
        return {"success": False, "message": str(e)}


@app.get("/api/my-applications")
def get_my_applications(
        db: Session = Depends(get_db),
        current_user: models.User = Depends(volunteer_required)
):
    """Волонтёр смотрит свои заявки"""
    applications = db.query(models.TaskApplication).filter(
        models.TaskApplication.user_id == current_user.id
    ).all()

    return [
        {
            "id": a.id,
            "task_id": a.task_id,
            "task_title": a.task.title if a.task else "Неизвестно",
            "status": a.status,
            "message": a.message,
            "applied_at": a.applied_at
        }
        for a in applications
    ]


@app.post("/api/reports/create")
def create_report(
        data: dict,
        db: Session = Depends(get_db),
        current_user: models.User = Depends(volunteer_required)
):
    """Волонтёр отправляет отчёт о выполненной задаче"""
    try:
        task_id = data.get("task_id")
        content = data.get("content")
        hours_spent = data.get("hours_spent")
        photos = data.get("photos")

        if not task_id or not content:
            return {"success": False, "message": "Необходимо указать задачу и содержание отчёта"}

        # Проверяем, назначена ли задача волонтёру
        assignment = db.query(models.TaskAssignment).filter(
            models.TaskAssignment.task_id == task_id,
            models.TaskAssignment.user_id == current_user.id
        ).first()

        if not assignment:
            return {"success": False, "message": "Эта задача не назначена вам"}

        report = models.TaskReport(
            task_id=task_id,
            user_id=current_user.id,
            content=content,
            hours_spent=hours_spent,
            photos=photos,
            status="submitted"
        )

        db.add(report)
        db.commit()

        return {"success": True, "message": "Отчёт отправлен на проверку"}

    except Exception as e:
        return {"success": False, "message": str(e)}


@app.get("/api/my-reports")
def get_my_reports(
        db: Session = Depends(get_db),
        current_user: models.User = Depends(volunteer_required)
):
    """Волонтёр смотрит свои отчёты"""
    reports = db.query(models.TaskReport).filter(
        models.TaskReport.user_id == current_user.id
    ).all()

    return [
        {
            "id": r.id,
            "task_id": r.task_id,
            "task_title": r.task.title if r.task else "Неизвестно",
            "content": r.content,
            "hours_spent": r.hours_spent,
            "status": r.status,
            "submitted_at": r.submitted_at
        }
        for r in reports
    ]


# ========== ЭНДПОИНТЫ ДЛЯ ОРГАНИЗАТОРОВ ==========

@app.post("/api/projects/create")
def create_project(
        data: dict,
        db: Session = Depends(get_db),
        current_user: models.User = Depends(organizer_required)
):
    """Организатор создаёт проект"""
    try:
        project = models.Project(
            name=data.get("name"),
            description=data.get("description"),
            start_date=data.get("start_date"),
            end_date=data.get("end_date"),
            status="active",
            created_by=current_user.id
        )

        db.add(project)
        db.commit()
        db.refresh(project)

        return {"success": True, "message": "Проект создан", "id": project.id}

    except Exception as e:
        return {"success": False, "message": str(e)}


@app.post("/api/tasks/create")
def create_task(
        data: dict,
        db: Session = Depends(get_db),
        current_user: models.User = Depends(organizer_required)
):
    """Организатор создаёт задачу"""
    try:
        task = models.Task(
            title=data.get("title"),
            description=data.get("description"),
            project_id=data.get("project_id"),
            location=data.get("location"),
            required_skills=data.get("required_skills"),
            start_date=data.get("start_date"),
            end_date=data.get("end_date"),
            status="open",
            created_by=current_user.id
        )

        db.add(task)
        db.commit()
        db.refresh(task)

        return {"success": True, "message": "Задача создана", "id": task.id}

    except Exception as e:
        return {"success": False, "message": str(e)}


@app.put("/api/tasks/{task_id}/edit")
def edit_task(
        task_id: int,
        data: dict,
        db: Session = Depends(get_db),
        current_user: models.User = Depends(organizer_required)
):
    """Организатор редактирует задачу"""
    try:
        task = db.query(models.Task).filter(models.Task.id == task_id).first()
        if not task:
            return {"success": False, "message": "Задача не найдена"}

        # Проверяем, что организатор создал эту задачу
        if task.created_by != current_user.id:
            return {"success": False, "message": "Вы можете редактировать только свои задачи"}

        # Обновляем поля
        if "title" in data:
            task.title = data["title"]
        if "description" in data:
            task.description = data["description"]
        if "location" in data:
            task.location = data["location"]
        if "start_date" in data:
            task.start_date = data["start_date"]
        if "end_date" in data:
            task.end_date = data["end_date"]

        db.commit()

        return {"success": True, "message": "Задача обновлена"}

    except Exception as e:
        return {"success": False, "message": str(e)}


# ========== ЭНДПОИНТЫ ДЛЯ КУРАТОРОВ ==========

@app.get("/api/applications/pending")
def get_pending_applications(
        db: Session = Depends(get_db),
        current_user: models.User = Depends(curator_required)
):
    """Куратор смотрит заявки на задачи"""
    applications = db.query(models.TaskApplication).filter(
        models.TaskApplication.status == "pending"
    ).all()

    return [
        {
            "id": a.id,
            "task_id": a.task_id,
            "task_title": a.task.title if a.task else "Неизвестно",
            "user_id": a.user_id,
            "user_name": a.user.full_name if a.user else "Неизвестно",
            "message": a.message,
            "applied_at": a.applied_at
        }
        for a in applications
    ]


@app.post("/api/applications/{app_id}/approve")
def approve_application(
        app_id: int,
        db: Session = Depends(get_db),
        current_user: models.User = Depends(curator_required)
):
    """Куратор одобряет заявку и назначает волонтёра"""
    try:
        application = db.query(models.TaskApplication).filter(
            models.TaskApplication.id == app_id
        ).first()

        if not application:
            return {"success": False, "message": "Заявка не найдена"}

        # Обновляем статус заявки
        application.status = "approved"

        # Создаём назначение
        assignment = models.TaskAssignment(
            task_id=application.task_id,
            user_id=application.user_id,
            assigned_by=current_user.id,
            status="assigned"
        )

        # Обновляем статус задачи
        task = db.query(models.Task).filter(models.Task.id == application.task_id).first()
        if task:
            task.status = "in_progress"

        db.add(assignment)
        db.commit()

        return {"success": True, "message": "Волонтёр назначен на задачу"}

    except Exception as e:
        return {"success": False, "message": str(e)}


@app.post("/api/applications/{app_id}/reject")
def reject_application(
        app_id: int,
        db: Session = Depends(get_db),
        current_user: models.User = Depends(curator_required)
):
    """Куратор отклоняет заявку"""
    try:
        application = db.query(models.TaskApplication).filter(
            models.TaskApplication.id == app_id
        ).first()

        if not application:
            return {"success": False, "message": "Заявка не найдена"}

        application.status = "rejected"
        db.commit()

        return {"success": True, "message": "Заявка отклонена"}

    except Exception as e:
        return {"success": False, "message": str(e)}


@app.get("/api/reports/pending")
def get_pending_reports(
        db: Session = Depends(get_db),
        current_user: models.User = Depends(curator_required)
):
    """Куратор смотрит отчёты на проверке"""
    reports = db.query(models.TaskReport).filter(
        models.TaskReport.status == "submitted"
    ).all()

    return [
        {
            "id": r.id,
            "task_id": r.task_id,
            "task_title": r.task.title if r.task else "Неизвестно",
            "user_id": r.user_id,
            "user_name": r.user.full_name if r.user else "Неизвестно",
            "content": r.content,
            "hours_spent": r.hours_spent,
            "submitted_at": r.submitted_at
        }
        for r in reports
    ]


@app.post("/api/reports/{report_id}/approve")
def approve_report(
        report_id: int,
        db: Session = Depends(get_db),
        current_user: models.User = Depends(curator_required)
):
    """Куратор одобряет отчёт"""
    try:
        report = db.query(models.TaskReport).filter(
            models.TaskReport.id == report_id
        ).first()

        if not report:
            return {"success": False, "message": "Отчёт не найден"}

        report.status = "approved"
        report.reviewed_at = datetime.utcnow()
        report.reviewed_by = current_user.id

        # Обновляем статус задачи
        task = db.query(models.Task).filter(models.Task.id == report.task_id).first()
        if task:
            task.status = "completed"

        db.commit()

        return {"success": True, "message": "Отчёт одобрен, задача завершена"}

    except Exception as e:
        return {"success": False, "message": str(e)}


@app.post("/api/reports/{report_id}/reject")
def reject_report(
        report_id: int,
        db: Session = Depends(get_db),
        current_user: models.User = Depends(curator_required)
):
    """Куратор отклоняет отчёт"""
    try:
        report = db.query(models.TaskReport).filter(
            models.TaskReport.id == report_id
        ).first()

        if not report:
            return {"success": False, "message": "Отчёт не найден"}

        report.status = "rejected"
        report.reviewed_at = datetime.utcnow()
        report.reviewed_by = current_user.id

        db.commit()

        return {"success": True, "message": "Отчёт отклонён"}

    except Exception as e:
        return {"success": False, "message": str(e)}


# ========== ЭНДПОИНТЫ ДЛЯ АДМИНИСТРАТОРОВ ==========

@app.get("/api/admin/users")
def get_all_users(
        db: Session = Depends(get_db),
        current_user: models.User = Depends(admin_required)
):
    """Админ смотрит всех пользователей"""
    users = db.query(models.User).all()
    return [
        {
            "id": u.id,
            "email": u.email,
            "name": u.full_name,
            "role": u.role.code,
            "role_name": u.role.name,
            "is_active": u.is_active,
            "created_at": u.created_at
        }
        for u in users
    ]


@app.post("/api/admin/users/{user_id}/toggle-active")
def toggle_user_active(
        user_id: int,
        db: Session = Depends(get_db),
        current_user: models.User = Depends(admin_required)
):
    """Админ активирует/деактивирует пользователя"""
    try:
        user = db.query(models.User).filter(models.User.id == user_id).first()
        if not user:
            return {"success": False, "message": "Пользователь не найден"}

        user.is_active = not user.is_active
        db.commit()

        status = "активирован" if user.is_active else "деактивирован"
        return {"success": True, "message": f"Пользователь {status}"}

    except Exception as e:
        return {"success": False, "message": str(e)}


@app.post("/api/admin/users/{user_id}/change-role")
def change_user_role(
        user_id: int,
        data: dict,
        db: Session = Depends(get_db),
        current_user: models.User = Depends(admin_required)
):
    """Админ меняет роль пользователя"""
    try:
        user = db.query(models.User).filter(models.User.id == user_id).first()
        if not user:
            return {"success": False, "message": "Пользователь не найден"}

        role_code = data.get("role")
        role = db.query(models.Role).filter(models.Role.code == role_code).first()
        if not role:
            return {"success": False, "message": "Роль не найдена"}

        user.role_id = role.id
        db.commit()

        return {"success": True, "message": f"Роль изменена на {role.name}"}

    except Exception as e:
        return {"success": False, "message": str(e)}


@app.get("/api/admin/stats")
def admin_stats(
        db: Session = Depends(get_db),
        current_user: models.User = Depends(admin_required)
):
    """Детальная статистика для админа"""
    total_users = db.query(models.User).count()
    active_users = db.query(models.User).filter(models.User.is_active == True).count()

    roles_stats = {}
    roles = db.query(models.Role).all()
    for role in roles:
        count = db.query(models.User).filter(models.User.role_id == role.id).count()
        roles_stats[role.code] = count

    tasks_by_status = {
        "open": db.query(models.Task).filter(models.Task.status == "open").count(),
        "in_progress": db.query(models.Task).filter(models.Task.status == "in_progress").count(),
        "completed": db.query(models.Task).filter(models.Task.status == "completed").count(),
        "cancelled": db.query(models.Task).filter(models.Task.status == "cancelled").count()
    }

    return {
        "total_users": total_users,
        "active_users": active_users,
        "roles": roles_stats,
        "tasks": tasks_by_status,
        "projects": db.query(models.Project).count(),
        "reports_pending": db.query(models.TaskReport).filter(models.TaskReport.status == "submitted").count()
    }


# ========== ДОПОЛНИТЕЛЬНЫЕ ЭНДПОИНТЫ ==========

@app.get("/api/health")
def health():
    return {"status": "healthy"}