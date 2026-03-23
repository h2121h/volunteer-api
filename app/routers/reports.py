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
    content: str = Form(...),
    hours_spent: float = Form(...),
    geo_lat: float = Form(None),
    geo_lon: float = Form(None),
    photos: list[UploadFile] = File(None),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.volunteer_required)
):
    assignment = db.query(models.TaskAssignment).filter(
        models.TaskAssignment.task_id == task_id,
        models.TaskAssignment.user_id == current_user.id
    ).first()
    if not assignment:
        raise HTTPException(403, "Вы не назначены на эту задачу")

    photo_urls = []
    if photos:
        for photo in photos:
            ext = os.path.splitext(photo.filename)[1].lower()
            filename = f"report_{task_id}_{uuid.uuid4().hex}{ext}"
            path = os.path.join(UPLOAD_DIR, filename)
            content_file = await photo.read()
            with open(path, "wb") as f:
                f.write(content_file)
            photo_urls.append(f"/media/reports/{filename}")

    report = models.TaskReport(
        task_id=task_id,
        user_id=current_user.id,
        content=content,
        hours_spent=hours_spent,
        photos=",".join(photo_urls) if photo_urls else None,
        status="submitted"
    )
    db.add(report)
    db.commit()
    return {"success": True, "id": report.id, "message": "Отчёт отправлен"}