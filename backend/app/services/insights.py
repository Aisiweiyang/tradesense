"""看板洞察：渠道转化、首响时长、目标达成率。

口径：
- 渠道转化 = 触达过 quoted 及之后的询盘 / 该渠道全部询盘（存量无事件按当前阶段兜底，与漏斗口径一致）；
- 首响时长 = 询盘创建 → 首条 out 方向消息；只统计已响应的，中位数才不被拖偏；
  未响应的单独给数量与最长等待（右删失观测，口径与漏斗停留时长一致）；
- 目标达成率 = 已批准报价中 customer_price ≤ 询盘目标价 的比例（无目标价的不计入）。
"""
from __future__ import annotations

import statistics
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import ConversationMessage, Inquiry, Quote

QUOTED_STAGES = {"quoted", "sample", "negotiating", "won"}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def channel_conversion(db: Session, org_id: int) -> list[dict]:
    rows = db.execute(select(Inquiry.source_channel, Inquiry.stage).where(
        Inquiry.org_id == org_id, Inquiry.deleted == 0)).all()
    agg: dict[str, dict] = {}
    for ch, stage in rows:
        a = agg.setdefault(ch or "manual", {"total": 0, "reached_quoted": 0})
        a["total"] += 1
        if (stage or "") in QUOTED_STAGES:
            a["reached_quoted"] += 1
    out = [{"channel": ch, "total": a["total"], "reached_quoted": a["reached_quoted"],
            "conversion": round(a["reached_quoted"] / a["total"], 4) if a["total"] else None}
           for ch, a in agg.items()]
    out.sort(key=lambda x: (-x["total"], x["channel"]))
    return out


def first_response(db: Session, org_id: int, at_now: datetime | None = None) -> dict:
    at_now = at_now or _utcnow()
    inquiries = db.execute(select(Inquiry.id, Inquiry.created_at).where(
        Inquiry.org_id == org_id, Inquiry.deleted == 0)).all()
    firsts: dict[int, datetime] = {}
    msgs = db.execute(select(ConversationMessage.inquiry_id, ConversationMessage.sent_at).where(
        ConversationMessage.org_id == org_id,
        ConversationMessage.direction == "out")).all()
    for iid, sent in msgs:
        if sent and (iid not in firsts or sent < firsts[iid]):
            firsts[iid] = sent
    samples: list[float] = []
    waiting = 0
    longest_wait_h = 0.0
    for iid, created in inquiries:
        if not created:
            continue
        t = firsts.get(iid)
        if t:
            samples.append(max((t - created).total_seconds() / 3600.0, 0.0))
        else:
            waiting += 1
            longest_wait_h = max(longest_wait_h, (at_now - created).total_seconds() / 3600.0)
    return {
        "median_hours": round(statistics.median(samples), 1) if samples else None,
        "responded": len(samples),
        "waiting": waiting,
        "longest_waiting_hours": round(longest_wait_h, 1) if waiting else None,
    }


def target_hit_rate(db: Session, org_id: int) -> dict:
    from .quote_sheet import _target_price  # 同一目标价解析口径
    quotes = db.scalars(select(Quote).where(
        Quote.org_id == org_id, Quote.status == "approved")).all()
    hit = total = 0
    for q in quotes:
        inq = db.get(Inquiry, q.inquiry_id) if q.inquiry_id else None
        if inq is None or inq.org_id != org_id:
            continue
        target = _target_price(inq)
        if target is None:
            continue
        total += 1
        if (q.customer_price or 0) <= target:
            hit += 1
    return {"hit": hit, "total": total,
            "rate": round(hit / total, 4) if total else None}


def build_insights(db: Session, org_id: int) -> dict:
    at_now = _utcnow()
    return {
        "channels": channel_conversion(db, org_id),
        "first_response": first_response(db, org_id, at_now),
        "target_hit": target_hit_rate(db, org_id),
        "generated_at": at_now.isoformat(),
    }
