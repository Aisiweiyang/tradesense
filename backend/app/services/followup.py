"""Customer/follow-up service: explainable lead scoring, smart task suggestions,
today/overdue/quoted-no-reply lists."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Customer, FollowUpTask, Inquiry, Quote


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def score_customer(customer: Customer, inquiries: list[Inquiry], quotes: list[Quote]) -> tuple[int, dict]:
    """Explainable lead score: factors and points, no mystery numbers (max 100)."""
    factors: dict[str, int] = {}
    factors["最近 30 天有新增询盘"] = 25 if any((i.created_at and (now_utc() - i.created_at) < timedelta(days=30)) for i in inquiries) else 0
    factors["存在已批准报价"] = 20 if any(q.status == "approved" for q in quotes) else 0
    factors["存在任意报价"] = 10 if quotes else 0
    factors["询盘完整度 ≥ 70%"] = 15 if any((i.completeness or 0) >= 70 for i in inquiries) else 0
    factors["近 14 天有联系"] = 15 if (customer.last_contact_at and (now_utc() - customer.last_contact_at) < timedelta(days=14)) else 0
    factors["销售阶段进入谈判及以后"] = 15 if customer.stage in ("negotiating", "won") else 0
    score = sum(factors.values())
    return score, factors


def suggest_tasks(db: Session, org_id: int, inquiry: Inquiry) -> list[dict]:
    """Rule-based next-step suggestions with visible reasons."""
    values_json = inquiry.summary_json  # summary holds next_step + missing
    try:
        summary = json.loads(values_json or "{}")
    except json.JSONDecodeError:
        summary = {}
    suggestions: list[dict] = []
    missing = summary.get("missing_zh") or []
    conflicting = summary.get("conflicting_zh") or []
    if conflicting:
        suggestions.append({"type": "clarify", "title": "确认矛盾字段",
                            "reason": f"字段存在冲突：{'、'.join(conflicting)}"})
    if missing:
        suggestions.append({"type": "ask_missing", "title": "询问缺失信息",
                            "reason": f"缺少：{'、'.join(missing)}"})
    if inquiry.status == "quoted":
        suggestions.append({"type": "quote_follow_up", "title": "报价后跟进",
                            "reason": "已报价，3 天未回复即可礼貌跟进"})
    if inquiry.quality_flag == "low_quality":
        suggestions.append({"type": "review_quality", "title": "标记低质量询盘",
                            "reason": "该询盘信息极少或疑似群发，建议先甄别再投入时间"})
    if not suggestions:
        suggestions.append({"type": "follow_up", "title": "安排常规跟进",
                            "reason": "当前阶段无阻塞项，保持 3-7 天跟进节奏"})
    return suggestions


def workload_lists(db: Session, org_id: int) -> dict:
    """Today / overdue / quoted-no-reply / long-silence / high-intent / incomplete."""
    today = now_utc()
    tasks_due = db.scalars(select(FollowUpTask).where(
        FollowUpTask.org_id == org_id,
        FollowUpTask.status == "pending",
        FollowUpTask.due_at != None,  # noqa: E711
        FollowUpTask.due_at <= today,
    )).all()
    overdue = [t for t in tasks_due if t.due_at and t.due_at < today.replace(hour=0, minute=0, second=0)]
    today_tasks = [t for t in tasks_due if t not in overdue]

    inquiries = db.scalars(select(Inquiry).where(Inquiry.org_id == org_id)).all()
    quoted_no_reply = [i for i in inquiries if i.status == "quoted"
                       and i.updated_at and (today - i.updated_at) > timedelta(days=3)]
    long_silence = [i for i in inquiries if i.updated_at and (today - i.updated_at) > timedelta(days=14)
                    and i.status not in ("won", "lost")]
    high_intent = sorted([i for i in inquiries if (i.completeness or 0) >= 70 and i.status in ("open", "clarifying", "quoted")],
                         key=lambda i: -(i.completeness or 0))[:10]
    incomplete = [i for i in inquiries if (i.completeness or 0) < 50 and i.status in ("open", "clarifying")]
    return {
        "today_due": [t.id for t in today_tasks],
        "overdue": [t.id for t in overdue],
        "quoted_no_reply": [i.id for i in quoted_no_reply],
        "long_silence": [i.id for i in long_silence],
        "high_intent": [i.id for i in high_intent],
        "incomplete": [i.id for i in incomplete],
    }


def workload_enriched(db: Session, org_id: int) -> dict[str, list[dict]]:
    """workload_lists with fully-populated objects for the frontend."""
    ids = workload_lists(db, org_id)
    task_ids = ids["today_due"] + ids["overdue"]
    tasks = {t.id: t for t in db.scalars(select(FollowUpTask).where(
        FollowUpTask.org_id == org_id, FollowUpTask.id.in_(task_ids or [0]))).all()}
    inquiry_ids = (ids["quoted_no_reply"] + ids["long_silence"]
                   + ids["high_intent"] + ids["incomplete"])
    inqs = {i.id: i for i in db.scalars(select(Inquiry).where(
        Inquiry.org_id == org_id, Inquiry.id.in_(inquiry_ids or [0]))).all()}
    customer_ids = {i.customer_id for i in inqs.values() if i.customer_id}
    customers = {c.id: c for c in db.scalars(select(Customer).where(
        Customer.org_id == org_id, Customer.id.in_(customer_ids or [0]))).all()}

    def task_out(t: FollowUpTask) -> dict:
        return {"id": t.id, "title": t.title, "task_type": t.task_type,
                "due_at": t.due_at.isoformat() if t.due_at else None,
                "status": t.status, "priority": t.priority,
                "inquiry_id": t.inquiry_id}

    def inq_out(i: Inquiry) -> dict:
        c = customers.get(i.customer_id) if i.customer_id else None
        return {"id": i.id, "title": i.title, "status": i.status,
                "completeness": i.completeness,
                "customer_name": c.company_name if c else "",
                "updated_at": i.updated_at.isoformat() if i.updated_at else None}

    overdue_set = set(ids["overdue"])
    return {
        "today_due": [task_out(tasks[t]) for t in ids["today_due"] if t in tasks],
        "overdue": [task_out(tasks[t]) for t in ids["overdue"] if t in tasks],
        "quoted_no_reply": [inq_out(inqs[i]) for i in ids["quoted_no_reply"] if i in inqs],
        "long_silence": [inq_out(inqs[i]) for i in ids["long_silence"] if i in inqs],
        "high_intent": [inq_out(inqs[i]) for i in ids["high_intent"] if i in inqs],
        "incomplete": [inq_out(inqs[i]) for i in ids["incomplete"] if i in inqs],
    }


def create_task(db: Session, org_id: int, **kw) -> FollowUpTask:
    task = FollowUpTask(org_id=org_id, **kw)
    db.add(task)
    db.flush()
    return task
