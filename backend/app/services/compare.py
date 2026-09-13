"""Multi-supplier comparison for a product.

Deterministic scoring: cost (50%) + lead time (30%) + supplier reliability (20%).
Every row carries per-factor explanations so the buyer can see WHY one supplier
ranks above another. Works standalone via API and feeds the quotation module.
"""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Product, Supplier, SupplierProduct

WEIGHTS = {"cost": 0.5, "lead_time": 0.3, "reliability": 0.2}


def _better_ratio(value: float, best: float) -> float:
    """0..1 relative to the best observed offer (best/1.0). A 6% price gap thus
    costs ~3 points of 50 — so lead time and reliability can legitimately
    outrank a slightly higher price."""
    if value <= 0 or best <= 0:
        return 1.0
    return max(0.0, min(1.0, best / value))


@dataclass
class QuoteRow:
    supplier_product: SupplierProduct
    supplier: Supplier
    total: float
    scores: dict  # {factor: {score(0-100), raw, detail}}


def compare_suppliers(db: Session, org_id: int, product: Product) -> list[QuoteRow]:
    rows = db.scalars(select(SupplierProduct).where(
        SupplierProduct.org_id == org_id,
        SupplierProduct.product_id == product.id)).all()
    if not rows:
        return []
    suppliers = {s.id: s for s in db.scalars(select(Supplier).where(
        Supplier.org_id == org_id, Supplier.id.in_([r.supplier_id for r in rows]))).all()}

    costs = [float(r.cost_price or 0) for r in rows]
    leads = [float(r.lead_time_days or 0) for r in rows]
    min_cost, min_lead = min(costs), min(leads)

    scored: list[QuoteRow] = []
    for r in rows:
        sup = suppliers.get(r.supplier_id)
        cost = float(r.cost_price or 0)
        lead = float(r.lead_time_days or 0)
        rel = float(sup.reliability_score if sup else 0.7)
        c_score = _better_ratio(cost, min_cost)
        l_score = _better_ratio(lead, min_lead)
        r_score = rel  # 0..1 already
        total = (c_score * WEIGHTS["cost"] + l_score * WEIGHTS["lead_time"]
                 + r_score * WEIGHTS["reliability"])
        scored.append(QuoteRow(
            supplier_product=r, supplier=sup, total=round(total * 100, 1),
            scores={
                "cost": {"score": round(c_score * 100, 1), "raw": cost,
                         "detail": f"成本 {cost:g} {r.currency}（最低 {min_cost:g}）"},
                "lead_time": {"score": round(l_score * 100, 1), "raw": lead,
                              "detail": f"交期 {lead:g} 天（最快 {min_lead:g} 天）"},
                "reliability": {"score": round(r_score * 100, 1), "raw": rel,
                                "detail": f"供应商可靠性 {rel:.2f}"},
            },
        ))

    # stable sort: total desc, then supplier_product id asc
    scored.sort(key=lambda q: (-q.total, q.supplier_product.id))
    return scored


def recommend_reason(rows: list[QuoteRow]) -> str:
    """One-line human explanation for the top-ranked supplier."""
    if not rows:
        return ""
    top = rows[0]
    factors = sorted(top.scores.items(), key=lambda kv: -kv[1]["score"])
    best = factors[0]
    label = {"cost": "成本最低", "lead_time": "交期最快", "reliability": "供应商最可靠"}.get(best[0], best[0])
    return f"推荐 {top.supplier.name if top.supplier else '默认供应商'}：{label}（综合 {top.total:g} 分）"
