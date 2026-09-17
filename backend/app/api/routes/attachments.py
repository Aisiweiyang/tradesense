"""Inquiry attachments: PDF/images uploaded for AI Intake context."""
from __future__ import annotations

import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ...database import get_db
from ...deps import OrgScope, get_scope
from ...models import Inquiry, InquiryAttachment
from ...services.audit import audit

router = APIRouter(prefix="/inquiries/{inquiry_id}/attachments", tags=["attachments"])

ALLOWED = {".pdf", ".png", ".jpg", ".jpeg", ".webp"}
MAX_MB = 10


def _dir(org_id: int, inquiry_id: int) -> Path:
    d = Path("data/attachments") / str(org_id) / str(inquiry_id)
    d.mkdir(parents=True, exist_ok=True)
    return d


def _inquiry(db: Session, org_id: int, inquiry_id: int) -> Inquiry:
    inq = db.scalar(select(Inquiry).where(
        Inquiry.org_id == org_id, Inquiry.id == inquiry_id))
    if inq is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND,
                            detail={"code": "not_found", "message": "询盘不存在"})
    return inq


@router.post("", status_code=201)
async def upload(inquiry_id: int, file: UploadFile,
                 scope: OrgScope = Depends(get_scope), db: Session = Depends(get_db)):
    _inquiry(db, scope.org_id, inquiry_id)
    filename = file.filename or "attachment"
    ext = Path(filename).suffix.lower()
    if ext not in ALLOWED:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail={
            "code": "bad_file_type", "message": "仅支持 PDF / PNG / JPG / WEBP"})
    content = file.file.read()
    if len(content) > MAX_MB * 1024 * 1024:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail={
            "code": "file_too_large", "message": f"文件超过 {MAX_MB}MB 限制"})
    if len(content) < 50:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail={
            "code": "file_empty", "message": "文件内容为空或损坏"})

    path = _dir(scope.org_id, inquiry_id) / f"{uuid.uuid4().hex}{ext}"
    path.write_bytes(content)

    text, st = "", "needs_manual"
    if ext == ".pdf":
        from ...services.doc_extractor import extract_pdf_fields
        try:
            outcome = extract_pdf_fields(str(path))
            if outcome.has_text_layer:
                text, st = outcome.text_head, "extracted"
        except Exception:  # noqa: BLE001 — 损坏文件降级为人工
            pass
    # 图片/扫描件的视觉提取由 AI Intake 在 run_intake 外按 provider 能力处理；
    # 无 AI 时保持 needs_manual，不阻塞上传。

    att = InquiryAttachment(
        org_id=scope.org_id, inquiry_id=inquiry_id, file_path=str(path),
        original_filename=filename, media_type=file.content_type or "",
        size=len(content), extracted_text=text, status=st,
        uploaded_by_user_id=scope.user.id)
    db.add(att)
    db.flush()
    audit(db, scope.org_id, scope.user.id, "attachment.upload", "inquiry", inquiry_id,
          {"file": filename, "status": st})
    ai_summary = None
    if st == "extracted":
        try:
            from ...services.ai.runner import run_intake
            ai_summary = run_intake(db, scope.org_id, _inquiry(db, scope.org_id, inquiry_id),
                                    scope.user.id)
        except Exception:  # noqa: BLE001
            pass
    db.commit()
    return {"id": att.id, "original_filename": att.original_filename,
            "media_type": att.media_type, "size": att.size, "status": att.status,
            "ai_intake": ai_summary}


@router.get("")
def list_attachments(inquiry_id: int, scope: OrgScope = Depends(get_scope),
                     db: Session = Depends(get_db)):
    _inquiry(db, scope.org_id, inquiry_id)
    rows = db.scalars(select(InquiryAttachment).where(
        InquiryAttachment.org_id == scope.org_id,
        InquiryAttachment.inquiry_id == inquiry_id).order_by(InquiryAttachment.id)).all()
    return {"items": [{"id": a.id, "original_filename": a.original_filename,
                       "media_type": a.media_type, "size": a.size, "status": a.status}
                      for a in rows]}


@router.delete("/{attachment_id}", status_code=204)
def remove(inquiry_id: int, attachment_id: int, scope: OrgScope = Depends(get_scope),
           db: Session = Depends(get_db)):
    _inquiry(db, scope.org_id, inquiry_id)
    att = db.scalar(select(InquiryAttachment).where(
        InquiryAttachment.org_id == scope.org_id,
        InquiryAttachment.id == attachment_id,
        InquiryAttachment.inquiry_id == inquiry_id))
    if att is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND,
                            detail={"code": "not_found", "message": "附件不存在"})
    try:
        Path(att.file_path).unlink(missing_ok=True)
    except OSError:
        pass
    db.delete(att)
    audit(db, scope.org_id, scope.user.id, "attachment.delete", "inquiry", inquiry_id,
          {"file": att.original_filename})
    db.commit()
    return None
