"""
BFF Mobile — с защитой от отсутствующих таблиц.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app import models, auth
from app.database import get_db
from app.logger import logger

router = APIRouter(prefix="/bff/mobile", tags=["BFF Mobile"])


@router.get("/dashboard")
def mobile_dashboard(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.volunteer_required),
):
    try:
        user_id = current_user.id

        # 1. Открытые задачи
        tasks_q = db.query(models.Task).filter(
            models.Task.status == "open"
        ).all()

        # 2. Проекты для задач
        project_ids = list({t.project_id for t in tasks_q if t.project_id})
        projects = {}
        if project_ids:
            for p in db.query(models.Project).filter(
                models.Project.id.in_(project_ids)
            ).all():
                projects[p.id] = p.title

        # 3. Мои заявки
        my_apps = db.query(models.TaskApplication).filter(
            models.TaskApplication.user_id == user_id
        ).all()
        applied_ids = {a.task_id for a in my_apps}

        # 4. Отчёты — таблица может не существовать
        my_reports    = []
        total_hours   = 0.0
        total_points  = 0
        pending_cnt   = 0
        try:
            my_assignments = db.query(models.TaskAssignment).filter(
                models.TaskAssignment.user_id == user_id
            ).all()
            if my_assignments:
                asgn_ids   = [a.id for a in my_assignments]
                my_reports = db.query(models.TaskReport).filter(
                    models.TaskReport.assignment_id.in_(asgn_ids)
                ).all()
                for r in my_reports:
                    h = float(r.hours or 0)
                    if r.is_approved:
                        total_hours  += h
                        total_points += int(h * 10)
                    else:
                        pending_cnt += 1
        except Exception as report_err:
            # Таблица task_reports или task_assignments ещё не создана
            logger.warning(f"[BFF_MOBILE] reports skipped: {report_err}")
            my_reports = []

        logger.info(
            f"[BFF_MOBILE] user={current_user.email} "
            f"tasks={len(tasks_q)} apps={len(my_apps)} points={total_points}"
        )

        return {
            "user": {
                "id":    user_id,
                "name":  current_user.name or "",
                "email": current_user.email,
                "city":  current_user.city if hasattr(current_user, 'city') else None,
            },
            "tasks": [
                {
                    "id":              t.id,
                    "title":           t.title or "",
                    "description":     t.description or "",
                    "event_date":      str(t.event_date) if t.event_date else None,
                    "location":        t.location or "",
                    "needed_people":   t.needed_people or 0,
                    "status":          t.status or "open",
                    "project":         projects.get(t.project_id, ""),
                    "already_applied": t.id in applied_ids,
                }
                for t in tasks_q
            ],
            "my_applications": [
                {
                    "id":         a.id,
                    "task_id":    a.task_id,
                    "status":     a.status or "pending",
                    "applied_at": str(a.applied_at) if a.applied_at else None,
                }
                for a in my_apps
            ],
            "stats": {
                "tasks_done":      len([r for r in my_reports if r.is_approved]),
                "total_hours":     round(total_hours, 1),
                "total_points":    total_points,
                "pending_reports": pending_cnt,
            },
            "my_reports": [
                {
                    "id":          r.id,
                    "hours":       float(r.hours or 0),
                    "comment":     r.comment or "",
                    "is_approved": bool(r.is_approved),
                    "status":      "approved" if r.is_approved else "pending",
                    "points":      int(float(r.hours or 0) * 10) if r.is_approved else 0,
                }
                for r in my_reports
            ],
        }

    except Exception as e:
        logger.error(f"[BFF_MOBILE] ERROR: {type(e).__name__}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/apply/{task_id}")
def mobile_apply(
    task_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.volunteer_required),
):
    try:
        task = db.query(models.Task).filter(models.Task.id == task_id).first()
        if not task:
            return {"success": False, "message": "Задача не найдена"}
        if task.status != "open":
            return {"success": False, "message": "Задача недоступна"}

        # BR-01
        count = db.query(models.TaskApplication).filter(
            models.TaskApplication.task_id == task_id,
            models.TaskApplication.status.in_(["pending", "approved"]),
        ).count()
        if count >= (task.needed_people or 999):
            return {"success": False, "code": "BR-01",
                    "message": "BR-01: достигнут лимит участников"}

        # BR-05
        if task.event_date:
            conflict = db.query(models.TaskApplication).join(
                models.Task, models.TaskApplication.task_id == models.Task.id
            ).filter(
                models.TaskApplication.user_id == current_user.id,
                models.TaskApplication.status.in_(["pending", "approved"]),
                models.Task.event_date == task.event_date,
                models.Task.id != task_id,
            ).first()
            if conflict:
                return {"success": False, "code": "BR-05",
                        "message": "BR-05: конфликт расписания"}

        existing = db.query(models.TaskApplication).filter(
            models.TaskApplication.task_id == task_id,
            models.TaskApplication.user_id == current_user.id,
        ).first()
        if existing:
            return {"success": False, "message": "Вы уже подали заявку"}

        app = models.TaskApplication(
            task_id=task_id,
            user_id=current_user.id,
            message="Хочу помочь!",
            status="pending",
        )
        db.add(app)
        db.commit()

        return {
            "success": True,
            "message": "Заявка подана! Ожидайте одобрения куратора",
            "application_id": app.id,
        }

    except Exception as e:
        logger.error(f"[BFF_MOBILE] apply ERROR: {e}")
        raise HTTPException(status_code=500, detail=str(e))
