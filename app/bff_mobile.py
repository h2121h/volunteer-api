"""
BFF (Backend for Frontend) — Mobile клиент (Kivy, волонтёр).

Агрегирует данные специально для мобильного приложения:
- Один запрос вместо четырёх
- Только нужные поля (меньше трафика)
- Данные отфильтрованы по текущему волонтёру
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func
from app import models, auth
from app.database import get_db
from app.logger import logger

router = APIRouter(prefix="/bff/mobile", tags=["BFF Mobile"])


@router.get("/dashboard")
def mobile_dashboard(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.volunteer_required),
):
    """
    Один запрос вместо четырёх — Mobile получает всё нужное сразу.
    tasks + my_applications + stats + my_reports
    """
    try:
        # Все открытые задачи с проектами
        tasks = db.query(models.Task).filter(
            models.Task.status == "open"
        ).options(
            joinedload(models.Task.project)
        ).all()

        # Свои заявки (используем реальные статусы: pending/approved/rejected)
        applications = db.query(models.TaskApplication).filter(
            models.TaskApplication.user_id == current_user.id
        ).all()

        # Назначения волонтёра (через TaskAssignment)
        assignments = db.query(models.TaskAssignment).filter(
            models.TaskAssignment.user_id == current_user.id
        ).all()
        assignment_ids = {a.id for a in assignments}

        # Свои отчёты через assignment
        reports = []
        if assignment_ids:
            reports = db.query(models.TaskReport).filter(
                models.TaskReport.assignment_id.in_(assignment_ids)
            ).all()

        approved_reports = [r for r in reports if r.is_approved]
        pending_reports  = [r for r in reports if not r.is_approved]

        # Баллы: 10 баллов за каждый одобренный час (BR-09)
        total_hours  = sum(float(r.hours or 0) for r in approved_reports)
        total_points = int(total_hours * 10)

        # ID задач на которые уже записан
        applied_task_ids = {a.task_id for a in applications}

        logger.info(
            f"[BFF_MOBILE] dashboard: user={current_user.email} "
            f"tasks={len(tasks)} apps={len(applications)} "
            f"points={total_points}"
        )

        return {
            "user": {
                "id":    current_user.id,
                "name":  current_user.name,
                "email": current_user.email,
                "city":  getattr(current_user, 'city', None),
            },
            # Задачи с пометкой — записан или нет
            "tasks": [
                {
                    "id":              t.id,
                    "title":           t.title,
                    "description":     t.description,
                    "event_date":      str(t.event_date) if t.event_date else None,
                    "location":        t.location,
                    "needed_people":   t.needed_people,
                    "status":          t.status,
                    "project":         t.project.title if t.project else None,
                    "already_applied": t.id in applied_task_ids,
                }
                for t in tasks
            ],
            # Свои заявки с реальными статусами
            "my_applications": [
                {
                    "id":         a.id,
                    "task_id":    a.task_id,
                    "status":     a.status,
                    "applied_at": str(a.applied_at) if a.applied_at else None,
                }
                for a in applications
            ],
            # Статистика
            "stats": {
                "tasks_done":      len(approved_reports),
                "total_hours":     round(total_hours, 1),
                "total_points":    total_points,
                "pending_reports": len(pending_reports),
            },
            # Отчёты
            "my_reports": [
                {
                    "id":          r.id,
                    "hours":       float(r.hours or 0),
                    "comment":     r.comment,
                    "is_approved": r.is_approved,
                    "status":      "approved" if r.is_approved else "pending",
                    "points":      int(float(r.hours or 0) * 10) if r.is_approved else 0,
                }
                for r in reports
            ],
        }

    except Exception as e:
        logger.error(f"[BFF_MOBILE] dashboard error: {e}")
        raise


@router.post("/apply/{task_id}")
def mobile_apply(
    task_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.volunteer_required),
):
    """
    Запись на задачу через Mobile BFF.
    BR-01: лимит участников.
    BR-05: конфликт расписания.
    """
    task = db.query(models.Task).filter(models.Task.id == task_id).first()
    if not task:
        return {"success": False, "message": "Задача не найдена"}

    if task.status != "open":
        return {"success": False, "message": "Задача недоступна для записи"}

    # BR-01: лимит участников
    # Статусы: pending (ожидает), approved (одобрена)
    count = db.query(models.TaskApplication).filter(
        models.TaskApplication.task_id == task_id,
        models.TaskApplication.status.in_(["pending", "approved"]),
    ).count()
    if count >= task.needed_people:
        return {
            "success": False,
            "message": "BR-01: достигнут лимит участников",
            "code": "BR-01",
        }

    # BR-05: конфликт расписания
    conflict = db.query(models.TaskApplication).join(models.Task).filter(
        models.TaskApplication.user_id == current_user.id,
        models.TaskApplication.status.in_(["pending", "approved"]),
        models.Task.event_date == task.event_date,
        models.Task.id != task_id,
    ).first()
    if conflict:
        return {
            "success": False,
            "message": "BR-05: конфликт расписания с другой задачей",
            "code": "BR-05",
        }

    # Уже записан?
    existing = db.query(models.TaskApplication).filter(
        models.TaskApplication.task_id == task_id,
        models.TaskApplication.user_id == current_user.id,
    ).first()
    if existing:
        return {"success": False, "message": "Вы уже подали заявку"}

    application = models.TaskApplication(
        task_id=task_id,
        user_id=current_user.id,
        message="Хочу помочь!",
        status="pending",
    )
    db.add(application)
    db.commit()

    logger.info(f"[BFF_MOBILE] apply: user={current_user.email} task={task_id}")

    return {
        "success": True,
        "message": "Заявка подана! Ожидайте одобрения куратора",
        "application_id": application.id,
    }
