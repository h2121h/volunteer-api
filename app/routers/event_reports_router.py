"""
Сводные отчёты по мероприятиям для куратора.

Цепочка:
  Волонтёры сдают task_reports (часы + комментарий + оценка)
    → BFF агрегирует по задаче/команде в EventReport
      → Куратор видит сводку: участники команды, часы, средняя оценка
        → Desktop одобряет → report.is_approved = True

Новые поля в task_reports:
  rating       — оценка мероприятия волонтёром (1-5)
  attended     — волонтёр присутствовал (True/False)
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import text
from pydantic import BaseModel
from typing import Optional
from app import models, auth
from app.database import get_db
from app.logger import logger

router = APIRouter(prefix="/api/event-reports", tags=["Event Reports"])


def _ensure_columns(db: Session):
    """Добавляем поля rating и attended в task_reports если нет."""
    try:
        db.execute(text("""
            ALTER TABLE task_reports
                ADD COLUMN IF NOT EXISTS rating   SMALLINT DEFAULT NULL,
                ADD COLUMN IF NOT EXISTS attended BOOLEAN  DEFAULT TRUE;
        """))
        db.commit()
    except Exception:
        db.rollback()


# ── DTO ────────────────────────────────────────────────────────────────────────

class VolunteerReportBody(BaseModel):
    task_id:   int
    hours:     float
    comment:   str
    rating:    Optional[int] = None   # оценка 1-5
    attended:  bool = True            # присутствовал ли
    photo_url: Optional[str] = None


# ── Волонтёр сдаёт отчёт с оценкой ───────────────────────────────────────────

@router.post("/submit")
def submit_volunteer_report(
    body: VolunteerReportBody,
    db:   Session = Depends(get_db),
    user: models.User = Depends(auth.volunteer_required),
):
    """
    Волонтёр сдаёт отчёт о мероприятии.
    Включает: часы, комментарий, оценку (1-5), отметку о присутствии.
    """
    _ensure_columns(db)
    try:
        # Находим назначение
        assignment = db.query(models.TaskAssignment).filter(
            models.TaskAssignment.task_id == body.task_id,
            models.TaskAssignment.user_id == user.id,
        ).first()

        if not assignment:
            return {"success": False,
                    "message": "Вы не назначены на эту задачу"}

        # Уже сдавал?
        existing = db.query(models.TaskReport).filter(
            models.TaskReport.assignment_id == assignment.id,
            models.TaskReport.user_id == user.id,
        ).first()
        if existing:
            return {"success": False, "message": "Отчёт уже подан"}

        if body.rating and not (1 <= body.rating <= 5):
            return {"success": False, "message": "Оценка должна быть от 1 до 5"}

        report = models.TaskReport(
            assignment_id = assignment.id,
            user_id       = user.id,
            hours         = body.hours,
            comment       = body.comment,
            photo_url     = body.photo_url,
            is_approved   = False,
        )
        db.add(report)
        db.flush()

        # Дополнительные поля через raw SQL
        db.execute(text("""
            UPDATE task_reports
            SET rating = :rating, attended = :attended
            WHERE id = :id
        """), {"rating": body.rating, "attended": body.attended, "id": report.id})

        db.commit()
        logger.info(
            f"[EVENT_REPORT] submitted: user={user.email} "
            f"task={body.task_id} rating={body.rating}"
        )
        return {"success": True, "id": report.id,
                "message": "Отчёт подан на проверку куратору"}

    except Exception as e:
        db.rollback()
        logger.error(f"[EVENT_REPORT] submit error: {e}")
        return {"success": False, "message": str(e)}


# ── Куратор видит сводный отчёт по задаче ────────────────────────────────────

@router.get("/task/{task_id}/summary")
def get_task_event_summary(
    task_id: int,
    db:      Session = Depends(get_db),
    user:    models.User = Depends(auth.curator_required),
):
    """
    Сводный отчёт куратора по одной задаче/мероприятию.
    Агрегирует отчёты всех волонтёров:
      - участники команды
      - сколько присутствовало
      - общие часы
      - средняя оценка мероприятия
      - индивидуальные отчёты волонтёров
    """
    _ensure_columns(db)
    try:
        # Информация о задаче
        task = db.query(models.Task).filter(models.Task.id == task_id).first()
        if not task:
            raise HTTPException(404, "Задача не найдена")

        # Все отчёты волонтёров по задаче
        rows = db.execute(text("""
            SELECT
                r.id,
                u.id         AS user_id,
                u.name       AS user_name,
                u.email      AS user_email,
                r.hours,
                r.comment,
                r.photo_url,
                r.is_approved,
                r.submitted_at,
                COALESCE(r.rating,   0) AS rating,
                COALESCE(r.attended, TRUE) AS attended,
                t_name.name  AS team_name
            FROM task_reports r
            JOIN task_assignments a ON a.id = r.assignment_id
            JOIN users u ON u.id = r.user_id
            LEFT JOIN team_members tm ON tm.user_id = u.id
            LEFT JOIN teams t_name ON t_name.id = tm.team_id
            WHERE a.task_id = :tid
            ORDER BY r.submitted_at DESC
        """), {"tid": task_id}).fetchall()

        if not rows:
            return {
                "task_id":   task_id,
                "task_title": task.title,
                "summary": {"total": 0, "attended": 0, "avg_rating": None,
                            "total_hours": 0, "approved": 0},
                "reports": [],
            }

        # Агрегация
        total        = len(rows)
        attended_cnt = sum(1 for r in rows if r[10])
        ratings      = [r[9] for r in rows if r[9] > 0]
        avg_rating   = round(sum(ratings) / len(ratings), 2) if ratings else None
        total_hours  = round(sum(float(r[4] or 0) for r in rows), 1)
        approved_cnt = sum(1 for r in rows if r[7])

        # Команды участников
        teams = {}
        for r in rows:
            tname = r[11] or "Без команды"
            if tname not in teams:
                teams[tname] = {"attended": 0, "total": 0}
            teams[tname]["total"] += 1
            if r[10]:
                teams[tname]["attended"] += 1

        reports = [{
            "id":          r[0],
            "user_id":     r[1],
            "user_name":   r[2] or r[3],
            "hours":       float(r[4] or 0),
            "comment":     r[5] or "",
            "photo_url":   r[6],
            "is_approved": bool(r[7]),
            "submitted_at": str(r[8]) if r[8] else None,
            "rating":      r[9] if r[9] > 0 else None,
            "attended":    bool(r[10]),
            "team_name":   r[11] or "Без команды",
        } for r in rows]

        return {
            "task_id":    task_id,
            "task_title": task.title,
            "task_date":  str(task.event_date) if task.event_date else None,
            "location":   task.location or "",
            "summary": {
                "total_volunteers": total,
                "attended":         attended_cnt,
                "not_attended":     total - attended_cnt,
                "attendance_rate":  round(attended_cnt / total * 100) if total else 0,
                "avg_rating":       avg_rating,
                "total_hours":      total_hours,
                "approved_reports": approved_cnt,
                "pending_reports":  total - approved_cnt,
            },
            "teams_breakdown": [
                {"team": k, "attended": v["attended"], "total": v["total"]}
                for k, v in teams.items()
            ],
            "reports": reports,
        }

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"[EVENT_REPORT] summary error: {e}")
        raise HTTPException(500, str(e))


# ── Список задач с отчётами (для Desktop) ────────────────────────────────────

@router.get("/pending")
def get_pending_event_reports(
    db:   Session = Depends(get_db),
    user: models.User = Depends(auth.curator_required),
):
    """
    Список задач у которых есть неодобренные отчёты.
    Для Desktop — куратор видит сводку и одобряет.
    """
    _ensure_columns(db)
    try:
        tasks = db.execute(text("""
            SELECT
                t.id,
                t.title,
                t.event_date,
                t.location,
                COUNT(r.id)                              AS total_reports,
                COUNT(r.id) FILTER (WHERE r.is_approved = FALSE) AS pending,
                ROUND(AVG(r.rating) FILTER (WHERE r.rating > 0), 1) AS avg_rating,
                COALESCE(SUM(r.hours), 0)                AS total_hours
            FROM tasks t
            JOIN task_assignments a ON a.task_id = t.id
            JOIN task_reports r ON r.assignment_id = a.id
            GROUP BY t.id, t.title, t.event_date, t.location
            HAVING COUNT(r.id) FILTER (WHERE r.is_approved = FALSE) > 0
            ORDER BY t.event_date DESC
        """)).fetchall()

        return [{
            "task_id":       r[0],
            "task_title":    r[1],
            "event_date":    str(r[2]) if r[2] else None,
            "location":      r[3] or "",
            "total_reports": int(r[4] or 0),
            "pending":       int(r[5] or 0),
            "avg_rating":    float(r[6]) if r[6] else None,
            "total_hours":   float(r[7] or 0),
        } for r in tasks]

    except Exception as e:
        db.rollback()
        return []


# ── Одобрить все отчёты по задаче (массовое одобрение) ───────────────────────

@router.post("/task/{task_id}/approve-all")
def approve_all_task_reports(
    task_id: int,
    db:      Session = Depends(get_db),
    user:    models.User = Depends(auth.curator_required),
):
    """Куратор одобряет все отчёты по задаче разом (из Desktop)."""
    try:
        result = db.execute(text("""
            UPDATE task_reports r
            SET is_approved = TRUE
            FROM task_assignments a
            WHERE r.assignment_id = a.id
              AND a.task_id = :tid
              AND r.is_approved = FALSE
            RETURNING r.id
        """), {"tid": task_id})
        db.commit()
        approved = result.rowcount
        logger.info(
            f"[EVENT_REPORT] approve-all: curator={user.email} "
            f"task={task_id} approved={approved}"
        )
        return {"success": True,
                "message": f"Одобрено {approved} отчётов",
                "approved": approved}
    except Exception as e:
        db.rollback()
        raise HTTPException(500, str(e))
