"""Workbench dashboard, analytics, audit log, glossary and demo routes."""
from __future__ import annotations

import json

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ...database import get_db
from ...deps import OrgScope, get_scope, paginate, order_by
from ...models import (AuditEvent, ConnectorAccount, Customer, ExternalMessage,
                       FollowUpTask, Inquiry, Product, Quote, SyncLog)
from ...services.followup import workload_enriched, workload_lists

router = APIRouter(tags=["dashboard"])


@router.get("/dashboard/workbench")
def workbench(scope: OrgScope = Depends(get_scope), db: Session = Depends(get_db)):
    today_counts = {
        "inquiries": db.scalar(select(func.count(Inquiry.id)).where(
            Inquiry.org_id == scope.org_id, Inquiry.deleted == 0)) or 0,
        "open_inquiries": db.scalar(select(func.count(Inquiry.id)).where(
            Inquiry.org_id == scope.org_id, Inquiry.deleted == 0,
            Inquiry.status.in_(["open", "clarifying"]))) or 0,
        "customers": db.scalar(select(func.count(Customer.id)).where(
            Customer.org_id == scope.org_id)) or 0,
        "products": db.scalar(select(func.count(Product.id)).where(
            Product.org_id == scope.org_id, Product.is_active == True)) or 0,  # noqa: E712
        "quotes": db.scalar(select(func.count(Quote.id)).where(
            Quote.org_id == scope.org_id)) or 0,
        "pending_followups": db.scalar(select(func.count(FollowUpTask.id)).where(
            FollowUpTask.org_id == scope.org_id, FollowUpTask.status == "pending")) or 0,
    }
    workload = workload_enriched(db, scope.org_id)
    recent = db.scalars(select(Inquiry).where(
        Inquiry.org_id == scope.org_id, Inquiry.deleted == 0
    ).order_by(Inquiry.id.desc()).limit(5)).all()
    due_tasks = db.scalars(select(FollowUpTask).where(
        FollowUpTask.org_id == scope.org_id, FollowUpTask.status == "pending"
    ).order_by(FollowUpTask.due_at).limit(5)).all()
    return {
        "counts": today_counts,
        "workload_sizes": {k: len(v) for k, v in workload.items()},
        "workload": workload,
        "recent_inquiries": [{"id": i.id, "title": i.title, "status": i.status,
                              "completeness": i.completeness} for i in recent],
        "due_tasks": [{"id": t.id, "title": t.title, "due_at": t.due_at.isoformat() if t.due_at else None,
                       "priority": t.priority} for t in due_tasks],
    }


@router.get("/dashboard/analytics")
def analytics(scope: OrgScope = Depends(get_scope), db: Session = Depends(get_db)):
    inquiries = db.scalars(select(Inquiry).where(Inquiry.org_id == scope.org_id,
                                                 Inquiry.deleted == 0)).all()
    stage_counts: dict[str, int] = {}
    for i in inquiries:
        stage_counts[i.status] = stage_counts.get(i.status, 0) + 1
    quotes = db.scalars(select(Quote).where(Quote.org_id == scope.org_id,
                                            Quote.status != "superseded")).all()
    channel_counts: dict[str, int] = {}
    for i in inquiries:
        channel_counts[i.source_channel] = channel_counts.get(i.source_channel, 0) + 1
    completeness_buckets = {"0-40": 0, "40-70": 0, "70-100": 0}
    for i in inquiries:
        c = i.completeness or 0
        key = "0-40" if c < 40 else ("40-70" if c < 70 else "70-100")
        completeness_buckets[key] += 1
    approved_amount = sum(q.total_amount for q in quotes if q.status == "approved")
    return {
        "inquiry_total": len(inquiries),
        "stage_counts": stage_counts,
        "channel_counts": channel_counts,
        "completeness_buckets": completeness_buckets,
        "quote_total": len(quotes),
        "approved_quote_amount": round(approved_amount, 2),
        "note": "金额为内部统计，仅供业务参考",
    }


funnel_router = APIRouter(prefix="/analytics", tags=["analytics"])


@funnel_router.get("/funnel")
def sales_funnel(scope: OrgScope = Depends(get_scope), db: Session = Depends(get_db)):
    """九阶段销售漏斗：数量、相邻转化率、阶段停留时长中位数（算法见 services/funnel.py）。"""
    from ...services.funnel import build_funnel

    return build_funnel(db, scope.org_id)


audit_router = APIRouter(prefix="/audit", tags=["audit"])


@audit_router.get("")
def list_audit(scope: OrgScope = Depends(get_scope), db: Session = Depends(get_db),
               pg: dict = Depends(paginate), action: str = Query("", max_length=100)):
    stmt = select(AuditEvent).where(AuditEvent.org_id == scope.org_id)
    if action:
        stmt = stmt.where(AuditEvent.action.ilike(f"%{action}%"))
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(stmt.order_by(order_by(AuditEvent, pg["sort"]))
                      .offset((pg["page"] - 1) * pg["page_size"]).limit(pg["page_size"])).all()
    from ...models import User
    users = {u.id: u.name for u in db.scalars(select(User).where(User.org_id == scope.org_id)).all()}
    return {"items": [{"id": r.id, "action": r.action, "entity_type": r.entity_type,
                       "entity_id": r.entity_id, "detail": json.loads(r.detail_json or "{}"),
                       "user": users.get(r.user_id, ""),
                       "created_at": r.created_at.isoformat()} for r in rows],
            "total": total, "page": pg["page"], "page_size": pg["page_size"]}


synclog_router = APIRouter(prefix="/sync-logs", tags=["sync-logs"])


@synclog_router.get("")
def list_sync_logs(scope: OrgScope = Depends(get_scope), db: Session = Depends(get_db),
                   pg: dict = Depends(paginate), account_id: int = Query(0),
                   level: str = Query("", max_length=10)):
    stmt = select(SyncLog).where(SyncLog.org_id == scope.org_id)
    if account_id:
        stmt = stmt.where(SyncLog.connector_account_id == account_id)
    if level:
        stmt = stmt.where(SyncLog.level == level)
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(stmt.order_by(order_by(SyncLog, pg["sort"]))
                      .offset((pg["page"] - 1) * pg["page_size"]).limit(pg["page_size"])).all()
    accounts = {a.id: a.name for a in db.scalars(select(ConnectorAccount).where(
        ConnectorAccount.org_id == scope.org_id)).all()}
    msgs = db.scalars(select(ExternalMessage).where(
        ExternalMessage.org_id == scope.org_id).order_by(ExternalMessage.id.desc()).limit(50)).all()
    return {"items": [{"id": r.id, "account": accounts.get(r.connector_account_id, r.connector_account_id),
                       "level": r.level, "event": r.event,
                       "detail": json.loads(r.detail_json or "{}"),
                       "created_at": r.created_at.isoformat()} for r in rows],
            "recent_messages": [{"id": m.id, "channel": m.channel, "sender": m.sender,
                                 "status": m.process_status, "inquiry_id": m.inquiry_id,
                                 "received_at": m.received_at.isoformat() if m.received_at else None}
                                for m in msgs],
            "total": total, "page": pg["page"], "page_size": pg["page_size"]}


glossary_router = APIRouter(prefix="/glossary", tags=["glossary"])


@glossary_router.get("")
def get_glossary(q: str = Query("", max_length=50)):
    from ...services.glossary import DISCLAIMER, GLOSSARY
    items = [{"term": k, "zh": v["zh"], "en": v["en"]}
             for k, v in GLOSSARY.items()
             if not q or q.lower() in k.lower() or q in v["zh"]]
    return {"items": items, "disclaimer": DISCLAIMER}
