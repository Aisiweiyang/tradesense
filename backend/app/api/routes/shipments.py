"""Shipment workbench API: 货件 CRUD、单证上传、字段对照、异常处理、催补邮件。"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, joinedload

from ...database import get_db
from ...deps import OrgScope, get_scope, order_by, paginate
from ...models import (AuditEvent, Customer, Document, DocumentField,
                       ReplyDraft, Shipment, ShipmentIssue, User)
from ...schemas import ORMModel
from ...services.audit import audit
from ...services.doc_rules import RULE_LABELS, refresh_issues, rule_enabled
from ...services.doc_service import ingest_document, manual_set_field, resolve_issue

router = APIRouter(prefix="/shipments", tags=["shipments"])


def _shipment(db: Session, scope: OrgScope, shipment_id: int) -> Shipment:
    obj = db.scalar(select(Shipment).where(
        Shipment.org_id == scope.org_id, Shipment.id == shipment_id))
    if obj is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND,
                            detail={"code": "not_found", "message": "货件不存在"})
    return obj


def _issue_counts(db: Session, scope: OrgScope, shipment_id: int) -> dict:
    rows = db.execute(
        select(ShipmentIssue.severity, func.count(ShipmentIssue.id)).where(
            ShipmentIssue.org_id == scope.org_id,
            ShipmentIssue.shipment_id == shipment_id,
            ShipmentIssue.status == "open").group_by(ShipmentIssue.severity)).all()
    counts = {sev: n for sev, n in rows}
    return {"open_total": sum(counts.values()),
            "high": counts.get("high", 0), "medium": counts.get("medium", 0),
            "low": counts.get("low", 0)}


def _dump(db: Session, scope: OrgScope, s: Shipment, with_lists: bool = False) -> dict:
    data = {
        "id": s.id, "shipment_no": s.shipment_no, "order_no": s.order_no,
        "transport_mode": s.transport_mode, "status": s.status,
        "port_of_loading": s.port_of_loading, "port_of_discharge": s.port_of_discharge,
        "incoterm": s.incoterm, "etd": s.etd.isoformat() if s.etd else None,
        "cutoff_at": s.cutoff_at.isoformat() if s.cutoff_at else None,
        "customer_id": s.customer_id, "inquiry_id": s.inquiry_id,
        "notes": s.notes, "required_docs_json": s.required_docs_json,
        "created_at": s.created_at.isoformat(),
    }
    if s.customer_id:
        c = db.get(Customer, s.customer_id)
        data["customer_name"] = c.company_name if c else ""
    else:
        data["customer_name"] = ""
    counts = _issue_counts(db, scope, s.id)
    data.update(counts)
    if counts["open_total"] and counts["high"] > 0:
        data["risk"] = "high"
    elif counts["open_total"]:
        data["risk"] = "medium"
    else:
        data["risk"] = "none"
    if with_lists:
        docs = db.scalars(select(Document).where(
            Document.org_id == scope.org_id, Document.shipment_id == s.id)
            .order_by(Document.doc_type, Document.version.desc())).all()
        data["documents"] = [{
            "id": d.id, "doc_type": d.doc_type, "version": d.version,
            "status": d.status, "original_filename": d.original_filename,
            "pages": d.pages, "has_text_layer": d.has_text_layer,
            "extract_error": d.extract_error,
        } for d in docs]
        issues = db.scalars(select(ShipmentIssue).where(
            ShipmentIssue.org_id == scope.org_id, ShipmentIssue.shipment_id == s.id)
            .order_by(ShipmentIssue.status, ShipmentIssue.id)).all()
        data["issues"] = [_dump_issue(i) for i in issues]
    return data


def _dump_issue(i: ShipmentIssue) -> dict:
    return {
        "id": i.id, "severity": i.severity, "issue_type": i.issue_type,
        "rule_code": i.rule_code, "title": i.title,
        "expected_value": i.expected_value, "actual_value": i.actual_value,
        "evidence": json.loads(i.evidence_json or "[]"),
        "status": i.status, "assigned_to_user_id": i.assigned_to_user_id,
        "resolution_note": i.resolution_note,
    }


@router.get("/rules")
def list_rules(scope: OrgScope = Depends(get_scope), db: Session = Depends(get_db),
               customer_id: int = 0):
    from ...models import DocRuleConfig

    rows = db.scalars(select(DocRuleConfig).where(
        DocRuleConfig.org_id == scope.org_id)).all()
    cid = customer_id or None
    out = []
    for code, label in RULE_LABELS.items():
        enabled, params = rule_enabled(db, scope.org_id, cid, code)
        overrides = [r for r in rows if r.rule_code == code
                     and (r.customer_id is None or r.customer_id == cid)]
        out.append({"rule_code": code, "label": label, "enabled": enabled,
                    "params": params, "has_override": bool(overrides)})
    return {"items": out}


@router.put("/rules/{rule_code}")
def set_rule(rule_code: str, body: dict, scope: OrgScope = Depends(get_scope),
             db: Session = Depends(get_db)):
    from ...models import DocRuleConfig

    if rule_code not in RULE_LABELS:
        raise HTTPException(status.HTTP_404_NOT_FOUND,
                            detail={"code": "not_found", "message": "未知规则"})
    customer_id = body.get("customer_id")
    row = db.scalar(select(DocRuleConfig).where(
        DocRuleConfig.org_id == scope.org_id, DocRuleConfig.rule_code == rule_code,
        DocRuleConfig.customer_id == (customer_id or None)))
    if row is None:
        row = DocRuleConfig(org_id=scope.org_id, rule_code=rule_code,
                            customer_id=customer_id or None)
        db.add(row)
    row.enabled = bool(body.get("enabled", True))
    row.params_json = json.dumps(body.get("params") or {})
    row.updated_by_user_id = scope.user.id
    audit(db, scope.org_id, scope.user.id, "doc_rule.update", "doc_rule", rule_code,
          {"enabled": row.enabled, "customer_id": customer_id})
    db.commit()
    return {"rule_code": rule_code, "enabled": row.enabled, "params": row.params_json}


@router.get("")
def list_shipments(scope: OrgScope = Depends(get_scope), db: Session = Depends(get_db),
                   pg: dict = Depends(paginate), q: str = Query("", max_length=100),
                   risk: str = Query("", pattern="^(high|medium|none|)$"),
                   status_filter: str = Query("", alias="status")):
    stmt = select(Shipment).where(Shipment.org_id == scope.org_id)
    if q:
        like = f"%{q}%"
        stmt = stmt.where(or_(Shipment.shipment_no.ilike(like), Shipment.order_no.ilike(like),
                              Shipment.port_of_discharge.ilike(like),
                              Shipment.port_of_loading.ilike(like)))
    if status_filter:
        stmt = stmt.where(Shipment.status == status_filter)
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(stmt.order_by(order_by(Shipment, pg["sort"]))
                      .offset((pg["page"] - 1) * pg["page_size"]).limit(pg["page_size"])).all()
    items = sorted(([_dump(db, scope, s) for s in rows]),
                   key=lambda x: ({"high": 0, "medium": 1, "none": 2}.get(x["risk"], 3), -x["id"]))
    if risk:
        items = [x for x in items if x["risk"] == risk]
    return {"items": items, "total": total, "page": pg["page"], "page_size": pg["page_size"]}


class ShipmentIn(ORMModel):
    pass


@router.post("", status_code=201)
def create_shipment(body: dict, scope: OrgScope = Depends(get_scope),
                    db: Session = Depends(get_db)):
    def _parse_dt(v):
        if not v:
            return None
        try:
            return datetime.fromisoformat(str(v).replace("Z", "+00:00"))
        except ValueError:
            return None

    s = Shipment(
        org_id=scope.org_id,
        shipment_no=f"SH-{datetime.now(timezone.utc).strftime('%Y%m%d')}-{db.scalar(select(func.count(Shipment.id)).where(Shipment.org_id == scope.org_id)) + 1:04d}",
        customer_id=body.get("customer_id"), order_no=body.get("order_no", ""),
        transport_mode=body.get("transport_mode", "sea"),
        port_of_loading=body.get("port_of_loading", ""),
        port_of_discharge=body.get("port_of_discharge", ""),
        incoterm=body.get("incoterm", "FOB"),
        etd=_parse_dt(body.get("etd")), cutoff_at=_parse_dt(body.get("cutoff_at")),
        owner_user_id=scope.user.id,
        required_docs_json=json.dumps(body.get("required_docs")
                                      if body.get("required_docs") is not None
                                      else ["invoice", "packing_list", "bill_of_lading"]),
        notes=body.get("notes", ""),
    )
    if body.get("inquiry_id"):
        s.inquiry_id = body["inquiry_id"]
    db.add(s)
    db.flush()
    refresh_issues(db, scope.org_id, s, scope.user.id)
    audit(db, scope.org_id, scope.user.id, "shipment.create", "shipment", s.id,
          {"shipment_no": s.shipment_no})
    db.commit()
    return _dump(db, scope, s)


@router.get("/{shipment_id}")
def get_shipment(shipment_id: int, scope: OrgScope = Depends(get_scope),
                 db: Session = Depends(get_db)):
    s = _shipment(db, scope, shipment_id)
    data = _dump(db, scope, s, with_lists=True)
    users = {u.id: u.name for u in db.scalars(select(User).where(User.org_id == scope.org_id)).all()}
    for i in data["issues"]:
        i["assigned_to"] = users.get(i["assigned_to_user_id"], "")
    return data


@router.patch("/{shipment_id}")
def update_shipment(shipment_id: int, body: dict, scope: OrgScope = Depends(get_scope),
                    db: Session = Depends(get_db)):
    s = _shipment(db, scope, shipment_id)
    for k in ("order_no", "transport_mode", "port_of_loading", "port_of_discharge",
              "incoterm", "status", "notes"):
        if k in body:
            setattr(s, k, body[k])
    if "required_docs" in body:
        s.required_docs_json = json.dumps(body["required_docs"])
    audit(db, scope.org_id, scope.user.id, "shipment.update", "shipment", s.id,
          {"fields": [k for k in body]})
    db.commit()
    return _dump(db, scope, s)


@router.post("/{shipment_id}/documents", status_code=201)
def upload_document(shipment_id: int, file: UploadFile = File(...),
                    scope: OrgScope = Depends(get_scope), db: Session = Depends(get_db)):
    s = _shipment(db, scope, shipment_id)
    doc = ingest_document(db, scope.org_id, s, file, scope.user.id)
    audit(db, scope.org_id, scope.user.id, "document.upload", "document", doc.id,
          {"doc_type": doc.doc_type, "status": doc.status})
    db.commit()
    return {"id": doc.id, "doc_type": doc.doc_type, "version": doc.version,
            "status": doc.status, "extract_error": doc.extract_error,
            "pages": doc.pages, "has_text_layer": doc.has_text_layer}


@router.get("/documents/{document_id}/file")
def get_document_file(document_id: int, request: Request,
                      access_token: str = Query("", alias="access_token"),
                      db: Session = Depends(get_db)):
    """PDF preview for iframes. Accepts the JWT via Authorization header OR
    `?access_token=` (browser viewers cannot set headers). Org-scoped either way."""
    from fastapi.responses import FileResponse

    from ...security import decode_token

    token = access_token or request.headers.get("authorization", "").removeprefix("Bearer ")
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED,
                            detail={"code": "unauthorized", "message": "缺少访问令牌"})
    try:
        org_id = int(decode_token(token)["org_id"])
    except Exception:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED,
                            detail={"code": "invalid_token", "message": "令牌无效或已过期"})
    doc = db.scalar(select(Document).where(Document.org_id == org_id,
                                           Document.id == document_id))
    if doc is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND,
                            detail={"code": "not_found", "message": "单证不存在"})
    from pathlib import Path
    path = Path(doc.file_path)
    if not path.exists():
        raise HTTPException(status.HTTP_404_NOT_FOUND,
                            detail={"code": "file_missing", "message": "文件已丢失，请重新上传"})
    return FileResponse(path, media_type="application/pdf", filename=doc.original_filename)


@router.get("/{shipment_id}/fields")
def get_fields(shipment_id: int, scope: OrgScope = Depends(get_scope),
               db: Session = Depends(get_db)):
    s = _shipment(db, scope, shipment_id)
    rows = db.scalars(select(DocumentField).join(Document).where(
        DocumentField.org_id == scope.org_id, Document.shipment_id == s.id)
        .order_by(DocumentField.field_name, DocumentField.document_id)).all()
    return {"items": [{
        "id": f.id, "document_id": f.document_id, "doc_type": f.document.doc_type,
        "field_name": f.field_name, "value": f.value, "confidence": f.confidence,
        "evidence_page": f.evidence_page, "evidence_text": f.evidence_text,
        "source": f.source,
    } for f in rows]}


@router.patch("/fields/{field_id}")
def set_field(field_id: int, body: dict, scope: OrgScope = Depends(get_scope),
              db: Session = Depends(get_db)):
    f = db.scalar(select(DocumentField).where(DocumentField.org_id == scope.org_id,
                                              DocumentField.id == field_id))
    if f is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND,
                            detail={"code": "not_found", "message": "字段不存在"})
    if not (body.get("value") or "").strip():
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            detail={"code": "empty_value", "message": "字段值不能为空"})
    manual_set_field(db, scope.org_id, f, body["value"].strip(), scope.user.id)
    shipment = db.get(Shipment, f.document.shipment_id)
    refresh_issues(db, scope.org_id, shipment, scope.user.id)
    audit(db, scope.org_id, scope.user.id, "document.field.manual_set", "document_field", f.id,
          {"field": f.field_name})
    db.commit()
    return {"id": f.id, "value": f.value, "source": f.source}


@router.post("/{shipment_id}/recheck")
def recheck(shipment_id: int, scope: OrgScope = Depends(get_scope),
            db: Session = Depends(get_db)):
    s = _shipment(db, scope, shipment_id)
    created = refresh_issues(db, scope.org_id, s, scope.user.id)
    audit(db, scope.org_id, scope.user.id, "shipment.recheck", "shipment", s.id,
          {"new_issues": created})
    db.commit()
    data = _dump(db, scope, s, with_lists=True)
    return {**data, "new_issues": created}


def _get_issue(db: Session, scope: OrgScope, issue_id: int) -> ShipmentIssue:
    issue = db.scalar(select(ShipmentIssue).where(
        ShipmentIssue.org_id == scope.org_id, ShipmentIssue.id == issue_id))
    if issue is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND,
                            detail={"code": "not_found", "message": "异常不存在"})
    return issue


@router.post("/issues/{issue_id}/action")
def issue_action(issue_id: int, body: dict, scope: OrgScope = Depends(get_scope),
                 db: Session = Depends(get_db)):
    issue = _get_issue(db, scope, issue_id)
    action = body.get("action", "")
    if action == "assign":
        issue.assigned_to_user_id = body.get("user_id")
        db.commit()
        return _dump_issue(issue)
    # find the actual-value target field for "adopt"
    target_field = None
    if action == "adopt":
        evidence = json.loads(issue.evidence_json or "[]")
        actual = next((e for e in evidence if e.get("value") == issue.actual_value
                       and e.get("doc_id")), None)
        if actual and actual.get("field"):
            doc = db.get(Document, actual["doc_id"])
            if doc:
                target_field = db.scalar(select(DocumentField).where(
                    DocumentField.document_id == doc.id,
                    DocumentField.field_name == actual["field"]))
    issue = resolve_issue(db, scope.org_id, issue, action, body.get("note", ""),
                          scope.user.id, target_field)
    audit(db, scope.org_id, scope.user.id, "shipment.issue." + action, "shipment_issue",
          issue.id, {"rule": issue.rule_code})
    db.commit()
    return _dump_issue(issue)




@router.post("/{shipment_id}/chase-email", status_code=201)
def chase_email(shipment_id: int, body: dict = None, scope: OrgScope = Depends(get_scope),
                db: Session = Depends(get_db)):
    """生成催补/改单邮件草稿：逐条引用异常 + 缺失清单 + 截止时间（人工发送）。"""
    s = _shipment(db, scope, shipment_id)
    issues = db.scalars(select(ShipmentIssue).where(
        ShipmentIssue.org_id == scope.org_id, ShipmentIssue.shipment_id == s.id,
        ShipmentIssue.status.in_(["open", "adopted", "manual_fixed"]))).all()
    try:
        required = set(json.loads(s.required_docs_json or "[]"))
    except json.JSONDecodeError:
        required = set()
    uploaded = set(db.scalars(select(Document.doc_type).where(
        Document.org_id == scope.org_id, Document.shipment_id == s.id)).all())
    missing = sorted(required - uploaded)

    ref = s.shipment_no
    lines_en, lines_zh = [], []
    for i in issues:
        if i.issue_type == "missing":
            continue
        lines_en.append(f"- {i.title} (expected: {i.expected_value}; found: {i.actual_value})")
        lines_zh.append(f"- {i.title}（期望：{i.expected_value}；实际：{i.actual_value}）")
    if missing:
        lines_en.append("- Missing documents: " + ", ".join(missing))
        lines_zh.append("- 缺失单证：" + "、".join(missing))
    has_items = bool(lines_en)
    if s.cutoff_at:
        deadline = s.cutoff_at.strftime("%Y-%m-%d %H:%M UTC")
        lines_en.append(f"- Document cutoff: {deadline}. Please reply before the cutoff.")
        lines_zh.append(f"- 截单时间：{deadline}，请在截单前回复确认。")

    body_en = ("Dear partner,\n\nDuring document verification for shipment "
               f"{ref}, we found the following items that need your attention:\n\n"
               + ("\n".join(lines_en) if has_items else "- No open items. Thank you!")
               + "\n\nPlease revise and resend the affected documents at your earliest "
                 "convenience.\n\nBest regards,\nTradeSense on behalf of the sales team")
    body_zh = ("尊敬的合作伙伴：\n\n货件 " + ref + " 单证核对时发现以下需要处理的问题：\n\n"
               + ("\n".join(lines_zh) if has_items else "- 暂无待处理问题。")
               + "\n\n请尽快修改并重新提供相关单证。\n\n谢谢！")

    draft = ReplyDraft(
        org_id=scope.org_id, inquiry_id=s.inquiry_id, kind="doc_chase", tone="formal",
        subject_en=f"Urgent: Documents Revision Required for Shipment {ref}",
        body_en=body_en, body_zh=body_zh,
        variables_json=json.dumps({"shipment_no": ref}, ensure_ascii=False),
        facts_used_json=json.dumps(
            [{"field": "shipment_issues", "value": f"{len(issues)} 条异常引用"},
             {"field": "missing_docs", "value": ", ".join(missing) or "无"}],
            ensure_ascii=False),
        needs_confirmation_json=json.dumps(
            ["收件人需人工填写", "截单时间与异常内容请核对后发送"], ensure_ascii=False),
        created_by_user_id=scope.user.id,
    )
    db.add(draft)
    audit(db, scope.org_id, scope.user.id, "shipment.chase_email", "shipment", s.id,
          {"issues": len(issues), "missing": len(missing)})
    db.commit()
    return {"id": draft.id, "subject_en": draft.subject_en, "body_en": body_en,
            "body_zh": body_zh, "needs_confirmation": json.loads(draft.needs_confirmation_json)}
