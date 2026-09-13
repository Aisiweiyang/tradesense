"""Shipment document pipeline: upload → extract → fields → rules → issues."""
from __future__ import annotations

import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import HTTPException, UploadFile
from sqlalchemy.orm import Session


from ..models import (AuditEvent, Document, DocumentField, Shipment,
                      ShipmentIssue)
from .doc_extractor import extract_pdf_fields
from .doc_rules import refresh_issues

ALLOWED_EXTENSIONS = {".pdf"}
MAX_UPLOAD_MB = 20


def _storage_dir(org_id: int, shipment_id: int) -> Path:
    """Files live under backend/data/documents (relative to backend CWD; gitignored)."""
    base = Path("data") / "documents" / str(org_id) / str(shipment_id)
    base.mkdir(parents=True, exist_ok=True)
    return base


def ingest_document(db: Session, org_id: int, shipment: Shipment,
                    upload: UploadFile, uploader_user_id: int | None) -> Document:
    filename = upload.filename or "document.pdf"
    ext = Path(filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=422, detail={
            "code": "bad_file_type", "message": "仅支持 PDF 单证文件"})
    content = upload.file.read()
    if len(content) > MAX_UPLOAD_MB * 1024 * 1024:
        raise HTTPException(status_code=413, detail={
            "code": "file_too_large", "message": f"文件超过 {MAX_UPLOAD_MB}MB 限制"})
    if len(content) < 100:
        raise HTTPException(status_code=422, detail={
            "code": "file_empty", "message": "文件内容为空或损坏"})

    doc_type_guess = _guess_doc_type(filename)
    existing = db.query(Document).filter_by(
        org_id=org_id, shipment_id=shipment.id, doc_type=doc_type_guess).count()
    version = existing + 1

    storage = _storage_dir(org_id, shipment.id)
    file_path = storage / f"{uuid.uuid4().hex}.pdf"
    file_path.write_bytes(content)

    doc = Document(org_id=org_id, shipment_id=shipment.id, doc_type=doc_type_guess,
                   version=version, file_path=str(file_path), original_filename=filename,
                   status="extracting", uploaded_by_user_id=uploader_user_id)
    db.add(doc)
    db.flush()

    try:
        outcome = extract_pdf_fields(str(file_path))
        doc.pages = outcome.pages
        doc.has_text_layer = outcome.has_text_layer
        if not outcome.has_text_layer:
            doc.status = "needs_manual"
            doc.extract_error = "未检测到文本层（扫描件/图片 PDF），请人工录入字段"
        elif not outcome.fields:
            doc.status = "needs_manual"
            doc.extract_error = "未识别到已知字段，请人工录入字段"
        else:
            for f in outcome.fields:
                db.add(DocumentField(
                    org_id=org_id, document_id=doc.id, field_name=f.field_name,
                    value=f.value, confidence=f.confidence,
                    evidence_page=f.evidence_page, evidence_text=f.evidence_text,
                    source="extracted"))
            doc.status = "extracted"
    except Exception as exc:  # noqa: BLE001 — pipeline failure must be visible & retryable
        doc.status = "failed"
        doc.extract_error = f"解析失败：{exc}"[:500]
    db.flush()

    refresh_issues(db, org_id, shipment, uploader_user_id)
    db.add(AuditEvent(org_id=org_id, user_id=uploader_user_id, action="document.upload",
                      entity_type="shipment", entity_id=str(shipment.id),
                      detail_json=f'{{"doc_type":"{doc.doc_type}","version":{version},'
                                  f'"status":"{doc.status}"}}'))
    db.flush()
    return doc


def _guess_doc_type(filename: str) -> str:
    n = filename.lower()
    for key, dtype in [
        ("invoice", "invoice"), ("发票", "invoice"),
        ("packing", "packing_list"), ("装箱", "packing_list"),
        ("bl", "bill_of_lading"), ("b_l", "bill_of_lading"), ("bill", "bill_of_lading"),
        ("提单", "bill_of_lading"), ("提单", "bill_of_lading"),
        ("customs", "customs_declaration"), ("cus", "customs_declaration"),
        ("报关", "customs_declaration"),
        ("lc", "letter_of_credit"), ("credit", "letter_of_credit"), ("信用证", "letter_of_credit"),
        ("origin", "origin_certificate"), ("产地", "origin_certificate"),
    ]:
        if key in n:
            return dtype
    return "other"


def manual_set_field(db: Session, org_id: int, field: DocumentField, value: str,
                     user_id: int | None) -> None:
    field.value = value
    field.source = "manual"
    field.confidence = 1.0
    field.modified_by_user_id = user_id
    field.evidence_text = field.evidence_text or "人工录入"
    db.flush()


def resolve_issue(db: Session, org_id: int, issue: ShipmentIssue, action: str,
                  note: str, actor_user_id: int | None,
                  target_field: DocumentField | None = None) -> ShipmentIssue:
    now = datetime.now(timezone.utc)
    if action == "adopt":
        if target_field is None:
            raise HTTPException(status_code=422, detail={
                "code": "no_target", "message": "该异常没有可自动修改的目标字段，请手动修改单证"})
        target_field.value = issue.expected_value
        target_field.source = "manual"
        target_field.confidence = 1.0
        target_field.modified_by_user_id = actor_user_id
        issue.status = "adopted"
        issue.resolution_note = note or "采纳系统建议值"
    elif action == "manual_fixed":
        issue.status = "manual_fixed"
        issue.resolution_note = note or "已人工修改单证"
    elif action == "ignore":
        if not (note or "").strip():
            raise HTTPException(status_code=422, detail={
                "code": "note_required", "message": "忽略异常必须填写理由"})
        issue.status = "ignored"
        issue.resolution_note = note
    elif action == "assign":
        raise HTTPException(status_code=422, detail={
            "code": "use_assign_endpoint", "message": "指派请使用 assign 接口"})
    else:
        raise HTTPException(status_code=422, detail={
            "code": "bad_action", "message": f"未知操作 {action}"})
    issue.handler_user_id = actor_user_id
    if issue.status in ("adopted", "manual_fixed"):
        issue.resolved_at = now
        # NOTE: no immediate refresh here — the adopted record must survive as
        # audit trail; stale open issues are cleaned on the next recheck.
    db.flush()
    return issue
