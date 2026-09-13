"""Two-stage product matching.

Stage 1 (recall): token/synonym based candidate retrieval over product text.
Stage 2 (deterministic rerank): weighted, explainable scoring with HARD filters.
Hard conditions never get masked by other scores — failing products are either
excluded (with reason) or flagged as risky candidates.
"""
from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass, field as dc_field
from datetime import timedelta, timezone
from datetime import datetime as dt

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import MatchResult, Product, Supplier
from . import normalization as norm
from .fields import FOOD_CONTACT_CERTS, FOOD_CONTACT_CONCEPTS

# --------------------------------------------------------------------- weights
DEFAULT_WEIGHTS = {
    "category": 20, "material": 10, "color": 6, "spec": 6, "quantity_vs_moq": 10,
    "price_fit": 14, "certification": 12, "customization": 8, "lead_time": 6,
    "destination": 3, "supplier_reliability": 3, "freshness": 2,
}

_TOKEN_RE = re.compile(r"[a-z0-9]+")


def _tokens(text: str) -> set[str]:
    return set(_TOKEN_RE.findall((text or "").lower()))


@dataclass
class HardFailure:
    dimension: str
    reason: str


@dataclass
class MatchOutcome:
    product: Product
    total_score: float
    scores: dict
    met: list
    unmet: list
    excluded: bool
    exclude_reason: str
    is_alternative: bool
    data_snapshot: dict


def recall_candidates(db: Session, org_id: int, values: dict, limit: int = 60) -> list[Product]:
    """Stage 1: candidate recall via concept synonyms + material + category keywords."""
    concept = (values.get("product") or {}).get("normalized") or ""
    query_terms: list[str] = []
    if concept:
        query_terms.extend(norm.concept_synonyms(concept))
        query_terms.append(concept.replace("_", " "))
    material = (values.get("material") or {}).get("normalized") or ""
    if material and material != "__unconstrained__":
        query_terms.append(material.replace("_", " "))

    products = db.scalars(
        select(Product).where(Product.org_id == org_id, Product.is_active == True)  # noqa: E712
    ).all()
    if not query_terms:
        return products[:limit]

    term_tokens = [t for term in query_terms for t in _tokens(term)]
    zh_terms = [t for term in query_terms for t in re.findall(r"[\u4e00-\u9fff]{2,}", term)]

    def score_product(p: Product) -> float:
        hay = " ".join([p.name_en, p.name_zh, p.category, p.keywords, p.description,
                        p.material, p.spec]).lower()
        hay_tokens = set(_TOKEN_RE.findall(hay))
        s = 0.0
        for t in term_tokens:
            if t in hay_tokens:
                s += 1.0
            elif any(t in tok for tok in hay_tokens):
                s += 0.5
        for t in zh_terms:
            if t in hay:
                s += 2.0
        return s

    scored = sorted(((score_product(p), p) for p in products), key=lambda x: -x[0])
    candidates = [p for s, p in scored if s > 0]
    # concept-less or zero-hit: fall back to everything so rerank can still judge
    return (candidates or [p for _, p in scored])[:limit]


def _price_tiers(product: Product) -> list[dict]:
    try:
        tiers = json.loads(product.price_tiers_json or "[]")
        return sorted(tiers, key=lambda t: t.get("min_qty", 0))
    except json.JSONDecodeError:
        return []


def tier_price(product: Product, qty: int) -> float | None:
    """Unit price for quantity from ladder pricing (highest applicable tier)."""
    price = None
    for t in _price_tiers(product):
        if qty >= (t.get("min_qty") or 0):
            price = float(t.get("unit_price") or 0)
    if price is None and _price_tiers(product):
        price = float(_price_tiers(product)[0].get("unit_price") or 0)
    return price


def evaluate_product(p: Product, values: dict, weights: dict, supplier: Supplier | None,
                     now: dt) -> MatchOutcome:
    """Stage 2: deterministic, explainable rerank with hard filters."""
    scores: dict[str, dict] = {}
    met: list[str] = []
    unmet: list[str] = []
    hard_failures: list[HardFailure] = []

    def add(dim: str, score: float, detail: str):
        max_w = weights.get(dim, 0)
        scores[dim] = {"score": round(min(max(score, 0.0), 1.0) * max_w, 2), "max": max_w, "detail": detail}

    def get(fld):
        v = values.get(fld) or {}
        return v

    def active(fld) -> str:
        v = get(fld)
        if not v or v.get("status") in ("unknown", "replaced") or v.get("normalized") == "__unconstrained__":
            return ""
        return v.get("normalized") or ""

    # ---------------- HARD: certifications --------------------------------
    req_certs = [c for c in active("certification").split("|") if c]
    pcerts = set(json.loads(p.certifications_json or "[]"))
    if req_certs:
        missing_certs = [c for c in req_certs if c not in pcerts]
        if missing_certs:
            hard_failures.append(HardFailure(
                "certification", f"缺少客户明确要求的认证: {', '.join(missing_certs)}"))
        else:
            met.append(f"认证齐全: {', '.join(req_certs)}")
    concept = active("product")
    if concept in FOOD_CONTACT_CONCEPTS and not (pcerts & FOOD_CONTACT_CERTS):
        # food-contact without any food-grade cert is a compliance risk, not silent
        unmet.append("食品接触类产品缺少食品级认证（FDA/LFGB 等），如客户需要食品接触用途须先确认")
        scores["_risk_food_contact"] = {"score": 0, "max": 0, "detail": "food-contact compliance risk"}
    add("certification", 1.0 if (not req_certs or not [c for c in req_certs if c not in pcerts]) else 0.0,
        f"产品认证 {sorted(pcerts) or '无'} / 客户要求 {req_certs or '未说明'}" if pcerts or req_certs else "双方均未涉及认证")

    # ---------------- HARD: max price --------------------------------------
    qty_val = get("quantity")
    qty = int(float(qty_val.get("normalized") or 0)) if (qty_val.get("normalized") or "").replace(".", "").isdigit() else 0
    price = tier_price(p, qty or (p.moq or 1))
    target_raw = active("target_price")
    target_price = None
    if target_raw:
        try:
            target_price = float(target_raw.split("|")[0])
        except (ValueError, IndexError):
            target_price = None
    if target_price and price:
        if price > target_price * 1.0:  # hard ceiling: cost tier above target
            hard_failures.append(HardFailure(
                "price_fit", f"阶梯单价 ${price:g} 高于客户目标价 ${target_price:g}"))
        elif price <= target_price * 0.95:
            met.append(f"单价 ${price:g} 满足目标价 ${target_price:g}")
    add("price_fit",
        1.0 if (not target_price or not price) else (1.0 if price <= target_price * 0.95 else max(0.0, 1 - (price - target_price) / max(target_price, 0.01))),
        f"产品单价 ${price if price is not None else '未知'} / 目标价 ${target_price if target_price else '未说明'}")

    # ---------------- HARD: deadline ---------------------------------------
    lead_req_raw = active("lead_time")
    if lead_req_raw and lead_req_raw.isdigit():
        need_days = int(lead_req_raw)
        if p.lead_time_days > need_days:
            hard_failures.append(HardFailure(
                "lead_time", f"生产周期 {p.lead_time_days} 天 超过客户要求 {need_days} 天"))
        else:
            met.append(f"交期满足: {p.lead_time_days} ≤ {need_days} 天")
    add("lead_time", 1.0 if not lead_req_raw else (1.0 if p.lead_time_days <= int(lead_req_raw or 0) else 0.0),
        f"生产周期 {p.lead_time_days} 天")

    # ---------------- HARD: forbidden material ------------------------------
    mat_active = active("material")
    forbidden = get("material").get("raw") or ""
    if re.search(r"\bno\b|\bwithout\b|不用|不要|不含", forbidden) and mat_active:
        pass  # negation handled by unconstrained/negation logic upstream
    if mat_active and mat_active != "__unconstrained__":
        p_mats = [m.strip() for m in (p.material or "").split(",") if m.strip()]
        if p_mats and mat_active.replace("_", " ") not in " ".join(p_mats).lower():
            unmet.append(f"材质不完全一致: 需求 {mat_active} / 产品 {', '.join(p_mats)}")
        else:
            met.append(f"材质匹配: {mat_active}")

    # ---------------- category / concept ------------------------------------
    if concept:
        if p.category == concept:
            met.append("产品类别完全匹配")
            add("category", 1.0, f"产品类别 = {p.category}")
        else:
            add("category", 0.0, f"产品类别 {p.category} ≠ 需求 {concept}")
    else:
        add("category", 0.4, "询盘未明确产品概念，按文本相关性计入")

    # ---------------- material score (soft when not contradicting) ----------
    if mat_active and mat_active != "__unconstrained__":
        p_mats = [m.strip().lower() for m in (p.material or "").split(",")]
        add("material", 1.0 if mat_active.replace("_", " ") in p_mats else 0.3,
            f"需求材质 {mat_active} / 产品 {p.material or '未标注'}")
    else:
        add("material", 0.6, "客户未限定材质")

    # ---------------- color --------------------------------------------------
    color = active("color")
    if color and color != "__unconstrained__":
        p_colors = [c.strip().lower() for c in (p.color or "").split(",")]
        add("color", 1.0 if color in p_colors else 0.3,
            f"需求颜色 {color} / 可供 {p.color or '未标注(通常可定制)'}")
    else:
        add("color", 0.8, "颜色无特殊要求")

    # ---------------- spec ---------------------------------------------------
    spec = active("spec")
    if spec:
        p_spec = (p.spec or "").lower().replace(" ", "")
        add("spec", 1.0 if spec.replace(" ", "") in p_spec else 0.2,
            f"需求规格 {spec} / 产品 {p.spec or '未标注'}")
    else:
        add("spec", 0.6, "规格未明确")

    # ---------------- quantity vs MOQ ---------------------------------------
    if qty:
        if qty >= p.moq:
            met.append(f"数量 {qty:,} 满足 MOQ {p.moq:,}")
            add("quantity_vs_moq", 1.0, f"{qty:,} ≥ MOQ {p.moq:,}")
        else:
            ratio = qty / max(p.moq, 1)
            # below MOQ is negotiable → strong penalty, visible risk, not hidden
            add("quantity_vs_moq", max(0.0, ratio - 0.1), f"{qty:,} 低于 MOQ {p.moq:,}（可协商）")
            unmet.append(f"数量 {qty:,} 低于该产品 MOQ {p.moq:,}，需与供应商协商")
    else:
        add("quantity_vs_moq", 0.5, "数量未明确，按 MOQ 评估")

    # ---------------- customization ------------------------------------------
    custom = active("customization")
    if custom:
        p_custom = (p.customization or "").lower()
        ok = any(k in p_custom for k in ("logo", "print", "oem", "odm", "custom", "定制", "印刷", "丝印"))
        add("customization", 1.0 if ok else 0.0,
            f"需求定制 {custom} / 产品支持 {p.customization or '未标注'}")
        if not ok:
            unmet.append("定制需求在该产品资料中未标注支持，需与供应商确认")
    else:
        add("customization", 0.8, "无定制要求")

    # ---------------- destination market -------------------------------------
    country_iso = (get("destination_country") or {}).get("normalized") or ""
    if p.markets and country_iso:
        allowed = [m.strip().upper() for m in p.markets.split(",")]
        if country_iso.upper() not in allowed and allowed not in ([""], ["ALL"]):
            hard_failures.append(HardFailure(
                "destination", f"产品备案市场 {p.markets} 不含目的国 {country_iso.upper()}"))
        else:
            met.append("目的国在产品可售市场内")
    add("destination", 0.8, f"市场备案: {p.markets or '无限制'}")

    # ---------------- supplier reliability -----------------------------------
    rel = supplier.reliability_score if supplier else 0.7
    add("supplier_reliability", float(rel or 0.7), f"供应商可靠性 {rel if supplier is None else rel}")

    # ---------------- freshness ----------------------------------------------
    fresh = 1.0
    if p.last_verified_at:
        age_days = (now - p.last_verified_at).days
        fresh = max(0.0, 1.0 - age_days / 365)
    add("freshness", fresh, "资料最近核验时间" + (f": {p.last_verified_at.date()}" if p.last_verified_at else ": 未核验"))

    total = sum(d["score"] for d in scores.values() if not d["max"] == 0)
    excluded = bool(hard_failures)
    exclude_reason = "；".join(h.reason for h in hard_failures)
    # a risky candidate can still be shown as alternative when it only misses
    # negotiable items; hard failures are excluded but reason is always shown
    is_alternative = excluded and len(hard_failures) == 1 and hard_failures[0].dimension == "price_fit"
    return MatchOutcome(
        product=p, total_score=round(total, 2), scores=scores, met=met, unmet=unmet,
        excluded=excluded, exclude_reason=exclude_reason, is_alternative=is_alternative,
        data_snapshot={"sku": p.sku, "source": p.data_source,
                       "last_verified_at": p.last_verified_at.isoformat() if p.last_verified_at else None,
                       "price_tiers": _price_tiers(p)},
    )


def match_products_for_inquiry(db: Session, org_id: int, values: dict,
                               weights: dict | None = None, top_n: int = 8) -> dict:
    """Run full two-stage matching and return ranked outcome objects (not persisted)."""
    weights = {**DEFAULT_WEIGHTS, **(weights or {})}
    now = dt.now(timezone.utc)
    candidates = recall_candidates(db, org_id, values)
    suppliers = {s.id: s for s in db.scalars(
        select(Supplier).where(Supplier.org_id == org_id)).all()} if candidates else {}

    outcomes: list[MatchOutcome] = []
    for p in candidates:
        outcomes.append(evaluate_product(p, values, weights, suppliers.get(p.supplier_id), now))

    # stable sort: score desc, then product id asc
    outcomes.sort(key=lambda o: (-o.total_score, o.product.id))
    viable = [o for o in outcomes if not o.excluded][:top_n]
    alternatives = [o for o in outcomes if o.excluded and o.is_alternative][:3]
    excluded_preview = [o for o in outcomes if o.excluded and not o.is_alternative][:3]
    return {
        "outcomes": outcomes, "viable": viable, "alternatives": alternatives,
        "excluded_preview": excluded_preview, "candidates_evaluated": len(candidates),
    }


def persist_match_results(db: Session, org_id: int, inquiry_id: int, values: dict,
                          weights: dict | None = None, top_n: int = 8) -> dict:
    """Match, persist a fresh MatchResult batch for the inquiry, return summary."""
    import uuid

    result = match_products_for_inquiry(db, org_id, values, weights, top_n)
    batch = uuid.uuid4().hex[:12]
    rank = 0
    for o in result["viable"] + result["alternatives"]:
        rank += 1
        db.add(MatchResult(
            org_id=org_id, inquiry_id=inquiry_id, product_id=o.product.id, batch_no=batch,
            total_score=o.total_score, scores_json=json.dumps(o.scores, ensure_ascii=False),
            met_json=json.dumps(o.met, ensure_ascii=False),
            unmet_json=json.dumps(o.unmet, ensure_ascii=False),
            excluded=o.excluded, exclude_reason=o.exclude_reason,
            is_alternative=o.is_alternative, rank=rank,
            data_snapshot_json=json.dumps(o.data_snapshot, ensure_ascii=False),
        ))
    return {
        "batch_no": batch,
        "candidates_evaluated": result["candidates_evaluated"],
        "viable": [o.product.id for o in result["viable"]],
        "alternatives": [o.product.id for o in result["alternatives"]],
        "excluded": [{"id": o.product.id, "reason": o.exclude_reason}
                     for o in result["excluded_preview"]],
    }
