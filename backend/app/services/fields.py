"""Canonical requirement field definitions — single source of truth.

Each field: labels, whether it blocks formal quoting, weights for completeness,
and flags used by the clarification algorithm.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class FieldDef:
    name: str
    label_zh: str
    label_en: str
    completeness_weight: int = 0          # share of the 100-point completeness score
    required_for_quote: bool = False      # missing => cannot produce a formal quote
    price_impact: bool = False            # affects quotation price
    lead_time_impact: bool = False        # affects delivery time
    cert_related: bool = False            # regulatory/certification relevance
    options: tuple = field(default_factory=tuple)  # hint of typical values (advisory)


FIELD_DEFS: dict[str, FieldDef] = {d.name: d for d in [
    FieldDef("product", "产品", "Product", 20, required_for_quote=True, price_impact=True),
    FieldDef("material", "材质", "Material", 8, price_impact=True),
    FieldDef("color", "颜色", "Color", 0),
    FieldDef("spec", "规格/容量/尺寸", "Spec", 5, price_impact=True),
    FieldDef("quantity", "数量", "Quantity", 15, required_for_quote=True, price_impact=True),
    FieldDef("target_price", "目标价格", "Target price", 5, price_impact=True),
    FieldDef("destination_country", "目的国", "Destination country", 10, required_for_quote=True),
    FieldDef("destination_port", "目的港", "Destination port", 10),
    FieldDef("incoterm", "贸易术语", "Incoterm", 10, required_for_quote=True, price_impact=True,
             options=("EXW", "FOB", "CIF", "DDP")),
    FieldDef("packaging", "包装", "Packaging", 5, price_impact=True),
    FieldDef("customization", "定制要求", "Customization", 0, price_impact=True, lead_time_impact=True),
    FieldDef("certification", "认证要求", "Certification", 7, cert_related=True,
             options=("FDA", "LFGB", "CE", "RoHS", "BPA-free", "CA Prop 65")),
    FieldDef("lead_time", "交期", "Lead time", 5, lead_time_impact=True),
    FieldDef("payment_terms", "付款方式", "Payment terms", 0),
    FieldDef("sample", "样品", "Sample", 0),
    FieldDef("shipping_method", "运输方式", "Shipping method", 0),
    FieldDef("notes", "其他说明", "Notes", 0),
]}

# Weight sum must be 100 so completeness stays interpretable.
assert sum(d.completeness_weight for d in FIELD_DEFS.values()) == 100

# Fields that must be present before a formal quote is allowed.
# destination_port becomes blocking when incoterm needs a destination leg.
BASE_REQUIRED_FOR_QUOTE = ["product", "quantity", "destination_country", "incoterm"]
PORT_REQUIRED_INCOTERMS = {"CIF", "DDP", "DAP", "CFR"}

# Food-contact product concepts require at least one food-contact certification
# before formal quoting (configurable, conservative default for beginners).
FOOD_CONTACT_CONCEPTS = {"insulated_bottle", "mug", "glass_cup", "plastic_bottle", "food_container", "baby_bottle"}
FOOD_CONTACT_CERTS = {"FDA", "LFGB", "EC1935/2004", "food_grade", "CPC", "CA Prop 65"}


def completeness_breakdown(slots: dict) -> dict:
    """Return {score, confirmed:[field], missing:[field], conflicting:[field]}.

    `slots` maps field -> {status: ...} (as produced by RequirementService.active_values).
    A field counts as confirmed when its slot status is active/unconstrained
    (a deliberate "no requirement" also counts as knowledge).
    """
    confirmed, missing, conflicting = [], [], []
    score = 0

    def status_of(name: str) -> str:
        slot = slots.get(name)
        if slot is None:
            return "unknown"
        if isinstance(slot, dict):
            return slot.get("status") or "unknown"
        return getattr(slot, "status", "unknown")

    for name, d in FIELD_DEFS.items():
        if d.completeness_weight <= 0:
            continue
        st = status_of(name)
        if st in ("unknown", "replaced"):
            missing.append(name)
        elif st == "conflicting":
            conflicting.append(name)
        else:
            confirmed.append(name)
            score += d.completeness_weight
    return {"score": min(score, 100), "confirmed": confirmed, "missing": missing, "conflicting": conflicting}
