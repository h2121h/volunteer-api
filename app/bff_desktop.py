"""
BFF (Backend for Frontend) — Desktop клиент (PyQt6, организатор).

Агрегирует данные специально для десктопного приложения:
- Все данные без фильтра (организатор = admin)
- Тяжёлая аналитика — только Desktop может это обработать
- Данные для PDF/Excel экспорта
- Управление пользователями и ролями
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session, joinedload
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
    """
    Полная картина системы — только для организатора.
    Без фильтров по ownership — организатор видит ВСЁ.
    """
    # Все проекты
    projects = db.query(models.Project).options(
        joinedload(models.Project.creator)
    ).all()

    # Все задачи
    tasks = db.query(models.Task).options(
        joinedload(models.Task.project)
    ).all()

    # Все пользователи
    all_users = db.query(models.User).options(
        joinedload(models.User.role)
    ).all()

    volunteers = [u for u in all_users if u.role and u.role.code == "volunteer"]
    curators   = [u for u in all_users if u.role and u.role.code == "curator"]

    # Все заявки
    applications = db.query(models.TaskApplication).options(
        joinedload(models.TaskApplication.task),
        joinedload(models.TaskApplication.user),
    ).all()

    # Все отчёты
    reports = db.query(models.TaskReport).options(
        joinedload(models.TaskReport.user),
    ).all()

    approved = [r for r in reports if r.is_approved]
    pending  = [r for r in reports if not r.is_approved]

    total_hours = db.query(func.sum(models.TaskReport.hours)).filter(
        models.TaskReport.is_approved == True
    ).scalar() or 0

    logger.info(
        f"[BFF_DESKTOP] dashboard: organizer={current_user.email} "
        f"projects={len(projects)} tasks={len(tasks)} "
        f"volunteers={len(volunteers)} reports={len(reports)}"
    )

    return {
        "organizer": {
            "id":    current_user.id,
            "name":  current_user.name,
            "email": current_user.email,
        },
        # Проекты
        "projects": [
            {
                "id":          p.id,
                "title":       p.title,
                "description": p.description,
                "status":      p.status,
                "creator":     p.creator.name if p.creator else "—",
                "created_at":  str(p.created_at) if p.created_at else None,
            }
            for p in projects
        ],
        # Задачи
        "tasks": [
            {
                "id":            t.id,
                "title":         t.title,
                "project":       t.project.title if t.project else "—",
                "event_date":    str(t.event_date) if t.event_date else None,
                "location":      t.location,
                "needed_people": t.needed_people,
                "status":        t.status,
            }
            for t in tasks
        ],
        # Все волонтёры
        "volunteers": [
            {
                "id":        u.id,
                "name":      u.name,
                "email":     u.email,
                "city":      u.city,
                "role":      u.role.code if u.role else "volunteer",
                "is_active": u.is_active,
            }
            for u in volunteers
        ],
        # Все кураторы
        "curators": [
            {
                "id":    u.id,
                "name":  u.name,
                "email": u.email,
            }
            for u in curators
        ],
        # Все заявки
        "applications": [
            {
                "id":         a.id,
                "task_id":    a.task_id,
                "task_title": a.task.title if a.task else "—",
                "user_id":    a.user_id,
                "user_name":  a.user.name if a.user else "—",
                "email":      a.user.email if a.user else "—",
                "message":    a.message,
                "status":     a.status,
                "applied_at": str(a.applied_at) if a.applied_at else None,
            }
            for a in applications
        ],
        # Все отчёты
        "reports": [
            {
                "id":           r.id,
                "user_id":      r.user_id,
                "user_name":    r.user.name if r.user else "—",
                "task_id":      r.assignment.task_id if r.assignment else None,
                "hours":        float(r.hours or 0),
                "is_approved":  r.is_approved,
                "comment":      r.comment,
                "photo_url":    r.photo_url,
                "submitted_at": str(r.submitted_at) if r.submitted_at else None,
            }
            for r in reports
        ],
        # Полная аналитика (UC-18)
        "analytics": {
            "total_projects":    len(projects),
            "total_tasks":       len(tasks),
            "open_tasks":        len([t for t in tasks if t.status == "open"]),
            "total_volunteers":  len(volunteers),
            "total_curators":    len(curators),
            "total_reports":     len(reports),
            "approved_reports":  len(approved),
            "pending_reports":   len(pending),
            "total_hours":       round(float(total_hours), 1),
            "total_points":      int(float(total_hours) * 10),
            "applications_total": len(applications),
            "applications_pending": len([a for a in applications if a.status == "created"]),
        },
    }


@router.get("/export")
def desktop_export(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.organizer_required),
):
    """
    Данные для экспорта в PDF/Excel (UC-15).
    Возвращает все данные в удобном для таблиц формате.
    """
    reports = db.query(models.TaskReport).options(
        joinedload(models.TaskReport.user),
        joinedload(models.TaskReport.assignment),
    ).filter(
        models.TaskReport.is_approved == True
    ).all()

    logger.info(f"[BFF_DESKTOP] export: organizer={current_user.email} reports={len(reports)}")

    return {
        "export_data": [
            {
                "volunteer":  r.user.name if r.user else "—",
                "email":      r.user.email if r.user else "—",
                "hours":      float(r.hours or 0),
                "points":     int(float(r.hours or 0) * 10),
                "comment":    r.comment,
                "approved":   r.is_approved,
            }
            for r in reports
        ],
        "total_volunteers": len({r.user_id for r in reports}),
        "total_hours":      round(sum(float(r.hours or 0) for r in reports), 1),
        "generated_by":     current_user.email,
    }
