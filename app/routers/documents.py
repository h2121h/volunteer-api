from fastapi import APIRouter, Depends, UploadFile, File, HTTPException
from sqlalchemy.orm import Session
from datetime import datetime
import os
import uuid
from app import models, auth
from app.database import get_db

router = APIRouter(prefix="/documents", tags=["documents"])

UPLOAD_DIR = "media/documents"
os.makedirs(UPLOAD_DIR, exist_ok=True)


@router.post("/upload")
async def upload_document(
    doc_type: str,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.volunteer_required),
):
    allowed_extensions = ('.pdf', '.jpg', '.jpeg', '.png')
    if not any(file.filename.lower().endswith(ext) for ext in allowed_extensions):
        raise HTTPException(400, "Только PDF/JPG/PNG")

    ext = os.path.splitext(file.filename)[1].lower()
    filename = f"{current_user.id}_{uuid.uuid4().hex}{ext}"
    filepath = os.path.join(UPLOAD_DIR, filename)

    content = await file.read()
    with open(filepath, "wb") as f:
        f.write(content)

    doc = models.VolunteerDocument(
        user_id=current_user.id,
        doc_type=doc_type,
        file_url=f"/media/documents/{filename}",
        status="new",
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)
    return {"success": True, "id": doc.id, "file_url": doc.file_url}


@router.post("/{doc_id}/verify")
def verify_document(
    doc_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.curator_required),
):
    doc = db.query(models.VolunteerDocument).filter(
        models.VolunteerDocument.id == doc_id
    ).first()
    if not doc:
        raise HTTPException(404, "Документ не найден")

    doc.status = "verified"
    doc.verified_at = datetime.utcnow()
    doc.verified_by = current_user.id
    db.commit()
    return {"success": True, "message": "Документ верифицирован"}