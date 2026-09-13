"""Clarification question recommender.

At most ONE primary question per round + a secondary list. Every question
carries an explicit reason ("why ask this"). Priority:

    regulatory / quote-blocking  >  severe conflicts  >  high information gain  >  preferences

Information gain for attribute questions uses candidate-set discrimination:
    p = share of candidate products that have this attribute
    split_score = 1 - 2*abs(0.5 - p)
"""
from __future__ import annotations

import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import ClarificationLog, Product
from .fields import (BASE_REQUIRED_FOR_QUOTE, FIELD_DEFS, FOOD_CONTACT_CERTS,
                     FOOD_CONTACT_CONCEPTS, PORT_REQUIRED_INCOTERMS)

# quote/question templates per field (EN for the customer, ZH for the salesperson)
QUESTION_TEMPLATES = {
    "incoterm": {
        "en": "May I know your preferred trade term (EXW / FOB / CIF / DDP) so we can quote accordingly?",
        "zh": "请问您希望使用哪种贸易术语（EXW / FOB / CIF / DDP）？这直接影响报价口径。",
    },
    "destination_port": {
        "en": "Could you share the destination port (or city) so we can calculate the shipping cost?",
        "zh": "请告知目的港（或目的城市），以便核算运费。",
    },
    "destination_country": {
        "en": "Which country will the goods be delivered to?",
        "zh": "请确认货物目的国。",
    },
    "quantity": {
        "en": "How many pieces do you need? Quantity affects the unit price and MOQ.",
        "zh": "请问需要多少数量？数量影响单价与起订量。",
    },
    "product": {
        "en": "Could you tell us which product category you are looking for? We can also send our catalog.",
        "zh": "请问您在找哪类产品？我们可以先发送产品目录供您挑选。",
    },
    "certification": {
        "en": "Do you have any certification requirements (e.g. FDA, LFGB, CE) for your market?",
        "zh": "请问对认证（如 FDA、LFGB、CE）有要求吗？涉及目的国合规。",
    },
    "material": {
        "en": "Any preference on material (e.g. stainless steel 304, plastic, glass)?",
        "zh": "对材质有偏好吗（如 304 不锈钢、塑料、玻璃）？",
    },
    "color": {
        "en": "Which color(s) would you prefer?",
        "zh": "请问需要什么颜色？",
    },
    "spec": {
        "en": "What capacity or size do you need (e.g. 500 ml)?",
        "zh": "请问需要什么容量/规格（如 500ml）？",
    },
    "packaging": {
        "en": "Any packaging requirement (color box, gift box, bulk)?",
        "zh": "对包装有要求吗（彩盒、礼盒、散装）？",
    },
    "lead_time": {
        "en": "When do you need the goods delivered?",
        "zh": "请问您期望的交货时间？",
    },
    "customization": {
        "en": "Would you like your logo printed on the product?",
        "zh": "是否需要在产品上印制贵司 Logo？",
    },
    "target_price": {
        "en": "Do you have a target unit price so we can recommend the best-fit options?",
        "zh": "您有目标单价吗？便于我们推荐最合适的产品。",
    },
    "payment_terms": {
        "en": "Which payment method do you prefer (T/T, L/C, etc.)?",
        "zh": "您偏好哪种付款方式（T/T、信用证等）？",
    },
}


def _candidate_products(db: Session, org_id: int, values: dict, limit: int = 12) -> list[Product]:
    from .matching import recall_candidates
    return recall_candidates(db, org_id, values, limit=limit)


def _split_score(products: list[Product], attr: str) -> float:
    if not products:
        return 0.3
    if attr == "color":
        with_attr = [p for p in products if (p.color or "").strip()]
    elif attr == "spec":
        with_attr = [p for p in products if (p.spec or "").strip()]
    elif attr == "material":
        with_attr = [p for p in products if (p.material or "").strip()]
    else:
        with_attr = [p for p in products if (p.spec or "").strip()]
    p = len(with_attr) / len(products)
    return max(0.0, 1 - 2 * abs(0.5 - p))


def build_candidates(db: Session, org_id: int, values: dict) -> list[dict]:
    """Score all possible questions; return sorted candidate list."""
    scored: list[dict] = []

    def push(fld: str, base: float, reason: str, en: str | None = None, zh: str | None = None):
        t = QUESTION_TEMPLATES.get(fld, {"en": f"Could you confirm the {fld}?", "zh": f"请确认{_LABEL(fld)}。"})
        scored.append({
            "field": fld,
            "question_en": en or t["en"],
            "question_zh": zh or t["zh"],
            "priority_score": round(base, 1),
            "reason": reason,
        })

    def _LABEL(fld):
        return FIELD_DEFS[fld].label_zh if fld in FIELD_DEFS else fld

    def active(fld) -> str:
        v = values.get(fld) or {}
        if not v or v.get("status") in ("unknown", "replaced") or v.get("normalized") == "__unconstrained__":
            return ""
        return v.get("normalized") or ""

    products = _candidate_products(db, org_id, values)
    concept = active("product")

    # 1) regulatory blockers -------------------------------------------------
    certs = active("certification")
    if concept in FOOD_CONTACT_CONCEPTS and not certs:
        push("certification", 100, "食品接触类产品涉及目的国法规（FDA/LFGB），缺少认证要求会阻塞合规报价")
    elif concept in FOOD_CONTACT_CONCEPTS and certs:
        have = set(certs.split("|"))
        if not (have & FOOD_CONTACT_CERTS):
            push("certification", 100, f"已提及认证 {sorted(have)} 但缺少食品接触类认证（FDA/LFGB 等）")

    # 2) quote blockers -------------------------------------------------------
    blocking = [f for f in BASE_REQUIRED_FOR_QUOTE if not active(f)]
    incoterm = active("incoterm")
    if incoterm in PORT_REQUIRED_INCOTERMS and not active("destination_port"):
        blocking.append("destination_port")
    for f in blocking:
        weight = 95 if f in ("product", "quantity", "incoterm") else 90
        why = "报价必需字段，缺少则无法生成正式报价"
        if f == "incoterm":
            why = "贸易术语决定报价口径（是否含运费保险），为报价必需项"
        if f == "destination_port" and incoterm:
            why = f"{incoterm} 条款下需要目的港核算海运费"
        push(f, weight, why)

    # 3) conflicts ------------------------------------------------------------
    for fld, v in values.items():
        if v.get("status") == "conflicting":
            push(fld, 80, f"客户消息中该字段存在矛盾表述（{v.get('value')}），必须先澄清")

    # 4) high information gain attributes -------------------------------------
    for fld in ("color", "spec", "material", "packaging"):
        if active(fld):
            continue
        gain = _split_score(products, fld) * 40
        if gain <= 0:
            continue
        price_note = FIELD_DEFS[fld].price_impact
        reason = f"候选产品集区分度高（信息增益 {gain:.0f}）" + ("，且影响价格" if price_note else "")
        push(fld, 40 + gain, reason)

    if not active("target_price") and products:
        push("target_price", 30, "目标价有助于在候选产品中快速收敛，避免报价落空")

    if not active("lead_time") and products:
        push("lead_time", 25, "交期影响生产安排与报价有效期判断")

    if not active("customization") and products:
        has_logo = any("logo" in (p.customization or "").lower() or "定制" in (p.customization or "") for p in products)
        if has_logo:
            push("customization", 20, "候选产品支持定制，Logo 印刷影响单价与打样时间")

    # previously asked questions are heavily de-prioritized
    asked = set(db.scalars(
        select(ClarificationLog.field).where(
            ClarificationLog.org_id == org_id,
            ClarificationLog.status.in_(["open", "answered"]),
        ).distinct()))
    for c in scored:
        if c["field"] in asked:
            c["priority_score"] -= 60
            c["reason"] += "（此前已问过，除非信息仍缺失否则降低优先级）"

    scored.sort(key=lambda c: -c["priority_score"])
    # de-duplicate fields keeping the highest scored entry
    seen, unique = set(), []
    for c in scored:
        if c["field"] not in seen:
            seen.add(c["field"])
            unique.append(c)
    return unique


def recommend(db: Session, org_id: int, inquiry_id: int, values: dict,
              persist: bool = True) -> dict:
    """One primary question + secondary list. Optionally persist open question."""
    candidates = build_candidates(db, org_id, values)
    primary = candidates[0] if candidates else None
    secondary = candidates[1:4]
    if persist and primary:
        existing = db.scalar(select(ClarificationLog).where(
            ClarificationLog.org_id == org_id,
            ClarificationLog.inquiry_id == inquiry_id,
            ClarificationLog.field == primary["field"],
            ClarificationLog.status == "open"))
        if existing is None:
            db.add(ClarificationLog(
                org_id=org_id, inquiry_id=inquiry_id, field=primary["field"],
                question_en=primary["question_en"], question_zh=primary["question_zh"],
                reason=primary["reason"], priority_score=primary["priority_score"],
            ))
            db.flush()
    return {"primary": primary, "secondary": secondary}
