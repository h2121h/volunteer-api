from fastapi import FastAPI, Depends, UploadFile, File, Form, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from typing import Optional
from datetime import datetime, timedelta
import os
import uuid
import time

from app.database import SessionLocal, engine
from app import models, schemas
from app.config import settings
from app.auth import (
    get_password_hash, authenticate_user, create_access_token,
    get_current_user, get_current_active_user,
    volunteer_required, organizer_required, curator_required, admin_required,
    decode_token, get_user_by_email
)
from app.logger import logger
from pydantic import BaseModel

app = FastAPI(
    title="Волонтёрское API",
    description="API для управления волонтёрскими программами",
    version="2.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    start_time = time.time()
    response   = await call_next(request)
    duration   = time.time() - start_time
    logger.info(
        f"{request.method} {request.url.path} - "
        f"Status: {response.status_code} - Duration: {duration:.3f}s"
    )
    return response


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ── Существующие роутеры ──────────────────────────────────────────────────────
# Пробуем оба варианта названия папки роутеров
try:
    from app.routers import (
        applications_router, auth_router, projects_router,
        checkins, tasks_extra, reports_router,
        projects_api, admin, stats,
    )
except ModuleNotFoundError:
    import importlib
    _r = "app.маршрутизаторы"
    applications_router = importlib.import_module(f"{_r}.applications_router")
    auth_router         = importlib.import_module(f"{_r}.auth_router")
    projects_router     = importlib.import_module(f"{_r}.projects_router")
    checkins            = importlib.import_module(f"{_r}.checkins")
    tasks_extra         = importlib.import_module(f"{_r}.tasks_extra")
    reports_router      = importlib.import_module(f"{_r}.reports_router")
    projects_api        = importlib.import_module(f"{_r}.projects_api")
    admin               = importlib.import_module(f"{_r}.admin")
    stats               = importlib.import_module(f"{_r}.stats")

app.include_router(applications_router.router)
app.include_router(auth_router.router)
app.include_router(projects_router.router)
app.include_router(checkins.router)
app.include_router(tasks_extra.router)
app.include_router(reports_router.router)
app.include_router(projects_api.router)
app.include_router(admin.router)
app.include_router(stats.router)

# ── BFF роутеры ───────────────────────────────────────────────────────────────
from app import bff_desktop, bff_web, bff_mobile

app.include_router(bff_desktop.router)   # GET /bff/desktop/*
app.include_router(bff_web.router)       # GET /bff/web/*

# bff_mobile может быть и в routers/ и в app/
try:
    from app.routers import bff_mobile as bff_mobile_router
    app.include_router(bff_mobile_router.router)  # GET /bff/mobile/*
except ImportError:
    app.include_router(bff_mobile.router)

# ── CQRS роутеры ──────────────────────────────────────────────────────────────
try:
    from app.routers import cqrs_commands, cqrs_queries
    app.include_router(cqrs_commands.router)   # POST /cmd/*
    app.include_router(cqrs_queries.router)    # GET  /query/*
except ImportError:
    from app import cqrs_commands, cqrs_queries
    app.include_router(cqrs_commands.router)
    app.include_router(cqrs_queries.router)

# ── Hotspot Metrics ───────────────────────────────────────────────────────────
try:
    from app import hotspot_metrics
    app.include_router(hotspot_metrics.router)  # GET /metrics/*
except Exception:
    pass  # Redis может быть недоступен — не падаем

# ── Domain Events subscriber (запускается при старте) ─────────────────────────
@app.on_event("startup")
async def startup():
    try:
        from app.domain_events import subscriber
        subscriber.start()
        logger.info("[APP] Domain Event subscriber started")
    except Exception as e:
        logger.warning(f"[APP] Domain Events unavailable: {e}")


# ── Base endpoints ────────────────────────────────────────────────────────────

@app.get("/")
def root():
    return {"message": "Волонтёрское API работает", "version": "2.0.0"}


@app.get("/health")
def health():
    return {"status": "healthy"}


@app.get("/api/roles")
def get_roles(db: Session = Depends(get_db)):
    roles = db.query(models.Role).all()
    return [{"id": r.id, "code": r.code, "name": r.name} for r in roles]


@app.get("/api/stats")
def get_stats(db: Session = Depends(get_db)):
    volunteers      = db.query(models.User).join(models.Role).filter(models.Role.code == "volunteer").count()
    organizers      = db.query(models.User).join(models.Role).filter(models.Role.code == "organizer").count()
    curators        = db.query(models.User).join(models.Role).filter(models.Role.code == "curator").count()
    tasks_open      = db.query(models.Task).filter(models.Task.status == "open").count()
    tasks_completed = db.query(models.TaskReport).filter(models.TaskReport.is_approved == True).count()
    projects_count  = db.query(models.Project).count()
    return {
        "volunteers_count": volunteers,
        "organizers_count": organizers,
        "curators_count":   curators,
        "tasks_open":       tasks_open,
        "tasks_completed":  tasks_completed,
        "projects_count":   projects_count,
    }


@app.get("/api/projects")
def get_projects(db: Session = Depends(get_db)):
    projects = db.query(models.Project).filter(models.Project.status == "active").all()
    return [{"id": p.id, "title": p.title, "description": p.description, "status": p.status}
            for p in projects]


@app.get("/api/tasks")
def get_tasks(db: Session = Depends(get_db), status: Optional[str] = None):
    query = db.query(models.Task)
    if status:
        query = query.filter(models.Task.status == status)
    tasks = query.all()
    return [{
        "id": t.id, "title": t.title, "description": t.description,
        "location": t.location, "event_date": t.event_date,
        "needed_people": t.needed_people, "status": t.status, "project_id": t.project_id
    } for t in tasks]


@app.post("/api/register")
def register(data: dict, db: Session = Depends(get_db)):
    try:
        email     = data.get("email")
        password  = data.get("password")
        name      = data.get("name", email.split('@')[0])
        phone     = data.get("phone", None)
        city      = data.get("city", None)
        role_code = data.get("role", "volunteer")
        if not email or not password:
            return {"success": False, "message": "Email и пароль обязательны"}
        existing_user = db.query(models.User).filter(models.User.email == email).first()
        if existing_user:
            return {"success": False, "message": "Пользователь уже существует"}
        role = db.query(models.Role).filter(models.Role.code == role_code).first()
        if not role:
            available_roles = db.query(models.Role).all()
            return {"success": False, "message": f"Роль '{role_code}' не существует",
                    "available_roles": [r.code for r in available_roles]}
        hashed_password = get_password_hash(password)
        new_user = models.User(
            email=email, password_hash=hashed_password, name=name,
            phone=phone, city=city, role_id=role.id, is_active=True
        )
        db.add(new_user)
        db.commit()
        db.refresh(new_user)
        return {"success": True, "message": "Регистрация успешна",
                "user": {"email": new_user.email, "name": new_user.name, "role": new_user.role.code}}
    except Exception as e:
        return {"success": False, "message": str(e)}


@app.post("/api/login")
def login(data: dict, db: Session = Depends(get_db)):
    try:
        email    = data.get("email")
        password = data.get("password")
        user     = authenticate_user(db, email, password)
        if not user:
            return {"success": False, "message": "Неверный email или пароль"}
        access_token = create_access_token(data={"sub": user.email})
        return {
            "success": True, "message": "Вход выполнен успешно",
            "token": access_token, "access_token": access_token,
            "user": {
                "id": user.id, "email": user.email,
                "name": user.name or user.email.split('@')[0],
                "role": user.role.code, "role_name": user.role.name,
            }
        }
    except Exception as e:
        return {"success": False, "message": str(e)}


@app.get("/api/users/me")
def get_current_user_info(current_user: models.User = Depends(get_current_active_user)):
    return {
        "id": current_user.id, "email": current_user.email, "name": current_user.name,
        "city": getattr(current_user, 'city', None),
        "role": current_user.role.code, "role_name": current_user.role.name,
        "is_active": current_user.is_active, "created_at": current_user.created_at,
    }


@app.post("/api/tasks/{task_id}/apply")
def apply_to_task(
    task_id: int, message: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(volunteer_required)
):
    try:
        task = db.query(models.Task).filter(models.Task.id == task_id).first()
        if not task:
            return {"success": False, "message": "Задача не найдена"}
        existing = db.query(models.TaskApplication).filter(
            models.TaskApplication.task_id == task_id,
            models.TaskApplication.user_id == current_user.id
        ).first()
        if existing:
            return {"success": False, "message": "Вы уже подали заявку на эту задачу"}
        application = models.TaskApplication(
            task_id=task_id, user_id=current_user.id, message=message, status="pending"
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
    applications = db.query(models.TaskApplication).filter(
        models.TaskApplication.user_id == current_user.id).all()
    return [{
        "id": a.id, "task_id": a.task_id,
        "task_title": a.task.title if a.task else "Неизвестно",
        "status": a.status, "message": a.message, "applied_at": a.applied_at
    } for a in applications]


@app.post("/api/reports/create")
def create_report(
    data: dict,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(volunteer_required)
):
    try:
        task_id   = data.get("task_id")
        comment   = data.get("comment")
        hours     = data.get("hours")
        photo_url = data.get("photo_url")
        if not task_id or not comment:
            return {"success": False, "message": "Необходимо указать задачу и содержание отчёта"}
        assignment = db.query(models.TaskAssignment).filter(
            models.TaskAssignment.task_id == task_id,
            models.TaskAssignment.user_id == current_user.id
        ).first()
        if not assignment:
            return {"success": False, "message": "Эта задача не назначена вам"}
        report = models.TaskReport(
            assignment_id=assignment.id, user_id=current_user.id, comment=comment,
            hours=hours, photo_url=photo_url, is_approved=False
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
    reports = db.query(models.TaskReport).filter(
        models.TaskReport.user_id == current_user.id).all()
    return [{
        "id": r.id, "assignment_id": r.assignment_id, "comment": r.comment,
        "hours": r.hours, "photo_url": r.photo_url,
        "is_approved": r.is_approved, "submitted_at": r.submitted_at
    } for r in reports]


@app.post("/api/projects/create")
def create_project(
    data: dict,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(organizer_required)
):
    try:
        project = models.Project(
            title=data.get("title"), description=data.get("description"),
            status="active", created_by=current_user.id
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
    try:
        task = models.Task(
            title=data.get("title"), description=data.get("description"),
            project_id=data.get("project_id"), event_date=data.get("event_date"),
            location=data.get("location"), needed_people=data.get("needed_people", 5),
            status="open"
        )
        db.add(task)
        db.commit()
        db.refresh(task)
        return {"success": True, "message": "Задача создана", "id": task.id}
    except Exception as e:
        return {"success": False, "message": str(e)}


@app.put("/api/tasks/{task_id}/edit")
def edit_task(
    task_id: int, data: dict,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(organizer_required)
):
    try:
        task = db.query(models.Task).filter(models.Task.id == task_id).first()
        if not task:
            return {"success": False, "message": "Задача не найдена"}
        # BR-10: запрет редактирования если есть записавшиеся
        applicants = db.query(models.TaskApplication).filter(
            models.TaskApplication.task_id == task_id,
            models.TaskApplication.status.in_(["pending", "approved"])
        ).count()
        if applicants > 0:
            return {"success": False,
                    "message": f"BR-10: нельзя редактировать — {applicants} волонтёр(ов) уже записалось"}
        for field in ("title", "description", "event_date", "location", "needed_people"):
            if field in data:
                setattr(task, field, data[field])
        db.commit()
        return {"success": True, "message": "Задача обновлена"}
    except Exception as e:
        return {"success": False, "message": str(e)}


@app.get("/api/applications/pending")
def get_pending_applications(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(curator_required)
):
    applications = db.query(models.TaskApplication).filter(
        models.TaskApplication.status == "pending").all()
    return [{
        "id": a.id, "task_id": a.task_id,
        "task_title": a.task.title if a.task else "Неизвестно",
        "user_id": a.user_id,
        "user_name": a.user.name if a.user else "Неизвестно",
        "message": a.message, "applied_at": a.applied_at
    } for a in applications]


@app.post("/api/applications/{app_id}/approve")
def approve_application(
    app_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(curator_required)
):
    try:
        application = db.query(models.TaskApplication).filter(
            models.TaskApplication.id == app_id).first()
        if not application:
            return {"success": False, "message": "Заявка не найдена"}
        application.status = "approved"
        assignment = models.TaskAssignment(
            task_id=application.task_id, user_id=application.user_id,
            assigned_by=current_user.id, status="assigned"
        )
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
    try:
        application = db.query(models.TaskApplication).filter(
            models.TaskApplication.id == app_id).first()
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
    reports = db.query(models.TaskReport).filter(
        models.TaskReport.is_approved == False).all()
    return [{
        "id": r.id, "assignment_id": r.assignment_id,
        "user_id": r.user_id,
        "user_name": r.user.name if r.user else "Неизвестно",
        "comment": r.comment, "hours": r.hours,
        "photo_url": r.photo_url, "submitted_at": r.submitted_at
    } for r in reports]


@app.post("/api/reports/{report_id}/approve")
def approve_report(
    report_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(curator_required)
):
    try:
        report = db.query(models.TaskReport).filter(
            models.TaskReport.id == report_id).first()
        if not report:
            return {"success": False, "message": "Отчёт не найден"}
        report.is_approved = True
        assignment = db.query(models.TaskAssignment).filter(
            models.TaskAssignment.id == report.assignment_id).first()
        if assignment:
            task = db.query(models.Task).filter(
                models.Task.id == assignment.task_id).first()
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
    try:
        report = db.query(models.TaskReport).filter(
            models.TaskReport.id == report_id).first()
        if not report:
            return {"success": False, "message": "Отчёт не найден"}
        db.delete(report)
        db.commit()
        return {"success": True, "message": "Отчёт отклонён"}
    except Exception as e:
        return {"success": False, "message": str(e)}


@app.get("/api/admin/users")
def get_all_users(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(admin_required)
):
    users = db.query(models.User).all()
    return [{
        "id": u.id, "email": u.email, "name": u.name,
        "city": getattr(u, 'city', None),
        "role": u.role.code, "role_name": u.role.name,
        "is_active": u.is_active, "created_at": u.created_at
    } for u in users]


@app.post("/api/admin/users/{user_id}/toggle-active")
def toggle_user_active(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(admin_required)
):
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
    user_id: int, data: dict,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(admin_required)
):
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
    from sqlalchemy import func
    total_users  = db.query(models.User).count()
    active_users = db.query(models.User).filter(models.User.is_active == True).count()
    roles_stats  = {}
    for role in db.query(models.Role).all():
        roles_stats[role.code] = db.query(models.User).filter(
            models.User.role_id == role.id).count()
    return {
        "total_users": total_users, "active_users": active_users,
        "roles": roles_stats,
        "tasks": {
            "open":        db.query(models.Task).filter(models.Task.status == "open").count(),
            "in_progress": db.query(models.Task).filter(models.Task.status == "in_progress").count(),
            "completed":   db.query(models.Task).filter(models.Task.status == "completed").count(),
        },
        "projects":        db.query(models.Project).count(),
        "reports_pending": db.query(models.TaskReport).filter(
            models.TaskReport.is_approved == False).count(),
    }


@app.post("/auth/refresh", response_model=schemas.Token)
def refresh_token(refresh_token: str, db: Session = Depends(get_db)):
    try:
        payload = decode_token(refresh_token)
        if not payload:
            raise HTTPException(status_code=401, detail="Invalid refresh token")
        user = get_user_by_email(db, payload.get("sub"))
        if not user or not user.is_active:
            raise HTTPException(status_code=401, detail="Invalid refresh token")
        new_access = create_access_token(
            data={"sub": user.email},
            expires_delta=timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
        )
        return {"access_token": new_access, "token_type": "bearer"}
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid refresh token")


UPLOAD_DIR = "media/documents"
os.makedirs(UPLOAD_DIR, exist_ok=True)


@app.post("/documents/upload")
async def upload_document(
    doc_type: str, file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(volunteer_required)
):
    allowed_extensions = ('.pdf', '.jpg', '.jpeg', '.png')
    if not any(file.filename.lower().endswith(ext) for ext in allowed_extensions):
        raise HTTPException(400, "Only PDF/JPG/PNG allowed")
    ext      = os.path.splitext(file.filename)[1].lower()
    filename = f"{current_user.id}_{uuid.uuid4().hex}{ext}"
    filepath = os.path.join(UPLOAD_DIR, filename)
    content  = await file.read()
    with open(filepath, "wb") as f:
        f.write(content)
    doc = models.VolunteerDocument(
        user_id=current_user.id, doc_type=doc_type,
        file_url=f"/media/documents/{filename}", status="new"
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)
    return {"success": True, "id": doc.id, "file_url": doc.file_url}


@app.post("/documents/{doc_id}/verify")
def verify_document(
    doc_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(curator_required)
):
    doc = db.query(models.VolunteerDocument).filter(
        models.VolunteerDocument.id == doc_id).first()
    if not doc:
        raise HTTPException(404, "Document not found")
    doc.status      = "verified"
    doc.verified_at = datetime.utcnow()
    doc.verified_by = current_user.id
    db.commit()
    return {"success": True, "message": "Документ верифицирован"}


@app.get("/analytics/summary")
def get_analytics_summary(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(curator_required)
):
    from sqlalchemy import func
    avg_hours = db.query(func.avg(models.TaskReport.hours)).filter(
        models.TaskReport.is_approved == True).scalar() or 0
    total_hours = db.query(func.sum(models.TaskReport.hours)).filter(
        models.TaskReport.is_approved == True).scalar() or 0
    return {
        "total_volunteers":   db.query(models.User).join(models.Role).filter(
            models.Role.code == "volunteer").count(),
        "active_tasks":       db.query(models.Task).filter(
            models.Task.status == "open").count(),
        "completed_reports":  db.query(models.TaskReport).filter(
            models.TaskReport.is_approved == True).count(),
        "pending_reports":    db.query(models.TaskReport).filter(
            models.TaskReport.is_approved == False).count(),
        "avg_hours_per_task": round(float(avg_hours), 2),
        "total_hours":        round(float(total_hours), 1),
    }


class FeedbackCreate(BaseModel):
    rating:  int
    comment: str


@app.post("/projects/{project_id}/feedback")
def create_feedback(
    project_id: int, feedback: FeedbackCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(volunteer_required)
):
    project = db.query(models.Project).filter(models.Project.id == project_id).first()
    if not project:
        raise HTTPException(404, "Project not found")
    fb = models.ProjectFeedback(
        project_id=project_id, user_id=current_user.id,
        rating=feedback.rating, comment=feedback.comment
    )
    db.add(fb)
    db.commit()
    return {"success": True, "message": "Отзыв добавлен"}


@app.post("/tasks/{task_id}/assign/{user_id}")
def direct_assign(
    task_id: int, user_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(curator_required)
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
        task_id=task_id, user_id=user_id,
        assigned_by=current_user.id, status="assigned"
    )
    db.add(assignment)
    db.commit()
    return {"success": True, "message": "Волонтёр назначен напрямую"}


REPORTS_UPLOAD_DIR = "media/reports"
os.makedirs(REPORTS_UPLOAD_DIR, exist_ok=True)


@app.post("/reports/")
async def create_report_with_photos(
    task_id: int = Form(...), comment: str = Form(...), hours: float = Form(...),
    photos: list[UploadFile] = File(None),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(volunteer_required)
):
    assignment = db.query(models.TaskAssignment).filter(
        models.TaskAssignment.task_id == task_id,
        models.TaskAssignment.user_id == current_user.id
    ).first()
    if not assignment:
        raise HTTPException(403, "Вы не назначены на эту задачу")
    photo_urls = []
    if photos:
        for photo in photos:
            ext      = os.path.splitext(photo.filename)[1].lower()
            filename = f"report_{task_id}_{uuid.uuid4().hex}{ext}"
            path     = os.path.join(REPORTS_UPLOAD_DIR, filename)
            content  = await photo.read()
            with open(path, "wb") as f:
                f.write(content)
            photo_urls.append(f"/media/reports/{filename}")
    report = models.TaskReport(
        assignment_id=assignment.id, user_id=current_user.id, comment=comment,
        hours=hours, photo_url=",".join(photo_urls) if photo_urls else None,
        is_approved=False
    )
    db.add(report)
    db.commit()
    return {"success": True, "id": report.id, "message": "Отчёт отправлен"}
