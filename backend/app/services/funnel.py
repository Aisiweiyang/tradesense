"""销售漏斗算法（九阶段）。

数据源：inquiry_stage_events 事件表（append-only）。
- 数量 count：询盘当前所处的阶段（Inquiry.stage）。
- 触达 reached：曾经进入过某阶段的询盘数 = 有 to_stage 事件的数量；
  无任何事件的存量询盘按"当前阶段触达"兜底计入。
- 转化率 conversion_to_next：主链 new→qualified→clarifying→quoted→sample
  →negotiating→won 上相邻两站 reached 的比值（分母 0 时为 None）。
- 停留时长：每次进入阶段 S 的事件时刻 t1，到该询盘下一次阶段事件时刻 t2
  的间隔；若之后没有再变更（仍在 S），用"至今"时长计入。
  这对仍在阶段的询盘是右删失（观测时刻截断），中位数因此是真实停留时长
  的保守下界——与 Salesforce 等 CRM 的"阶段耗时"报表口径一致；
  后续如需精确可换 Kaplan-Meier/逆向 KM，这里刻意保持可解释、可手算。
"""
from __future__ import annotations

import statistics
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import FUNNEL_NEXT, FUNNEL_STAGES, FUNNEL_STAGE_LABELS, Inquiry, InquiryStageEvent


def _stage_dwell_hours(events: list[InquiryStageEvent], at_now: datetime) -> dict[str, list[float]]:
    """一次询盘的停留时长采样：{stage: [hours, ...]}。"""
    out: dict[str, list[float]] = {}
    ordered = sorted(events, key=lambda e: (e.occurred_at or at_now, e.id))
    for i, e in enumerate(ordered):
        start = e.occurred_at or at_now
        end = ordered[i + 1].occurred_at if i + 1 < len(ordered) else at_now
        hours = max((end - start).total_seconds() / 3600.0, 0.0)
        out.setdefault(e.to_stage, []).append(hours)
    return out


def build_funnel(db: Session, org_id: int) -> dict:
    at_now = datetime.now(timezone.utc)
    inquiries = db.scalars(select(Inquiry).where(
        Inquiry.org_id == org_id, Inquiry.deleted == 0)).all()
    events = db.scalars(select(InquiryStageEvent).where(
        InquiryStageEvent.org_id == org_id)).all()

    by_inquiry: dict[int, list[InquiryStageEvent]] = {}
    for e in events:
        by_inquiry.setdefault(e.inquiry_id, []).append(e)

    count: dict[str, int] = {s: 0 for s in FUNNEL_STAGES}
    reached: dict[str, set[int]] = {s: set() for s in FUNNEL_STAGES}
    dwell: dict[str, list[float]] = {s: [] for s in FUNNEL_STAGES}

    for inq in inquiries:
        count[inq.stage] = count.get(inq.stage, 0) + 1
        evts = by_inquiry.get(inq.id) or []
        if evts:
            for e in evts:
                if e.to_stage in reached:
                    reached[e.to_stage].add(inq.id)
            for stage, samples in _stage_dwell_hours(evts, at_now).items():
                if stage in dwell:
                    dwell[stage].extend(samples)
        else:
            # 存量数据兜底：没有事件的询盘视作一直待在当前阶段
            if inq.stage in reached:
                reached[inq.stage].add(inq.id)
            start = inq.created_at or at_now
            hours = max((at_now - start).total_seconds() / 3600.0, 0.0)
            if inq.stage in dwell:
                dwell[inq.stage].append(hours)

    stages = []
    for s in FUNNEL_STAGES:
        nxt = FUNNEL_NEXT.get(s)
        conv = None
        if nxt and reached[s]:
            conv = round(len(reached[nxt]) / len(reached[s]), 4)
        med = None
        if dwell[s]:
            med = round(statistics.median(dwell[s]), 1)
        stages.append({
            "stage": s,
            "label": FUNNEL_STAGE_LABELS.get(s, s),
            "count": count.get(s, 0),
            "reached": len(reached[s]),
            "conversion_to_next": conv,
            "next_stage": nxt,
            "median_dwell_hours": med,
        })
    return {"stages": stages, "generated_at": at_now.isoformat()}
