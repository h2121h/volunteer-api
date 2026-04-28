"""
BFF Desktop — организатор видит всё без фильтров.
Защищён от отсутствующих таблиц (task_reports, task_assignments).
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func
from app import models, auth
from app.database import get_db
from app.logger import logger

router = APIRouter(prefix="/bff/desktop", tags=["BFF Desktop"])


@router.get("/dashboard")
def desktop_dashboard(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.organizer_required),
):
    try:
        # ── Проекты ───────────────────────────────────────────────────────
        projects_q = db.query(models.Project).all()

        # Создатели проектов
        creator_ids = [p.created_by for p in projects_q if p.created_by]
        creators = {}
        if creator_ids:
            for u in db.query(models.User).filter(
                models.User.id.in_(creator_ids)
            ).all():
                creators[u.id] = u.name or u.email

        # ── Задачи ────────────────────────────────────────────────────────
        tasks_q = db.query(models.Task).all()

        project_ids = [t.project_id for t in tasks_q if t.project_id]
        projects_map = {p.id: p.title for p in projects_q}

        # ── Пользователи ──────────────────────────────────────────────────
        all_users = db.query(models.User).all()

        # Роли одним запросом
        roles_q = db.query(models.Role).all()
        roles_map = {r.id: r.code for r in roles_q}

        volunteers = [u for u in all_users
                      if roles_map.get(u.role_id) == "volunteer"]
        curators   = [u for u in all_users
                      if roles_map.get(u.role_id) == "curator"]

        # ── Заявки ────────────────────────────────────────────────────────
        applications = db.query(models.TaskApplication).all()

        # Задачи и волонтёры для заявок
        task_map = {t.id: t.title for t in tasks_q}
        user_map = {u.id: (u.name or u.email) for u in all_users}

        # ── Отчёты (с защитой от отсутствия таблицы) ─────────────────────
        reports      = []
        total_hours  = 0.0
        approved_cnt = 0
        pending_cnt  = 0

        try:
            reports = db.query(models.TaskReport).all()
            approved_cnt = sum(1 for r in reports if r.is_approved)
            pending_cnt  = sum(1 for r in reports if not r.is_approved)
            total_hours  = sum(float(r.hours or 0) for r in reports if r.is_approved)
        except Exception as e:
            logger.warning(f"[BFF_DESKTOP] reports skipped: {e}")
            db.rollback()

        logger.info(
            f"[BFF_DESKTOP] organizer={current_user.email} "
            f"projects={len(projects_q)} tasks={len(tasks_q)} "
            f"volunteers={len(volunteers)} reports={len(reports)}"
        )

        return {
            "organizer": {
                "id":    current_user.id,
                "name":  current_user.name,
                "email": current_user.email,
            },
            "projects": [
                {
                    "id":          p.id,
                    "title":       p.title or "",
                    "description": p.description or "",
                    "status":      p.status or "active",
                    "creator":     creators.get(p.created_by, "—"),
                    "created_at":  str(p.created_at) if p.created_at else None,
                }
                for p in projects_q
            ],
            "tasks": [
                {
                    "id":            t.id,
                    "title":         t.title or "",
                    "project":       projects_map.get(t.project_id, "—"),
                    "project_id":    t.project_id,
                    "event_date":    str(t.event_date) if t.event_date else None,
                    "location":      t.location or "",
                    "needed_people": t.needed_people or 0,
                    "status":        t.status or "open",
                }
                for t in tasks_q
            ],
            "volunteers": [
                {
                    "id":        u.id,
                    "name":      u.name or "",
                    "email":     u.email or "",
                    "city":      u.city if hasattr(u, 'city') else "",
                    "role":      roles_map.get(u.role_id, "volunteer"),
                    "is_active": bool(u.is_active),
                }
                for u in volunteers
            ],
            "curators": [
                {
                    "id":    u.id,
                    "name":  u.name or "",
                    "email": u.email or "",
                }
                for u in curators
            ],
            "applications": [
                {
                    "id":         a.id,
                    "task_id":    a.task_id,
                    "task_title": task_map.get(a.task_id, "—"),
                    "user_id":    a.user_id,
                    "user_name":  user_map.get(a.user_id, "—"),
                    "status":     a.status or "pending",
                    "applied_at": str(a.applied_at) if a.applied_at else None,
                }
                for a in applications
            ],
            "reports": [
                {
                    "id":          r.id,
                    "user_id":     r.user_id,
                    "user_name":   user_map.get(r.user_id, "—"),
                    "hours":       float(r.hours or 0),
                    "is_approved": bool(r.is_approved),
                    "comment":     r.comment or "",
                    "submitted_at": str(r.submitted_at) if r.submitted_at else None,
                }
                for r in reports
            ],
            "analytics": {
                "total_projects":       len(projects_q),
                "total_tasks":          len(tasks_q),
                "open_tasks":           sum(1 for t in tasks_q if t.status == "open"),
                "total_volunteers":     len(volunteers),
                "total_curators":       len(curators),
                "total_reports":        len(reports),
                "approved_reports":     approved_cnt,
                "pending_reports":      pending_cnt,
                "total_hours":          round(total_hours, 1),
                "total_points":         int(total_hours * 10),
                "applications_total":   len(applications),
                # pending — реальный статус в БД
                "applications_pending": sum(
                    1 for a in applications
                    if a.status in ("pending", "created")
                ),
            },
        }

    except Exception as e:
        logger.error(f"[BFF_DESKTOP] FATAL: {type(e).__name__}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/export")
def desktop_export(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.organizer_required),
):
    """UC-15 Экспорт — только одобренные отчёты (BR-07)."""
    try:
        reports = []
        try:
            reports = db.query(models.TaskReport).filter(
                models.TaskReport.is_approved == True
            ).all()
        except Exception as e:
            logger.warning(f"[BFF_DESKTOP] export reports skipped: {e}")
            db.rollback()

        user_ids = list({r.user_id for r in reports})
        users = {}
        if user_ids:
            for u in db.query(models.User).filter(
                models.User.id.in_(user_ids)
            ).all():
                users[u.id] = {"name": u.name or "—", "email": u.email or "—"}

        return {
            "export_data": [
                {
                    "volunteer": users.get(r.user_id, {}).get("name", "—"),
                    "email":     users.get(r.user_id, {}).get("email", "—"),
                    "hours":     float(r.hours or 0),
                    "points":    int(float(r.hours or 0) * 10),
                    "comment":   r.comment or "",
                    "approved":  True,
                }
                for r in reports
            ],
            "total_volunteers": len(user_ids),
            "total_hours":      round(sum(float(r.hours or 0) for r in reports), 1),
            "generated_by":     current_user.email,
        }

    except Exception as e:
        logger.error(f"[BFF_DESKTOP] export ERROR: {e}")
        raise HTTPException(status_code=500, detail=str(e))
