"""Inquiry routes: the core workbench API.

Covers: list/create/detail, messages, requirement state (view/manual set/lock),
history, clarification recommendation, product matching, summary.
"""
from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ...database import get_db
from ...deps import OrgScope, get_scope, order_by, paginate
from ...models import (ClarificationLog, ConversationMessage, Customer,
                       Inquiry, InquiryStageEvent, MatchResult, Product,
                       FUNNEL_STAGES)
from ...schemas import (HistoryOut, InquiryCreate, InquiryDetail, InquiryOut,
                        MatchOut, MessageIn, MessageOut, SlotOut, SlotSetIn)
from ...services.audit import audit
from ...services.search import ESCAPE, contains
from ...services.clarification import recommend
from ...services.fields import (BASE_REQUIRED_FOR_QUOTE, FIELD_DEFS,
                                FOOD_CONTACT_CERTS, FOOD_CONTACT_CONCEPTS,
                                PORT_REQUIRED_INCOTERMS)
from ...services.ingestion import _utcnow, add_message, find_or_create_customer
from ...services.matching import persist_match_results
from ...services.requirement_service import RequirementService

router = APIRouter(prefix="/inquiries", tags=["inquiries"])


def _get_inquiry(db: Session, scope: OrgScope, inquiry_id: int) -> Inquiry:
    inq = db.scalar(select(Inquiry).where(Inquiry.org_id == scope.org_id, Inquiry.id == inquiry_id))
    if inq is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND,
                            detail={"code": "not_found", "message": "询盘不存在"})
    return inq


def _requirement_view(db: Session, scope: OrgScope, inq: Inquiry) -> dict:
    svc = RequirementService(db, scope.org_id)
    values = svc.active_values(inq.id)
    breakdown = svc.recompute(inq)
    blocking = [f for f in BASE_REQUIRED_FOR_QUOTE
                if not values.get(f, {}).get("normalized")]
    incoterm = (values.get("incoterm") or {}).get("normalized") or ""
    if incoterm in PORT_REQUIRED_INCOTERMS and not values.get("destination_port", {}).get("normalized"):
        blocking.append("destination_port")
    concept = (values.get("product") or {}).get("normalized") or ""
    certs = {(values.get("certification") or {}).get("normalized") or ""}
    certs = {c for c in certs if c}
    food_cert_missing = concept in FOOD_CONTACT_CONCEPTS and not (certs & FOOD_CONTACT_CERTS)
    return {
        "completeness": breakdown,
        "fields": {f: values.get(f) for f in FIELD_DEFS},
        "cannot_quote_reasons": [
            f"缺少 {_FIELD_ZH(f)}" for f in blocking
        ] + (["食品接触类产品缺少食品级认证要求（如 FDA/LFGB）"] if food_cert_missing else [])
        + ([f"字段存在矛盾需确认：{'、'.join(FIELD_DEFS[f].label_zh for f in breakdown['conflicting'] if f in FIELD_DEFS)}"]
           if breakdown["conflicting"] else []),
    }


def _FIELD_ZH(f: str) -> str:
    return FIELD_DEFS[f].label_zh if f in FIELD_DEFS else f


@router.get("")
def list_inquiries(scope: OrgScope = Depends(get_scope), db: Session = Depends(get_db),
                   pg: dict = Depends(paginate),
                   q: str = Query("", max_length=200),
                   status_filter: str = Query("", alias="status"),
                   stage: str = Query("", max_length=30),
                   flag: str = Query("", max_length=30)):
    stmt = select(Inquiry).where(Inquiry.org_id == scope.org_id, Inquiry.deleted == 0)
    if q:
        like = contains(q)
        stmt = stmt.where(Inquiry.title.ilike(like, escape=ESCAPE)
                          | Inquiry.raw_text.ilike(like, escape=ESCAPE))
    if stage:
        stmt = stmt.where(Inquiry.stage == stage)
    if status_filter:
        stmt = stmt.where(Inquiry.status == status_filter)
    if flag:
        stmt = stmt.where(Inquiry.quality_flag == flag)
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(stmt.order_by(order_by(Inquiry, pg["sort"]))
                      .offset((pg["page"] - 1) * pg["page_size"]).limit(pg["page_size"])).all()
    customer_ids = {r.customer_id for r in rows if r.customer_id}
    customers = {c.id: c for c in db.scalars(select(Customer).where(
        Customer.org_id == scope.org_id, Customer.id.in_(customer_ids or [0]))).all()}
    return {
        "items": [{**InquiryOut.model_validate(r).model_dump(mode="json"),
                   "customer_name": customers[r.customer_id].company_name if r.customer_id in customers else "",
                   "country": customers[r.customer_id].country if r.customer_id in customers else ""}
                  for r in rows],
        "total": total, "page": pg["page"], "page_size": pg["page_size"],
    }


@router.post("", status_code=201)
def create_inquiry(body: InquiryCreate, scope: OrgScope = Depends(get_scope),
                   db: Session = Depends(get_db)):
    """Manual paste entry (基础入口): parse immediately, create/link customer."""
    text = body.text.strip()
    if body.customer_id:
        customer = db.scalar(select(Customer).where(
            Customer.org_id == scope.org_id, Customer.id == body.customer_id))
        if customer is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND,
                                detail={"code": "not_found", "message": "指定客户不存在"})
        contact_id = None
    else:
        customer, _contact = find_or_create_customer(db, scope.org_id, text, body.sender, body.source_channel)
        contact_id = _contact.id if _contact else None

    inq = Inquiry(
        org_id=scope.org_id, customer_id=customer.id if customer else None,
        contact_id=contact_id, title=body.title or (text.splitlines()[0][:120] if text else ""),
        raw_text=text, language="en", source_channel=body.source_channel,
        quality_flag="low_quality" if len(text) < 25 else "normal",
    )
    db.add(inq)
    db.flush()
    from ...models import ConversationThread
    thread = ConversationThread(org_id=scope.org_id, inquiry_id=inq.id,
                                channel=body.source_channel)
    db.add(thread)
    db.flush()
    add_message(db, scope.org_id, inq, thread.id, direction="in",
                sender=body.sender or (customer.company_name if customer else ""), text=text,
                sent_at=_utcnow())
    if customer:
        customer.last_contact_at = _utcnow()
        if not customer.next_follow_up_at:
            customer.next_follow_up_at = _utcnow() + __import__("datetime").timedelta(days=3)
    db.add(InquiryStageEvent(org_id=scope.org_id, inquiry_id=inq.id,
                             from_stage="", to_stage=inq.stage or "new",
                             actor_user_id=scope.user.id))
    audit(db, scope.org_id, scope.user.id, "inquiry.create", "inquiry", inq.id)
    ai_summary = None
    try:
        from ...services.ai.runner import run_intake
        ai_summary = run_intake(db, scope.org_id, inq, scope.user.id)
    except Exception:  # noqa: BLE001 — AI 失败不阻塞建单
        db.rollback()
    db.commit()
    return {**InquiryDetail.model_validate(inq).model_dump(mode="json"),
            "requirement": _requirement_view(db, scope, inq),
            "ai_intake": ai_summary}


@router.get("/{inquiry_id}")
def get_inquiry(inquiry_id: int, scope: OrgScope = Depends(get_scope),
                db: Session = Depends(get_db)):
    inq = _get_inquiry(db, scope, inquiry_id)
    data = {**InquiryDetail.model_validate(inq).model_dump(mode="json"),
            "requirement": _requirement_view(db, scope, inq)}
    customer = db.get(Customer, inq.customer_id) if inq.customer_id else None
    data["customer"] = ({"id": customer.id, "company_name": customer.company_name,
                         "country": customer.country, "stage": customer.stage}
                        if customer else None)
    latest_matches = db.scalars(select(MatchResult).where(
        MatchResult.org_id == scope.org_id, MatchResult.inquiry_id == inq.id
    ).order_by(MatchResult.id.desc()).limit(30)).all()
    if latest_matches:
        latest_batch = latest_matches[0].batch_no
        data["latest_match_batch"] = latest_batch
    return data


@router.get("/{inquiry_id}/messages")
def list_messages(inquiry_id: int, scope: OrgScope = Depends(get_scope),
                  db: Session = Depends(get_db)):
    inq = _get_inquiry(db, scope, inquiry_id)
    rows = db.scalars(select(ConversationMessage).where(
        ConversationMessage.org_id == scope.org_id,
        ConversationMessage.inquiry_id == inq.id).order_by(ConversationMessage.id)).all()
    return {"items": [MessageOut.model_validate(m).model_dump(mode="json") for m in rows]}


@router.post("/{inquiry_id}/messages", status_code=201)
def post_message(inquiry_id: int, body: MessageIn, scope: OrgScope = Depends(get_scope),
                 db: Session = Depends(get_db)):
    """Add a follow-up message (multi-round). Inbound messages re-parse the state."""
    inq = _get_inquiry(db, scope, inquiry_id)
    # duplicate content guard within the same inquiry
    from ...services.normalization import content_hash
    chash = content_hash(body.text)
    dup = db.scalar(select(ConversationMessage).where(
        ConversationMessage.org_id == scope.org_id,
        ConversationMessage.inquiry_id == inq.id,
        ConversationMessage.content_hash == chash))
    if dup and body.direction == "in":
        return {"duplicate": True, "message": MessageOut.model_validate(dup).model_dump(mode="json")}
    from ...models import ConversationThread
    thread = db.scalar(select(ConversationThread).where(
        ConversationThread.org_id == scope.org_id,
        ConversationThread.inquiry_id == inq.id))
    if thread is None:
        thread = ConversationThread(org_id=scope.org_id, inquiry_id=inq.id,
                                    channel=inq.source_channel)
        db.add(thread)
        db.flush()
    msg = add_message(db, scope.org_id, inq, thread.id, direction=body.direction,
                      sender=inq.customer_id and "customer" or "us", text=body.text.strip())
    db.commit()
    return {"duplicate": False, "message": MessageOut.model_validate(msg).model_dump(mode="json"),
            "requirement": _requirement_view(db, scope, inq)}


@router.get("/{inquiry_id}/requirement")
def get_requirement(inquiry_id: int, scope: OrgScope = Depends(get_scope),
                    db: Session = Depends(get_db)):
    inq = _get_inquiry(db, scope, inquiry_id)
    return _requirement_view(db, scope, inq)


@router.get("/{inquiry_id}/slots")
def get_slots(inquiry_id: int, scope: OrgScope = Depends(get_scope),
              db: Session = Depends(get_db)):
    inq = _get_inquiry(db, scope, inquiry_id)
    svc = RequirementService(db, scope.org_id)
    rows = svc.slots_map(inq.id)
    return {"items": [SlotOut.model_validate(r).model_dump(mode="json")
                      for r in rows.values() if r.status != "unknown"]}


@router.patch("/{inquiry_id}/slots")
def set_slot(inquiry_id: int, body: SlotSetIn, scope: OrgScope = Depends(get_scope),
             db: Session = Depends(get_db)):
    """Manual field set/correction — human is authoritative; optional lock."""
    inq = _get_inquiry(db, scope, inquiry_id)
    svc = RequirementService(db, scope.org_id)
    try:
        change = svc.manual_set(inq, body.field, body.value, lock=body.lock)
    except ValueError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            detail={"code": "bad_field", "message": str(e)})
    audit(db, scope.org_id, scope.user.id, "requirement.manual_set", "inquiry", inq.id,
          {"field": body.field, "lock": body.lock})
    db.commit()
    return {"change": {"field": change.field, "old": change.old_value, "new": change.new_value,
                       "type": change.change_type, "note": change.note},
            "requirement": _requirement_view(db, scope, inq)}


@router.delete("/{inquiry_id}/slots/{field}/lock")
def unlock_slot(inquiry_id: int, field: str, scope: OrgScope = Depends(get_scope),
                db: Session = Depends(get_db)):
    inq = _get_inquiry(db, scope, inquiry_id)
    svc = RequirementService(db, scope.org_id)
    svc.manual_unlock(inq, field)
    db.commit()
    return {"ok": True}


@router.get("/{inquiry_id}/history")
def get_history(inquiry_id: int, scope: OrgScope = Depends(get_scope),
                db: Session = Depends(get_db)):
    inq = _get_inquiry(db, scope, inquiry_id)
    svc = RequirementService(db, scope.org_id)
    rows = svc.history(inq.id)
    return {"items": [HistoryOut.model_validate(r).model_dump(mode="json") for r in rows]}


@router.post("/{inquiry_id}/clarification")
def recommend_clarification(inquiry_id: int, scope: OrgScope = Depends(get_scope),
                            db: Session = Depends(get_db)):
    inq = _get_inquiry(db, scope, inquiry_id)
    svc = RequirementService(db, scope.org_id)
    result = recommend(db, scope.org_id, inq.id, svc.active_values(inq.id))
    db.commit()
    return result


@router.post("/{inquiry_id}/clarification/{log_id}/dismiss")
def dismiss_clarification(inquiry_id: int, log_id: int, scope: OrgScope = Depends(get_scope),
                          db: Session = Depends(get_db)):
    log = db.scalar(select(ClarificationLog).where(
        ClarificationLog.org_id == scope.org_id,
        ClarificationLog.id == log_id, ClarificationLog.inquiry_id == inquiry_id))
    if log is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND,
                            detail={"code": "not_found", "message": "追问记录不存在"})
    log.status = "dismissed"
    db.commit()
    return {"ok": True}


def _product_brief(p: Product) -> dict:
    return {"id": p.id, "sku": p.sku, "name_zh": p.name_zh, "name_en": p.name_en,
            "moq": p.moq, "currency": p.currency, "price_tiers_json": p.price_tiers_json,
            "lead_time_days": p.lead_time_days, "image_url": p.image_url,
            "certifications": json.loads(p.certifications_json or "[]"),
            "material": p.material, "spec": p.spec}


def _match_items(db: Session, scope: OrgScope, inquiry_id: int, batch_no: str | None) -> list[dict]:
    stmt = select(MatchResult).where(
        MatchResult.org_id == scope.org_id, MatchResult.inquiry_id == inquiry_id)
    if batch_no:
        stmt = stmt.where(MatchResult.batch_no == batch_no)
    matches = db.scalars(stmt.order_by(MatchResult.rank)).all()
    products = {p.id: p for p in db.scalars(select(Product).where(
        Product.org_id == scope.org_id,
        Product.id.in_([m.product_id for m in matches] or [0]))).all()}
    return [{**MatchOut.model_validate(m).model_dump(mode="json"),
             "product": _product_brief(products[m.product_id])}
            for m in matches if m.product_id in products]


@router.post("/{inquiry_id}/match")
def run_match(inquiry_id: int, scope: OrgScope = Depends(get_scope),
              db: Session = Depends(get_db)):
    inq = _get_inquiry(db, scope, inquiry_id)
    svc = RequirementService(db, scope.org_id)
    values = svc.active_values(inq.id)
    summary = persist_match_results(db, scope.org_id, inq.id, values)
    audit(db, scope.org_id, scope.user.id, "inquiry.match", "inquiry", inq.id,
          {"batch": summary["batch_no"]})
    db.commit()
    return {**summary, "items": _match_items(db, scope, inq.id, summary["batch_no"])}


@router.get("/{inquiry_id}/matches")
def get_matches(inquiry_id: int, scope: OrgScope = Depends(get_scope),
                db: Session = Depends(get_db)):
    inq = _get_inquiry(db, scope, inquiry_id)
    latest = db.scalar(select(MatchResult).where(
        MatchResult.org_id == scope.org_id, MatchResult.inquiry_id == inq.id
    ).order_by(MatchResult.id.desc()))
    if latest is None:
        return {"items": [], "batch_no": None}
    return {"batch_no": latest.batch_no,
            "items": _match_items(db, scope, inq.id, latest.batch_no)}


@router.post("/{inquiry_id}/status")
def set_status(inquiry_id: int, body: dict, scope: OrgScope = Depends(get_scope),
               db: Session = Depends(get_db)):
    inq = _get_inquiry(db, scope, inquiry_id)
    # 传了字段但值非法：明确拒绝，不静默吞掉（与 stage 口径一致）
    if "status" in body and body["status"] not in ("open", "clarifying", "quoted", "won", "lost", "spam"):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail={
            "code": "invalid_status", "message": f"非法状态 {body['status']}"})
    if "quality_flag" in body and body["quality_flag"] not in ("normal", "low_quality", "suspected_fraud"):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail={
            "code": "invalid_quality_flag", "message": f"非法质量标记 {body['quality_flag']}"})
    if body.get("status"):
        inq.status = body["status"]
    if body.get("quality_flag"):
        inq.quality_flag = body["quality_flag"]
    old_stage = inq.stage or "new"
    new_stage = body.get("stage") or ""
    # 传了 stage 但不在九阶段里：明确拒绝，不静默吞掉
    if new_stage and new_stage not in FUNNEL_STAGES:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail={
            "code": "invalid_stage",
            "message": f"非法阶段 {new_stage}，可选值：{'/'.join(FUNNEL_STAGES)}"})
    if not new_stage and inq.status in ("won", "lost"):
        new_stage = inq.status  # 终态状态同步漏斗阶段
    if new_stage and new_stage != old_stage:
        inq.stage = new_stage
        db.add(InquiryStageEvent(org_id=scope.org_id, inquiry_id=inq.id,
                                 from_stage=old_stage, to_stage=new_stage,
                                 actor_user_id=scope.user.id))
    audit(db, scope.org_id, scope.user.id, "inquiry.status", "inquiry", inq.id, body)
    db.commit()
    return InquiryOut.model_validate(inq).model_dump(mode="json")
