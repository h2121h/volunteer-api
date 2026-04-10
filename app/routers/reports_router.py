from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload
from datetime import datetime, timedelta
from app import models, auth
from app.database import get_db
from app.logger import logger

router = APIRouter(prefix="/api/reports", tags=["reports"])

REPORT_DEADLINE_HOURS = 48   # BR-02: принимается только 48ч после дедлайна
AUTO_APPROVE_HOURS    = 72   # BR-03: автоодобрение через 72ч


@router.post("/create")
def create_report_simple(
    assignment_id: int,
    hours: float,
    comment: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.volunteer_required),
):
    """POST /api/reports/create — простой отчёт без фото."""
    assignment = db.query(models.TaskAssignment).filter(
        models.TaskAssignment.id == assignment_id,
        models.TaskAssignment.user_id == current_user.id,
    ).first()
    if not assignment:
        raise HTTPException(403, "Назначение не найдено")

    # BR-02: проверяем дедлайн (48ч)
    task = assignment.task
    if task and task.event_date:
        deadline = datetime.combine(task.event_date, datetime.min.time()) + timedelta(hours=REPORT_DEADLINE_HOURS)
        if datetime.utcnow() > deadline:
            raise HTTPException(400, f"BR-02: отчёт принимается только в течение {REPORT_DEADLINE_HOURS}ч после мероприятия")

    report = models.TaskReport(
        assignment_id=assignment_id,
        user_id=current_user.id,
        hours=hours,
        comment=comment,
        is_approved=False,
    )
    db.add(report)
    db.commit()
    db.refresh(report)

    logger.info(f"[REPORT] volunteer={current_user.email} assignment={assignment_id} hours={hours}")

    return {"success": True, "id": report.id, "message": "Отчёт отправлен на проверку"}


@router.get("/my-reports")
def get_my_reports(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.volunteer_required),
):
    """GET /api/my-reports — свои отчёты."""
    reports = db.query(models.TaskReport).options(
        joinedload(models.TaskReport.assignment)
    ).filter(
        models.TaskReport.user_id == current_user.id
    ).all()

    return [
        {
            "id":            r.id,
            "assignment_id": r.assignment_id,
            "hours":         float(r.hours) if r.hours else 0,
            "comment":       r.comment,
            "photo_url":     r.photo_url,
            "is_approved":   r.is_approved,
            "submitted_at":  r.submitted_at,
        }
        for r in reports
    ]


@router.get("/pending")
def get_pending_reports(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.curator_required),
):
    """
    GET /api/reports/pending — отчёты на проверке.
    BR-03: куратор должен проверить в течение 72ч,
    иначе backend автоматически одобряет.
    """
    # Автоодобрение просроченных отчётов (BR-03)
    deadline = datetime.utcnow() - timedelta(hours=AUTO_APPROVE_HOURS)
    expired = db.query(models.TaskReport).filter(
        models.TaskReport.is_approved == False,
        models.TaskReport.submitted_at <= deadline,
    ).all()
    for r in expired:
        r.is_approved = True
        logger.info(f"[AUTO_APPROVE] BR-03: report={r.id} auto-approved after {AUTO_APPROVE_HOURS}h")
    if expired:
        db.commit()

    # Возвращаем оставшиеся pending
    reports = db.query(models.TaskReport).options(
        joinedload(models.TaskReport.user),
        joinedload(models.TaskReport.assignment),
    ).filter(
        models.TaskReport.is_approved == False
    ).all()

    return [
        {
            "id":            r.id,
            "user_id":       r.user_id,
            "user_name":     r.user.name if r.user else "—",
            "assignment_id": r.assignment_id,
            "hours":         float(r.hours) if r.hours else 0,
            "comment":       r.comment,
            "photo_url":     r.photo_url,
            "submitted_at":  r.submitted_at,
        }
        for r in reports
    ]


@router.post("/{report_id}/approve")
def approve_report(
    report_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.curator_required),
):
    """
    POST /api/reports/{report_id}/approve — одобрить отчёт.
    BR-09: баллы начисляются только после одобрения.
    BR-06: три подряд отклонения — предложить блокировку.
    """
    report = db.query(models.TaskReport).filter(
        models.TaskReport.id == report_id
    ).first()
    if not report:
        raise HTTPException(404, "Отчёт не найден")

    report.is_approved = True
    db.commit()

    logger.info(f"[APPROVE_REPORT] curator={current_user.email} report={report_id} user={report.user_id}")

    return {
        "success": True,
        "message": "Отчёт одобрен, волонтёру начислены баллы (BR-09)",
    }


@router.post("/{report_id}/reject")
def reject_report(
    report_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.curator_required),
):
    """
    POST /api/reports/{report_id}/reject — отклонить отчёт.
    BR-06: три подряд отклонения — предложить блокировку пользователя.
    """
    report = db.query(models.TaskReport).filter(
        models.TaskReport.id == report_id
    ).first()
    if not report:
        raise HTTPException(404, "Отчёт не найден")

    # Помечаем как отклонённый (не удаляем)
    report.is_approved = False
    report.comment = f"[REJECTED by {current_user.email}] {report.comment}"
    db.commit()

    # BR-06: считаем подряд идущие отклонения
    rejected_count = db.query(models.TaskReport).filter(
        models.TaskReport.user_id == report.user_id,
        models.TaskReport.is_approved == False,
        models.TaskReport.comment.like("[REJECTED%]"),
    ).count()

    warn_block = rejected_count >= 3

    logger.warning(
        f"[REJECT_REPORT] curator={current_user.email} report={report_id} "
        f"user={report.user_id} consecutive_rejected={rejected_count}"
    )

    return {
        "success":      True,
        "message":      "Отчёт отклонён",
        "warn_block":   warn_block,
        "warn_message": f"BR-06: {rejected_count} отклонения подряд — рекомендуется блокировка" if warn_block else None,
    }
