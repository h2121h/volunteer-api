from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func
from app import models, auth
from app.database import get_db

router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.get("/summary")
def get_analytics_summary(
        db: Session = Depends(get_db),
        current_user: models.User = Depends(auth.curator_required)
):
    avg_hours = db.query(func.avg(models.TaskReport.hours_spent)).filter(
        models.TaskReport.status == "approved"
    ).scalar() or 0

    return {
        "total_volunteers": db.query(models.User).join(models.Role).filter(models.Role.code == "volunteer").count(),
        "active_tasks": db.query(models.Task).filter(models.Task.status == "open").count(),
        "completed_reports": db.query(models.TaskReport).filter(models.TaskReport.status == "approved").count(),
        "pending_reports": db.query(models.TaskReport).filter(models.TaskReport.status == "submitted").count(),
        "avg_hours_per_task": avg_hours
    }