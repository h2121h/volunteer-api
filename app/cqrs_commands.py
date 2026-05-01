"""
CQRS — Command side (запись).

Все команды меняют состояние БД.
Работают через ORM (нормализованная write-модель).
Каждая команда после выполнения публикует Domain Event в Redis.

4.1.1 Разделение на Command/Query
4.3.1 Domain Event
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional
from datetime import datetime
import json

from app import models, auth
from app.database import get_db

try:
    import redis as redis_lib
    _redis = redis_lib.Redis(host='localhost', port=6379, db=0, decode_responses=True)
    _redis.ping()
    REDIS_OK = True
except Exception:
    REDIS_OK = False

router = APIRouter(prefix="/cmd", tags=["CQRS Commands"])


# ── Domain Event Publisher ────────────────────────────────────────────────────

def publish_event(event_type: str, payload: dict):
    """
    4.3.1 Domain Event: публикуем событие в Redis channel.
    Подписчики (например, уведомления) реагируют асинхронно.
    """
    if not REDIS_OK:
        return
    event = {
        "type":      event_type,
        "payload":   payload,
        "timestamp": datetime.utcnow().isoformat(),
    }
    try:
        _redis.publish("volunteer:events", json.dumps(event))
        _redis.lpush("volunteer:event_log", json.dumps(event))
        _redis.ltrim("volunteer:event_log", 0, 499)  # храним последние 500
    except Exception:
        pass


# ── DTOs (Write-модели) ───────────────────────────────────────────────────────

class ApplyTaskCommand(BaseModel):
    message: Optional[str] = "Хочу помочь!"


class SubmitReportCommand(BaseModel):
    assignment_id: int
    hours:         float
    comment:       str


class CompleteTaskCommand(BaseModel):
    pass


class ApproveApplicationCommand(BaseModel):
    pass


class RejectApplicationCommand(BaseModel):
    reason: Optional[str] = ""


class ApproveReportCommand(BaseModel):
    pass


class RejectReportCommand(BaseModel):
    reason: Optional[str] = ""


# ── Commands ──────────────────────────────────────────────────────────────────

@router.post("/tasks/{task_id}/apply")
def cmd_apply_task(
    task_id: int,
    body:    ApplyTaskCommand,
    db:      Session = Depends(get_db),
    user:    models.User = Depends(auth.volunteer_required),
):
    """
    Command: записаться на задачу.
    BR-01: лимит участников.
    BR-05: конфликт расписания.
    Публикует событие ApplicationCreated.
    """
    task = db.query(models.Task).filter(models.Task.id == task_id).first()
    if not task:
        raise HTTPException(404, "Задача не найдена")
    if task.status != "open":
        raise HTTPException(400, "Задача недоступна")

    # BR-01
    count = db.query(models.TaskApplication).filter(
        models.TaskApplication.task_id == task_id,
        models.TaskApplication.status.in_(["created", "active"]),
    ).count()
    if count >= task.needed_people:
        raise HTTPException(400, detail={"code": "BR-01", "message": "Лимит участников достигнут"})

    # BR-05
    conflict = db.query(models.TaskApplication).join(models.Task).filter(
        models.TaskApplication.user_id == user.id,
        models.TaskApplication.status.in_(["created", "active"]),
        models.Task.event_date == task.event_date,
        models.Task.id != task_id,
    ).first()
    if conflict:
        raise HTTPException(400, detail={"code": "BR-05", "message": "Конфликт расписания"})

    # Уже записан?
    existing = db.query(models.TaskApplication).filter(
        models.TaskApplication.task_id == task_id,
        models.TaskApplication.user_id == user.id,
    ).first()
    if existing:
        raise HTTPException(400, "Вы уже подали заявку")

    app = models.TaskApplication(
        task_id=task_id, user_id=user.id,
        message=body.message, status="created",
    )
    db.add(app)
    db.commit()

    # Domain Event
    publish_event("ApplicationCreated", {
        "application_id": app.id,
        "task_id":        task_id,
        "task_title":     task.title,
        "user_id":        user.id,
        "user_name":      user.name,
    })

    return {"success": True, "application_id": app.id,
            "message": "Заявка подана! Ожидайте одобрения куратора"}


@router.post("/applications/{app_id}/approve")
def cmd_approve_application(
    app_id: int,
    db:     Session = Depends(get_db),
    user:   models.User = Depends(auth.curator_required),
):
    """Command: одобрить заявку. Публикует ApplicationApproved."""
    application = db.query(models.TaskApplication).filter(
        models.TaskApplication.id == app_id
    ).first()
    if not application:
        raise HTTPException(404, "Заявка не найдена")

    application.status = "active"
    db.commit()

    publish_event("ApplicationApproved", {
        "application_id": app_id,
        "task_id":        application.task_id,
        "user_id":        application.user_id,
        "curator_id":     user.id,
    })

    return {"success": True, "message": "Заявка одобрена"}


@router.post("/applications/{app_id}/reject")
def cmd_reject_application(
    app_id: int,
    body:   RejectApplicationCommand,
    db:     Session = Depends(get_db),
    user:   models.User = Depends(auth.curator_required),
):
    """Command: отклонить заявку. Публикует ApplicationRejected."""
    application = db.query(models.TaskApplication).filter(
        models.TaskApplication.id == app_id
    ).first()
    if not application:
        raise HTTPException(404, "Заявка не найдена")

    application.status = "rejected"
    db.commit()

    publish_event("ApplicationRejected", {
        "application_id": app_id,
        "user_id":        application.user_id,
        "reason":         body.reason,
    })

    return {"success": True, "message": "Заявка отклонена"}


@router.post("/reports/{report_id}/approve")
def cmd_approve_report(
    report_id: int,
    db:        Session = Depends(get_db),
    user:      models.User = Depends(auth.curator_required),
):
    """Command: одобрить отчёт. BR-09: начисляем баллы. Публикует ReportApproved."""
    report = db.query(models.TaskReport).filter(
        models.TaskReport.id == report_id
    ).first()
    if not report:
        raise HTTPException(404, "Отчёт не найден")

    report.is_approved = True
    # BR-09: сохраняем баллы в БД (hours * 10 по умолчанию)
    if not (hasattr(report, 'points') and report.points):
        report.points = int(float(report.hours or 0) * 10)
    db.commit()

    # Инвалидируем кэш волонтёра (5.2.3)
    if REDIS_OK:
        cache_key = f"volunteer:dashboard:{report.user_id}"
        try:
            _redis.delete(cache_key)
        except Exception:
            pass

    points = report.points if hasattr(report, 'points') and report.points else int(float(report.hours or 0) * 10)
    publish_event("ReportApproved", {
        "report_id":  report_id,
        "user_id":    report.user_id,
        "hours":      float(report.hours or 0),
        "points":     points,
        "curator_id": user.id,
    })

    return {"success": True, "message": f"Отчёт принят, начислено {points} баллов"}


@router.post("/reports/{report_id}/reject")
def cmd_reject_report(
    report_id: int,
    body:      RejectReportCommand,
    db:        Session = Depends(get_db),
    user:      models.User = Depends(auth.curator_required),
):
    """Command: отклонить отчёт. Публикует ReportRejected."""
    report = db.query(models.TaskReport).filter(
        models.TaskReport.id == report_id
    ).first()
    if not report:
        raise HTTPException(404, "Отчёт не найден")

    report.is_approved = False
    # Помечаем как отклонённый — удаляем из БД чтобы волонтёр мог подать новый
    db.delete(report)
    db.commit()

    publish_event("ReportRejected", {
        "report_id": report_id,
        "user_id":   report.user_id,
        "reason":    body.reason,
    })

    return {"success": True, "message": "Отчёт отклонён"}
