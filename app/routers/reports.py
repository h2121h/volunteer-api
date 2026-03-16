from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from app import schemas, models, auth
from app.database import get_db

router = APIRouter(prefix="/api/reports", tags=["reports"])

@router.post("/", response_model=schemas.ReportResponse)
def create_report(
    report: schemas.ReportCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user)
):
    db_report = models.TaskReport(
        **report.dict(),
        user_id=current_user.id
    )
    db.add(db_report)
    db.commit()
    db.refresh(db_report)
    return db_report

@router.get("/task/{task_id}", response_model=List[schemas.ReportResponse])
def get_task_reports(
    task_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user)
):
    reports = db.query(models.TaskReport).filter(models.TaskReport.task_id == task_id).all()
    return reports