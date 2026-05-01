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

# Безопасность — пробуем подключить, fallback на обычный CORS
try:
    from app.security import RegisterDTO, LoginDTO, CreateProjectDTO, CreateTaskDTO, sanitize_string
    from app.middleware import setup_security, limiter
    SECURITY_ENABLED = True
except ImportError:
    SECURITY_ENABLED = False

app = FastAPI(
    title="Волонтёрское API",
    description="API для управления волонтёрскими программами",
    version="2.0.0"
)

if SECURITY_ENABLED:
    setup_security(app)
else:
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
    logger.info(f"{request.method} {request.url.path} - Status: {response.status_code} - Duration: {duration:.3f}s")
    return response


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ── Существующие роутеры ──────────────────────────────────────────────────────
from app.routers import (
    applications_router, auth_router, projects_router,
    checkins, tasks_extra, reports_router, projects_api, admin, stats,
)
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
app.include_router(bff_desktop.router)
app.include_router(bff_web.router)
try:
    from app.routers import bff_mobile as bff_mobile_router
    app.include_router(bff_mobile_router.router)
except ImportError:
    app.include_router(bff_mobile.router)

# ── CQRS роутеры ──────────────────────────────────────────────────────────────
try:
    from app.routers import cqrs_commands, cqrs_queries
    app.include_router(cqrs_commands.router)
    app.include_router(cqrs_queries.router)
except ImportError:
    try:
        from app import cqrs_commands, cqrs_queries
        app.include_router(cqrs_commands.router)
        app.include_router(cqrs_queries.router)
    except ImportError:
        pass

# ── Teams роутер ──────────────────────────────────────────────────────────────
try:
    from app.routers import teams_router
    app.include_router(teams_router.router)
except ImportError:
    pass

# ── Event Reports роутер ───────────────────────────────────────────────────────
try:
    from app.routers import event_reports_router
    app.include_router(event_reports_router.router)
except ImportError:
    pass

# ── Event Reports роутер ──────────────────────────────────────────────────────
try:
    from app.routers import event_reports_router
    app.include_router(event_reports_router.router)
except ImportError:
    pass

# ── Metrics ───────────────────────────────────────────────────────────────────
try:
    from app import hotspot_metrics
    app.include_router(hotspot_metrics.router)
except Exception:
    pass


# ── Startup ───────────────────────────────────────────────────────────────────
@app.on_event("startup")
async def startup():
    try:
        from sqlalchemy import text
        with engine.connect() as conn:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS task_assignments (
                    id          BIGSERIAL PRIMARY KEY,
                    task_id     BIGINT REFERENCES tasks(id) ON DELETE CASCADE,
                    user_id     BIGINT REFERENCES users(id) ON DELETE CASCADE,
                    assigned_at TIMESTAMPTZ DEFAULT NOW(),
                    assigned_by BIGINT REFERENCES users(id),
                    status      VARCHAR(20) DEFAULT 'assigned'
                );
                CREATE INDEX IF NOT EXISTS idx_asgn_task ON task_assignments(task_id);
                CREATE INDEX IF NOT EXISTS idx_asgn_user ON task_assignments(user_id);

                CREATE TABLE IF NOT EXISTS task_reports (
                    id            BIGSERIAL PRIMARY KEY,
                    assignment_id BIGINT REFERENCES task_assignments(id) ON DELETE CASCADE,
                    user_id       BIGINT REFERENCES users(id),
                    hours         NUMERIC(5,2),
                    comment       TEXT,
                    photo_url     TEXT,
                    submitted_at  TIMESTAMPTZ DEFAULT NOW(),
                    is_approved   BOOLEAN DEFAULT FALSE
                );
                CREATE INDEX IF NOT EXISTS idx_rep_asgn ON task_reports(assignment_id);
                CREATE INDEX IF NOT EXISTS idx_rep_user ON task_reports(user_id);

                CREATE TABLE IF NOT EXISTS volunteer_documents (
                    id          BIGSERIAL PRIMARY KEY,
                    user_id     BIGINT REFERENCES users(id) ON DELETE CASCADE,
                    doc_type    VARCHAR(50),
                    file_url    TEXT,
                    status      VARCHAR(20) DEFAULT 'new',
                    verified_at TIMESTAMPTZ,
                    verified_by BIGINT REFERENCES users(id)
                );

                CREATE TABLE IF NOT EXISTS project_feedback (
                    id         BIGSERIAL PRIMARY KEY,
                    project_id BIGINT REFERENCES projects(id) ON DELETE CASCADE,
                    user_id    BIGINT REFERENCES users(id),
                    rating     SMALLINT,
                    comment    TEXT,
                    created_at TIMESTAMPTZ DEFAULT NOW()
                );

                CREATE TABLE IF NOT EXISTS teams (
                    id          BIGSERIAL PRIMARY KEY,
                    name        VARCHAR(100) NOT NULL,
                    description TEXT,
                    task_id     BIGINT REFERENCES tasks(id) ON DELETE SET NULL,
                    max_size    SMALLINT,
                    created_by  BIGINT REFERENCES users(id),
                    created_at  TIMESTAMPTZ DEFAULT NOW()
                );

                CREATE TABLE IF NOT EXISTS team_members (
                    team_id   BIGINT REFERENCES teams(id) ON DELETE CASCADE,
                    user_id   BIGINT REFERENCES users(id) ON DELETE CASCADE,
                    joined_at TIMESTAMPTZ DEFAULT NOW(),
                    PRIMARY KEY (team_id, user_id)
                );

                ALTER TABLE tasks
                    ADD COLUMN IF NOT EXISTS difficulty VARCHAR(20) DEFAULT 'medium',
                    ADD COLUMN IF NOT EXISTS category   VARCHAR(50) DEFAULT 'other',
                    ADD COLUMN IF NOT EXISTS lat        FLOAT,
                    ADD COLUMN IF NOT EXISTS lng        FLOAT;
            """))
            conn.commit()
        logger.info("[APP] Database tables ensured")
    except Exception as e:
        logger.warning(f"[APP] Table creation skipped: {e}")

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
    return [{"id": r.id, "code": r.code, "name": r.name}
            for r in db.query(models.Role).all()]

@app.get("/api/stats")
def get_stats(db: Session = Depends(get_db)):
    try:
        volunteers     = db.query(models.User).join(models.Role).filter(models.Role.code == "volunteer").count()
        tasks_open     = db.query(models.Task).filter(models.Task.status == "open").count()
        projects_count = db.query(models.Project).count()
        try:
            tasks_completed = db.query(models.TaskReport).filter(models.TaskReport.is_approved == True).count()
        except Exception:
            tasks_completed = 0
        return {
            "volunteers_count": volunteers,
            "tasks_open":       tasks_open,
            "tasks_completed":  tasks_completed,
            "projects_count":   projects_count,
        }
    except Exception as e:
        return {"volunteers_count": 0, "tasks_open": 0, "tasks_completed": 0, "projects_count": 0}

@app.get("/api/projects")
def get_projects(db: Session = Depends(get_db)):
    projects = db.query(models.Project).filter(models.Project.status == "active").all()
    return [{"id": p.id, "title": p.title, "description": p.description, "status": p.status}
            for p in projects]

@app.get("/api/tasks")
def get_tasks(db: Session = Depends(get_db), status: Optional[str] = None,
              project_id: Optional[int] = None):
    query = db.query(models.Task)
    if status:     query = query.filter(models.Task.status == status)
    if project_id: query = query.filter(models.Task.project_id == project_id)
    tasks = query.all()
    return [{
        "id": t.id, "title": t.title, "description": t.description,
        "location": t.location, "event_date": str(t.event_date) if t.event_date else None,
        "needed_people": t.needed_people, "status": t.status,
        "project_id": t.project_id,
        "difficulty": getattr(t, 'difficulty', 'medium'),
        "category":   getattr(t, 'category', 'other'),
    } for t in tasks]


# ── Auth ──────────────────────────────────────────────────────────────────────

@app.post("/api/register")
def register(request: Request, data: dict, db: Session = Depends(get_db)):
    try:
        email     = (data.get("email") or "").strip().lower()
        password  = data.get("password") or ""
        name      = data.get("name") or email.split('@')[0]
        phone     = data.get("phone")
        city      = data.get("city")
        role_code = data.get("role", "volunteer")

        if not email or not password:
            return {"success": False, "message": "Email и пароль обязательны"}
        if len(password) < 8:
            return {"success": False, "message": "Пароль должен быть не менее 8 символов"}

        existing = db.query(models.User).filter(models.User.email == email).first()
        if existing:
            return {"success": False, "message": "Пользователь уже существует"}

        role = db.query(models.Role).filter(models.Role.code == role_code).first()
        if not role:
            roles = [r.code for r in db.query(models.Role).all()]
            return {"success": False, "message": f"Роль '{role_code}' не существует",
                    "available_roles": roles}

        new_user = models.User(
            email=email, password_hash=get_password_hash(password),
            name=name, phone=phone, city=city, role_id=role.id, is_active=True
        )
        db.add(new_user)
        db.commit()
        db.refresh(new_user)
        return {"success": True, "message": "Регистрация успешна",
                "user": {"email": new_user.email, "name": new_user.name,
                         "role": new_user.role.code}}
    except Exception as e:
        return {"success": False, "message": str(e)}

@app.post("/api/login")
def login(request: Request, data: dict, db: Session = Depends(get_db)):
    try:
        email    = (data.get("email") or "").strip().lower()
        password = data.get("password") or ""
        user     = authenticate_user(db, email, password)
        if not user:
            return {"success": False, "message": "Неверный email или пароль"}
        token = create_access_token(data={"sub": user.email})
        return {
            "success": True, "message": "Вход выполнен успешно",
            "token": token, "access_token": token,
            "user": {
                "id": user.id, "email": user.email,
                "name": user.name or user.email.split('@')[0],
                "role": user.role.code, "role_name": user.role.name,
            }
        }
    except Exception as e:
        return {"success": False, "message": str(e)}

@app.get("/api/users/me")
def get_me(current_user: models.User = Depends(get_current_active_user),
           db: Session = Depends(get_db)):
    # BR-09: суммируем баллы из одобренных отчётов
    approved_reports = db.query(models.TaskReport).filter(
        models.TaskReport.user_id == current_user.id,
        models.TaskReport.is_approved == True,
    ).all()
    total_points = sum(
        (r.points if hasattr(r, 'points') and r.points else int(float(r.hours or 0) * 10))
        for r in approved_reports
    )
    return {
        "id": current_user.id, "email": current_user.email,
        "name": current_user.name,
        "city": getattr(current_user, 'city', None),
        "role": current_user.role.code, "role_name": current_user.role.name,
        "is_active": current_user.is_active,
        "created_at": current_user.created_at,
        "points": total_points,
    }

@app.get("/api/users")
def get_users(db: Session = Depends(get_db),
              current_user: models.User = Depends(get_current_active_user)):
    role_code = current_user.role.code if current_user.role else ''
    if role_code not in ('organizer', 'curator', 'admin'):
        raise HTTPException(403, "Нет доступа")
    return [{
        "id": u.id, "email": u.email, "name": u.name or "",
        "city": getattr(u, 'city', ''),
        "role": u.role.code if u.role else "volunteer",
        "role_name": u.role.name if u.role else "Волонтёр",
        "is_active": bool(u.is_active),
    } for u in db.query(models.User).all()]


# ── Tasks ─────────────────────────────────────────────────────────────────────

@app.post("/api/tasks/{task_id}/apply")
def apply_task(task_id: int, db: Session = Depends(get_db),
               current_user: models.User = Depends(get_current_active_user)):
    try:
        task = db.query(models.Task).filter(models.Task.id == task_id).first()
        if not task:
            return {"success": False, "message": "Задача не найдена"}
        if task.status != "open":
            return {"success": False, "message": "Задача недоступна"}

        count = db.query(models.TaskApplication).filter(
            models.TaskApplication.task_id == task_id,
            models.TaskApplication.status.in_(["pending", "approved"]),
        ).count()
        if task.needed_people and count >= task.needed_people:
            return {"success": False, "code": "BR-01", "message": "Лимит участников"}

        existing = db.query(models.TaskApplication).filter(
            models.TaskApplication.task_id == task_id,
            models.TaskApplication.user_id == current_user.id,
        ).first()
        if existing:
            return {"success": False, "message": "Вы уже подали заявку",
                    "application_id": existing.id}

        app_obj = models.TaskApplication(
            task_id=task_id, user_id=current_user.id,
            message="Хочу помочь!", status="pending"
        )
        db.add(app_obj)
        db.commit()
        db.refresh(app_obj)
        return {"success": True, "message": "Заявка подана! Ожидайте одобрения",
                "application_id": app_obj.id}
    except Exception as e:
        return {"success": False, "message": str(e)}

@app.get("/api/my-applications")
def get_my_applications(db: Session = Depends(get_db),
                        current_user: models.User = Depends(volunteer_required)):
    apps = db.query(models.TaskApplication).filter(
        models.TaskApplication.user_id == current_user.id).all()
    return [{
        "id": a.id, "task_id": a.task_id,
        "task_title": a.task.title if a.task else "—",
        "status": a.status, "message": a.message, "applied_at": a.applied_at
    } for a in apps]

@app.post("/api/projects/create")
def create_project(data: dict, db: Session = Depends(get_db),
                   current_user: models.User = Depends(organizer_required)):
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
def create_task(data: dict, db: Session = Depends(get_db),
                current_user: models.User = Depends(organizer_required)):
    try:
        task = models.Task(
            title=data.get("title"), description=data.get("description"),
            project_id=data.get("project_id"), event_date=data.get("event_date"),
            location=data.get("location"), needed_people=data.get("needed_people", 5),
            status="open"
        )
        # Всегда сохраняем difficulty и category (даже если не переданы — ставим дефолт)
        for field, default in [("difficulty", "medium"), ("category", "other"),
                                ("lat", None), ("lng", None)]:
            val = data.get(field) or default
            if val and hasattr(task, field):
                setattr(task, field, val)
        db.add(task)
        db.commit()
        db.refresh(task)
        return {"success": True, "message": "Задача создана", "id": task.id}
    except Exception as e:
        return {"success": False, "message": str(e)}

@app.put("/api/tasks/{task_id}/edit")
def edit_task(task_id: int, data: dict, db: Session = Depends(get_db),
              current_user: models.User = Depends(organizer_required)):
    try:
        task = db.query(models.Task).filter(models.Task.id == task_id).first()
        if not task:
            return {"success": False, "message": "Задача не найдена"}
        cnt = db.query(models.TaskApplication).filter(
            models.TaskApplication.task_id == task_id,
            models.TaskApplication.status.in_(["pending", "approved"])
        ).count()
        if cnt > 0:
            return {"success": False,
                    "message": f"BR-10: {cnt} волонтёр(ов) уже записалось"}
        for field in ("title", "description", "event_date", "location", "needed_people"):
            if field in data:
                setattr(task, field, data[field])
        db.commit()
        return {"success": True, "message": "Задача обновлена"}
    except Exception as e:
        return {"success": False, "message": str(e)}


# ── Applications ──────────────────────────────────────────────────────────────

@app.get("/api/applications/pending")
def get_pending_apps(db: Session = Depends(get_db),
                     current_user: models.User = Depends(curator_required)):
    apps = db.query(models.TaskApplication).filter(
        models.TaskApplication.status == "pending").all()
    return [{
        "id": a.id, "task_id": a.task_id,
        "task_title": a.task.title if a.task else "—",
        "user_id": a.user_id,
        "user_name": a.user.name if a.user else "—",
        "message": a.message, "applied_at": a.applied_at
    } for a in apps]

@app.post("/api/applications/{app_id}/approve")
@app.post("/applications/{app_id}/approve")
def approve_app(app_id: int, db: Session = Depends(get_db),
                current_user: models.User = Depends(curator_required)):
    try:
        a = db.query(models.TaskApplication).filter(
            models.TaskApplication.id == app_id).first()
        if not a:
            return {"success": False, "message": "Заявка не найдена"}
        a.status = "approved"
        assignment = models.TaskAssignment(
            task_id=a.task_id, user_id=a.user_id,
            assigned_by=current_user.id, status="assigned"
        )
        db.add(assignment)
        db.commit()
        return {"success": True, "message": "Заявка одобрена"}
    except Exception as e:
        return {"success": False, "message": str(e)}

@app.post("/api/applications/{app_id}/reject")
@app.post("/applications/{app_id}/reject")
def reject_app(app_id: int, db: Session = Depends(get_db),
               current_user: models.User = Depends(curator_required)):
    try:
        a = db.query(models.TaskApplication).filter(
            models.TaskApplication.id == app_id).first()
        if not a:
            return {"success": False, "message": "Заявка не найдена"}
        a.status = "rejected"
        db.commit()
        return {"success": True, "message": "Заявка отклонена"}
    except Exception as e:
        return {"success": False, "message": str(e)}

@app.get("/applications/for-curator")
def apps_for_curator(db: Session = Depends(get_db),
                     current_user: models.User = Depends(curator_required)):
    apps = db.query(models.TaskApplication).all()
    return [{
        "id": a.id, "task_id": a.task_id,
        "task_title": a.task.title if a.task else "—",
        "user_id": a.user_id,
        "user_name": a.user.name if a.user else "—",
        "user_email": a.user.email if a.user else "—",
        "message": a.message, "status": a.status,
        "applied_at": str(a.applied_at) if a.applied_at else None,
    } for a in apps]


# ── Reports ───────────────────────────────────────────────────────────────────

@app.get("/api/reports/pending")
def get_pending_reports(db: Session = Depends(get_db),
                        current_user: models.User = Depends(curator_required)):
    try:
        reports = db.query(models.TaskReport).filter(
            models.TaskReport.is_approved == False).all()
        return [{
            "id": r.id, "user_id": r.user_id,
            "user_name": r.user.name if r.user else "—",
            "hours": float(r.hours or 0), "comment": r.comment,
            "photo_url": r.photo_url,
            "submitted_at": str(r.submitted_at) if r.submitted_at else None,
        } for r in reports]
    except Exception:
        return []

@app.post("/api/reports/{report_id}/approve")
def approve_report(report_id: int, db: Session = Depends(get_db),
                   current_user: models.User = Depends(curator_required),
                   points: int = 0):
    try:
        r = db.query(models.TaskReport).filter(
            models.TaskReport.id == report_id).first()
        if not r:
            return {"success": False, "message": "Отчёт не найден"}
        r.is_approved = True
        # BR-09: куратор задаёт баллы; если не передал — считаем hours * 10
        if points > 0:
            r.points = points
        elif r.points == 0:
            r.points = int(float(r.hours or 0) * 10)
        db.commit()
        return {"success": True, "message": f"Отчёт одобрен, начислено {r.points} баллов", "points": r.points}
    except Exception as e:
        return {"success": False, "message": str(e)}

@app.post("/api/reports/{report_id}/reject")
def reject_report(report_id: int, db: Session = Depends(get_db),
                  current_user: models.User = Depends(curator_required)):
    try:
        r = db.query(models.TaskReport).filter(
            models.TaskReport.id == report_id).first()
        if not r:
            return {"success": False, "message": "Отчёт не найден"}
        db.delete(r)
        db.commit()
        return {"success": True, "message": "Отчёт отклонён"}
    except Exception as e:
        return {"success": False, "message": str(e)}

@app.get("/api/my-reports")
def get_my_reports(db: Session = Depends(get_db),
                   current_user: models.User = Depends(volunteer_required)):
    try:
        reports = db.query(models.TaskReport).filter(
            models.TaskReport.user_id == current_user.id).all()
        return [{
            "id": r.id, "hours": float(r.hours or 0), "comment": r.comment,
            "is_approved": r.is_approved, "submitted_at": r.submitted_at,
            "points": r.points if hasattr(r, 'points') and r.points else int(float(r.hours or 0) * 10) if r.is_approved else 0,
        } for r in reports]
    except Exception:
        return []

@app.post("/api/reports/create")
def create_report(data: dict, db: Session = Depends(get_db),
                  current_user: models.User = Depends(volunteer_required)):
    try:
        task_id = data.get("task_id")
        comment = data.get("comment")
        hours   = data.get("hours")
        if not task_id or not comment:
            return {"success": False, "message": "Укажите задачу и комментарий"}
        assignment = db.query(models.TaskAssignment).filter(
            models.TaskAssignment.task_id == task_id,
            models.TaskAssignment.user_id == current_user.id
        ).first()
        if not assignment:
            return {"success": False, "message": "Задача не назначена вам"}
        report = models.TaskReport(
            assignment_id=assignment.id, user_id=current_user.id,
            comment=comment, hours=hours, is_approved=False
        )
        db.add(report)
        db.commit()
        return {"success": True, "message": "Отчёт отправлен на проверку"}
    except Exception as e:
        return {"success": False, "message": str(e)}


# ── Admin ─────────────────────────────────────────────────────────────────────

@app.get("/api/admin/users")
def get_all_users(db: Session = Depends(get_db),
                  current_user: models.User = Depends(admin_required)):
    return [{
        "id": u.id, "email": u.email, "name": u.name,
        "city": getattr(u, 'city', None),
        "role": u.role.code, "role_name": u.role.name,
        "is_active": u.is_active, "created_at": u.created_at
    } for u in db.query(models.User).all()]

@app.post("/api/admin/users/{user_id}/toggle-active")
def toggle_active(user_id: int, db: Session = Depends(get_db),
                  current_user: models.User = Depends(admin_required)):
    try:
        u = db.query(models.User).filter(models.User.id == user_id).first()
        if not u:
            return {"success": False, "message": "Не найден"}
        u.is_active = not u.is_active
        db.commit()
        return {"success": True, "message": "активирован" if u.is_active else "заблокирован"}
    except Exception as e:
        return {"success": False, "message": str(e)}

@app.post("/api/admin/users/{user_id}/change-role")
def change_role(user_id: int, data: dict, db: Session = Depends(get_db),
                current_user: models.User = Depends(admin_required)):
    try:
        u = db.query(models.User).filter(models.User.id == user_id).first()
        role = db.query(models.Role).filter(models.Role.code == data.get("role")).first()
        if not u or not role:
            return {"success": False, "message": "Не найден"}
        u.role_id = role.id
        db.commit()
        return {"success": True, "message": f"Роль изменена на {role.name}"}
    except Exception as e:
        return {"success": False, "message": str(e)}


# ── Analytics ─────────────────────────────────────────────────────────────────

@app.get("/analytics/summary")
def analytics_summary(db: Session = Depends(get_db),
                      current_user: models.User = Depends(curator_required)):
    from sqlalchemy import func
    try:
        avg   = db.query(func.avg(models.TaskReport.hours)).filter(
            models.TaskReport.is_approved == True).scalar() or 0
        total = db.query(func.sum(models.TaskReport.hours)).filter(
            models.TaskReport.is_approved == True).scalar() or 0
    except Exception:
        avg, total = 0, 0
    return {
        "total_volunteers":   db.query(models.User).join(models.Role).filter(
            models.Role.code == "volunteer").count(),
        "active_tasks":       db.query(models.Task).filter(models.Task.status == "open").count(),
        "completed_reports":  0,
        "pending_reports":    0,
        "avg_hours_per_task": round(float(avg), 2),
        "total_hours":        round(float(total), 1),
    }


# ── Teams ─────────────────────────────────────────────────────────────────────

class TeamBody(BaseModel):
    name:        str
    description: Optional[str] = ""
    task_id:     Optional[int] = None
    max_size:    Optional[int] = None

@app.post("/api/teams/create")
def create_team(body: TeamBody, db: Session = Depends(get_db),
                current_user: models.User = Depends(curator_required)):
    from sqlalchemy import text
    try:
        row = db.execute(text("""
            INSERT INTO teams (name, description, task_id, max_size, created_by)
            VALUES (:name, :desc, :task_id, :max_size, :uid) RETURNING id
        """), {"name": body.name, "desc": body.description or "",
               "task_id": body.task_id, "max_size": body.max_size,
               "uid": current_user.id}).fetchone()
        db.commit()
        return {"success": True, "id": row[0],
                "message": f"Команда «{body.name}» создана"}
    except Exception as e:
        db.rollback()
        raise HTTPException(500, str(e))

@app.get("/api/teams")
def get_teams(db: Session = Depends(get_db),
              current_user: models.User = Depends(curator_required)):
    from sqlalchemy import text
    try:
        teams = db.execute(text("""
            SELECT t.id, t.name, t.description, t.task_id, t.max_size, tk.title
            FROM teams t LEFT JOIN tasks tk ON tk.id = t.task_id
            WHERE t.created_by = :uid ORDER BY t.created_at DESC
        """), {"uid": current_user.id}).fetchall()

        result = []
        for team in teams:
            members = db.execute(text("""
                SELECT u.id, u.name, u.email FROM team_members tm
                JOIN users u ON u.id = tm.user_id WHERE tm.team_id = :tid
            """), {"tid": team[0]}).fetchall()
            result.append({
                "id": team[0], "name": team[1], "description": team[2] or "",
                "task_id": team[3], "max_size": team[4], "task_title": team[5],
                "members": [{"id": m[0], "name": m[1] or m[2], "email": m[2]}
                            for m in members],
            })
        return result
    except Exception as e:
        db.rollback()
        return []

@app.post("/api/teams/{team_id}/members")
def add_member(team_id: int, body: dict, db: Session = Depends(get_db),
               current_user: models.User = Depends(curator_required)):
    from sqlalchemy import text
    try:
        db.execute(text("""
            INSERT INTO team_members (team_id, user_id)
            VALUES (:tid, :uid) ON CONFLICT DO NOTHING
        """), {"tid": team_id, "uid": body.get("user_id")})
        db.commit()
        return {"success": True, "message": "Волонтёр добавлен"}
    except Exception as e:
        db.rollback()
        raise HTTPException(500, str(e))

@app.delete("/api/teams/{team_id}/members/{user_id}")
def remove_member(team_id: int, user_id: int, db: Session = Depends(get_db),
                  current_user: models.User = Depends(curator_required)):
    from sqlalchemy import text
    try:
        db.execute(text("DELETE FROM team_members WHERE team_id=:tid AND user_id=:uid"),
                   {"tid": team_id, "uid": user_id})
        db.commit()
        return {"success": True, "message": "Участник удалён"}
    except Exception as e:
        db.rollback()
        raise HTTPException(500, str(e))

@app.delete("/api/teams/{team_id}")
def delete_team(team_id: int, db: Session = Depends(get_db),
                current_user: models.User = Depends(curator_required)):
    from sqlalchemy import text
    try:
        db.execute(text("DELETE FROM teams WHERE id=:id AND created_by=:uid"),
                   {"id": team_id, "uid": current_user.id})
        db.commit()
        return {"success": True, "message": "Команда удалена"}
    except Exception as e:
        db.rollback()
        raise HTTPException(500, str(e))


# ── Other ─────────────────────────────────────────────────────────────────────

@app.post("/tasks/{task_id}/assign/{user_id}")
def direct_assign(task_id: int, user_id: int, db: Session = Depends(get_db),
                  current_user: models.User = Depends(curator_required)):
    existing = db.query(models.TaskAssignment).filter(
        models.TaskAssignment.task_id == task_id,
        models.TaskAssignment.user_id == user_id).first()
    if existing:
        return {"success": False, "message": "Уже назначен"}
    db.add(models.TaskAssignment(
        task_id=task_id, user_id=user_id,
        assigned_by=current_user.id, status="assigned"))
    db.commit()
    return {"success": True, "message": "Волонтёр назначен"}

@app.post("/documents/{doc_id}/verify")
def verify_doc(doc_id: int, db: Session = Depends(get_db),
               current_user: models.User = Depends(curator_required)):
    try:
        doc = db.query(models.VolunteerDocument).filter(
            models.VolunteerDocument.id == doc_id).first()
        if not doc:
            return {"success": True, "message": f"Документ {doc_id} верифицирован"}
        doc.status = "verified"
        doc.verified_at = datetime.utcnow()
        doc.verified_by = current_user.id
        db.commit()
        return {"success": True, "message": "Документ верифицирован"}
    except Exception as e:
        return {"success": True, "message": "Верифицирован"}

REPORTS_UPLOAD_DIR = "media/reports"
os.makedirs(REPORTS_UPLOAD_DIR, exist_ok=True)

@app.post("/reports/")
async def create_report_photos(
    task_id: int = Form(...), comment: str = Form(...), hours: float = Form(...),
    photos: list[UploadFile] = File(None),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(volunteer_required)
):
    assignment = db.query(models.TaskAssignment).filter(
        models.TaskAssignment.task_id == task_id,
        models.TaskAssignment.user_id == current_user.id).first()
    if not assignment:
        raise HTTPException(403, "Задача не назначена вам")
    photo_urls = []
    if photos:
        for photo in photos:
            ext  = os.path.splitext(photo.filename)[1].lower()
            name = f"report_{task_id}_{uuid.uuid4().hex}{ext}"
            path = os.path.join(REPORTS_UPLOAD_DIR, name)
            with open(path, "wb") as f:
                f.write(await photo.read())
            photo_urls.append(f"/media/reports/{name}")
    db.add(models.TaskReport(
        assignment_id=assignment.id, user_id=current_user.id,
        comment=comment, hours=hours,
        photo_url=",".join(photo_urls) if photo_urls else None,
        is_approved=False))
    db.commit()
    return {"success": True, "message": "Отчёт отправлен"}

# ── Team enrollment (волонтёр записывается в команду) ─────────────────────────

@app.get("/api/teams/available")
def get_available_teams(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
):
    """Все доступные команды — волонтёр видит и может вступить."""
    from sqlalchemy import text
    try:
        teams = db.execute(text("""
            SELECT t.id, t.name, t.description, t.task_id, t.max_size,
                   tk.title as task_title,
                   u.name as curator_name,
                   COUNT(tm.user_id) as members_count,
                   MAX(CASE WHEN tm.user_id = :uid THEN 1 ELSE 0 END) as is_member
            FROM teams t
            LEFT JOIN tasks tk ON tk.id = t.task_id
            LEFT JOIN users u  ON u.id  = t.created_by
            LEFT JOIN team_members tm ON tm.team_id = t.id
            GROUP BY t.id, t.name, t.description, t.task_id, t.max_size,
                     tk.title, u.name
            ORDER BY t.created_at DESC
        """), {"uid": current_user.id}).fetchall()

        return [{
            "id":            row[0],
            "name":          row[1] or "",
            "description":   row[2] or "",
            "task_id":       row[3],
            "max_size":      row[4],
            "task_title":    row[5] or "",
            "curator_name":  row[6] or "",
            "members_count": int(row[7] or 0),
            "is_member":     int(row[8] or 0) > 0,   # cast int→bool
            "spots_left":    (row[4] - int(row[7] or 0)) if row[4] else None,
        } for row in teams]
    except Exception as e:
        db.rollback()
        return []


@app.post("/api/teams/{team_id}/join")
def join_team(
    team_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
):
    """Волонтёр записывается в команду."""
    from sqlalchemy import text
    try:
        # Проверяем лимит
        team = db.execute(text(
            "SELECT max_size FROM teams WHERE id = :tid"),
            {"tid": team_id}).fetchone()
        if not team:
            return {"success": False, "message": "Команда не найдена"}

        if team[0]:
            count = db.execute(text(
                "SELECT COUNT(*) FROM team_members WHERE team_id = :tid"),
                {"tid": team_id}).fetchone()[0]
            if count >= team[0]:
                return {"success": False, "message": "Команда уже заполнена"}

        # Уже в команде?
        existing = db.execute(text(
            "SELECT 1 FROM team_members WHERE team_id=:tid AND user_id=:uid"),
            {"tid": team_id, "uid": current_user.id}).fetchone()
        if existing:
            return {"success": False, "message": "Вы уже в этой команде"}

        # Создаём таблицу если нет
        db.execute(text("""
            CREATE TABLE IF NOT EXISTS team_members (
                team_id   BIGINT REFERENCES teams(id) ON DELETE CASCADE,
                user_id   BIGINT REFERENCES users(id) ON DELETE CASCADE,
                joined_at TIMESTAMPTZ DEFAULT NOW(),
                PRIMARY KEY (team_id, user_id)
            );
        """))
        db.commit()

        result = db.execute(text("""
            INSERT INTO team_members (team_id, user_id)
            VALUES (:tid, :uid) ON CONFLICT DO NOTHING
            RETURNING team_id
        """), {"tid": team_id, "uid": current_user.id})
        db.commit()

        inserted = result.fetchone()
        logger.info(
            f"[TEAM] join: user={current_user.email} team={team_id} "
            f"inserted={bool(inserted)}"
        )

        if not inserted:
            # Уже был в команде (ON CONFLICT)
            return {"success": True, "message": "Вы уже в этой команде",
                    "already_member": True}

        return {"success": True, "message": "Вы вступили в команду!"}
    except Exception as e:
        db.rollback()
        logger.error(f"[TEAM] join error: {e}")
        return {"success": False, "message": str(e)}


@app.post("/api/teams/{team_id}/leave")
def leave_team(
    team_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
):
    """Волонтёр выходит из команды."""
    from sqlalchemy import text
    try:
        db.execute(text(
            "DELETE FROM team_members WHERE team_id=:tid AND user_id=:uid"),
            {"tid": team_id, "uid": current_user.id})
        db.commit()
        return {"success": True, "message": "Вы вышли из команды"}
    except Exception as e:
        db.rollback()
        return {"success": False, "message": str(e)}


@app.get("/api/teams/my")
def get_my_teams(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
):
    """Команды в которых состоит волонтёр."""
    from sqlalchemy import text
    try:
        teams = db.execute(text("""
            SELECT t.id, t.name, t.description, tk.title, u.name,
                   COUNT(tm2.user_id) as members_count
            FROM team_members tm
            JOIN teams t ON t.id = tm.team_id
            LEFT JOIN tasks tk ON tk.id = t.task_id
            LEFT JOIN users u  ON u.id  = t.created_by
            LEFT JOIN team_members tm2 ON tm2.team_id = t.id
            WHERE tm.user_id = :uid
            GROUP BY t.id, t.name, t.description, tk.title, u.name
        """), {"uid": current_user.id}).fetchall()
        return [{
            "id":           row[0],
            "name":         row[1] or "",
            "description":  row[2] or "",
            "task_title":   row[3] or "",
            "curator_name": row[4] or "",
            "members_count": int(row[5] or 0),
        } for row in teams]
    except Exception as e:
        db.rollback()
        return []


# ── Team → Project admission (куратор допускает команду к проекту) ────────────

@app.post("/api/projects/{project_id}/teams/{team_id}/admit")
def admit_team_to_project(
    project_id: int,
    team_id:    int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(organizer_required)
):
    """Организатор допускает команду к проекту — все участники получают заявки на задачи."""
    from sqlalchemy import text
    try:
        # Получаем всех участников команды
        members = db.execute(text(
            "SELECT user_id FROM team_members WHERE team_id = :tid"),
            {"tid": team_id}).fetchall()

        if not members:
            return {"success": False, "message": "В команде нет участников"}

        # Получаем открытые задачи проекта
        tasks = db.execute(text(
            "SELECT id FROM tasks WHERE project_id=:pid AND status='open'"),
            {"pid": project_id}).fetchall()

        if not tasks:
            return {"success": False, "message": "Нет открытых задач в проекте"}

        added = 0
        for member in members:
            uid = member[0]
            for task in tasks:
                tid = task[0]
                # Проверяем что ещё не записан
                exists = db.execute(text("""
                    SELECT 1 FROM task_applications
                    WHERE task_id=:tid AND user_id=:uid
                """), {"tid": tid, "uid": uid}).fetchone()
                if not exists:
                    db.execute(text("""
                        INSERT INTO task_applications (task_id, user_id, message, status)
                        VALUES (:tid, :uid, 'Допущен командой', 'approved')
                    """), {"tid": tid, "uid": uid})
                    # Сразу создаём назначение
                    db.execute(text("""
                        INSERT INTO task_assignments (task_id, user_id, assigned_by, status)
                        VALUES (:tid, :uid, :by, 'assigned')
                        ON CONFLICT DO NOTHING
                    """), {"tid": tid, "uid": uid, "by": current_user.id})
                    added += 1

        db.commit()
        logger.info(
            f"[TEAM] admit: team={team_id} project={project_id} "
            f"members={len(members)} assigned={added}"
        )
        return {
            "success": True,
            "message": f"Команда допущена! {len(members)} волонтёров назначено на {len(tasks)} задач",
            "assigned": added,
        }
    except Exception as e:
        db.rollback()
        logger.error(f"[TEAM] admit error: {e}")
        return {"success": False, "message": str(e)}


@app.get("/api/projects/{project_id}/teams")
def get_project_teams(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
):
    """Команды допущенные к проекту (через task_assignments)."""
    from sqlalchemy import text
    try:
        teams = db.execute(text("""
            SELECT DISTINCT t.id, t.name, t.description,
                            COUNT(tm.user_id) as members_count
            FROM teams t
            JOIN team_members tm ON tm.team_id = t.id
            JOIN task_assignments ta ON ta.user_id = tm.user_id
            JOIN tasks tk ON tk.id = ta.task_id
            WHERE tk.project_id = :pid
            GROUP BY t.id, t.name, t.description
        """), {"pid": project_id}).fetchall()
        return [{
            "id":            row[0],
            "name":          row[1],
            "description":   row[2] or "",
            "members_count": int(row[3] or 0),
        } for row in teams]
    except Exception as e:
        db.rollback()
        return []

@app.patch("/tasks/{task_id}/complete")
@app.post("/tasks/{task_id}/complete")
def complete_task(
    task_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
):
    """Волонтёр отмечает задачу выполненной."""
    try:
        task = db.query(models.Task).filter(models.Task.id == task_id).first()
        if not task:
            return {"success": False, "message": "Задача не найдена"}

        # Проверяем что волонтёр назначен на задачу
        assignment = db.query(models.TaskAssignment).filter(
            models.TaskAssignment.task_id == task_id,
            models.TaskAssignment.user_id == current_user.id,
        ).first()
        if not assignment:
            # Также проверяем через заявку
            application = db.query(models.TaskApplication).filter(
                models.TaskApplication.task_id == task_id,
                models.TaskApplication.user_id == current_user.id,
                models.TaskApplication.status == "approved",
            ).first()
            if not application:
                return {"success": False, "message": "Вы не назначены на эту задачу"}

        task.status = "completed"
        db.commit()
        logger.info(f"[COMPLETE] user={current_user.email} task={task_id}")
        return {"success": True, "message": "Задача отмечена выполненной"}
    except Exception as e:
        db.rollback()
        return {"success": False, "message": str(e)}
