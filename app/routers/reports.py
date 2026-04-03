from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException
from sqlalchemy.orm import Session
import os
import uuid
from app import models, auth
from app.database import get_db

router = APIRouter(prefix="/reports", tags=["reports"])

UPLOAD_DIR = "media/reports"
os.makedirs(UPLOAD_DIR, exist_ok=True)


@router.post("/")
async def create_report(
    task_id: int = Form(...),
    comment: str = Form(...),
    hours: float = Form(...),
    photos: list[UploadFile] = File(None),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.volunteer_required),
):
    assignment = db.query(models.TaskAssignment).filter(
        models.TaskAssignment.task_id == task_id,
        models.TaskAssignment.user_id == current_user.id,
    ).first()
    if not assignment:
        raise HTTPException(403, "Вы не назначены на эту задачу")

    photo_urls = []
    if photos:
        for photo in photos:
            ext = os.path.splitext(photo.filename)[1].lower()
            filename = f"report_{task_id}_{uuid.uuid4().hex}{ext}"
            path = os.path.join(UPLOAD_DIR, filename)
            content_bytes = await photo.read()
            with open(path, "wb") as f:
                f.write(content_bytes)
            photo_urls.append(f"/media/reports/{filename}")

    report = models.TaskReport(
        assignment_id=assignment.id,
        user_id=current_user.id,
        comment=comment,
        hours=hours,
        photo_url=",".join(photo_urls) if photo_urls else None,
        is_approved=False,
    )
    db.add(report)
    db.commit()
    db.refresh(report)
    return {"success": True, "id": report.id, "message": "Отчёт отправлен на проверку"}