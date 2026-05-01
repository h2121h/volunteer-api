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

        # 2. Проекты (для открытых задач)
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

        # 3a. Догружаем исторические задачи (закрытые/прошедшие) по заявкам
        #     чтобы в истории заголовки отображались корректно
        open_task_ids = {t.id for t in tasks_q}
        hist_task_ids = {a.task_id for a in my_apps} - open_task_ids
        hist_tasks = []
        if hist_task_ids:
            hist_tasks = db.query(models.Task).filter(
                models.Task.id.in_(hist_task_ids)
            ).all()
            for t in hist_tasks:
                if t.project_id and t.project_id not in projects:
                    p = db.query(models.Project).filter(
                        models.Project.id == t.project_id
                    ).first()
                    if p:
                        projects[t.project_id] = p.title

        # Общий map всех задач (открытые + исторические)
        all_tasks_map = {t.id: t for t in tasks_q + hist_tasks}

        # 4. Отчёты — таблицы могут не существовать
        #    ВАЖНО: rollback после ошибки — иначе вся сессия в ABORTED
        my_reports   = []
        total_hours  = 0.0
        total_points = 0
        pending_cnt  = 0

        try:
            my_assignments = db.query(models.TaskAssignment).filter(
                models.TaskAssignment.user_id == user_id
            ).all()
            if my_assignments:
                asgn_ids   = [a.id for a in my_assignments]
                # Строим map assignment_id -> task_id
                asgn_task_map = {a.id: a.task_id for a in my_assignments}
                my_reports = db.query(models.TaskReport).filter(
                    models.TaskReport.assignment_id.in_(asgn_ids)
                ).all()
                for r in my_reports:
                    h = float(r.hours or 0)
                    pts = r.points if hasattr(r, 'points') and r.points else int(h * 10)
                    if r.is_approved:
                        total_hours  += h
                        total_points += pts
                    else:
                        pending_cnt += 1
            else:
                asgn_task_map = {}
        except Exception as e:
            logger.warning(f"[BFF_MOBILE] reports skipped (table missing?): {e}")
            db.rollback()   # ← сброс ABORTED транзакции
            my_reports = []
            asgn_task_map = {}

        logger.info(
            f"[BFF_MOBILE] OK user={current_user.email} "
            f"tasks={len(tasks_q)} apps={len(my_apps)} pts={total_points}"
        )

        # Команды волонтёра (через many-to-many team_members)
        try:
            my_teams = [
                {"id": t.id, "name": t.name}
                for t in db.query(models.Team).join(
                    models.team_members,
                    models.Team.id == models.team_members.c.team_id
                ).filter(models.team_members.c.user_id == user_id).all()
            ]
        except Exception:
            my_teams = []

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
                    "difficulty":      t.difficulty if hasattr(t, "difficulty") else "medium",
                    "category":        t.category if hasattr(t, "category") else "other",
                }
                for t in tasks_q
            ],
            "history_tasks": [
                {
                    "id":         t.id,
                    "title":      t.title or "",
                    "event_date": str(t.event_date) if t.event_date else None,
                    "location":   t.location or "",
                    "status":     t.status or "closed",
                    "project":    projects.get(t.project_id, ""),
                }
                for t in hist_tasks
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
            "my_teams": my_teams,
            "my_reports": [
                {
                    "id":          r.id,
                    "task_id":     asgn_task_map.get(r.assignment_id),
                    "task_title":  (all_tasks_map[asgn_task_map[r.assignment_id]].title if asgn_task_map.get(r.assignment_id) and asgn_task_map[r.assignment_id] in all_tasks_map else None),
                    "hours":       float(r.hours or 0),
                    "comment":     r.comment or "",
                    "is_approved": bool(r.is_approved),
                    "status":      "approved" if r.is_approved else "pending",
                    "points":      (r.points if hasattr(r, 'points') and r.points else int(float(r.hours or 0) * 10)) if r.is_approved else 0,
                    "submitted_at": str(r.submitted_at) if r.submitted_at else None,
                }
                for r in my_reports
            ],
        }

    except Exception as e:
        logger.error(f"[BFF_MOBILE] FATAL: {type(e).__name__}: {e}")
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
            models.TaskApplication.status.in_(["created", "active"]),
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
                models.TaskApplication.status.in_(["created", "active"]),
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
            status="created",
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
