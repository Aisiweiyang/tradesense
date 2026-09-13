"""Deterministic Chinese summary of an inquiry (no AI needed).

Structure follows the product spec: what the customer wants, quantity,
destination, target price, customization, certifications, lead time,
known / missing info, risks, suggested next step.
"""
from __future__ import annotations

from .fields import FIELD_DEFS, FOOD_CONTACT_CONCEPTS, FOOD_CONTACT_CERTS, PORT_REQUIRED_INCOTERMS
from .normalization import concept_labels

_LABEL = {name: d.label_zh for name, d in FIELD_DEFS.items()}


def _val(values: dict, field: str) -> str:
    v = values.get(field) or {}
    if v.get("status") == "unconstrained":
        return "客户表示无特殊要求"
    return v.get("value") or ""


def _risk_flags(values: dict) -> list[str]:
    risks = []
    for f, v in values.items():
        if v.get("status") == "conflicting":
            risks.append(f"{_LABEL.get(f, f)} 存在矛盾表述，需与客户确认（当前记录：{v.get('value')}）")
    concept = (values.get("product") or {}).get("normalized") or ""
    certs_raw = (values.get("certification") or {}).get("normalized") or ""
    certs = {c for c in certs_raw.split("|") if c}
    if concept in FOOD_CONTACT_CONCEPTS and not (certs & FOOD_CONTACT_CERTS):
        risks.append("产品属于食品接触类，但客户未明确认证要求（如 FDA / LFGB），正式报价前建议确认")
    incoterm = (values.get("incoterm") or {}).get("normalized") or ""
    port = _val(values, "destination_port")
    if incoterm in PORT_REQUIRED_INCOTERMS and not port:
        risks.append(f"贸易术语为 {incoterm}，但缺少目的港，无法准确核算海运费与保险")
    price_raw = (values.get("target_price") or {}).get("normalized") or ""
    if price_raw:
        try:
            target = float(price_raw.split("|")[0])
            if target and target < 0.8:
                risks.append("客户目标价格较低，请核对成本后再决定是否报价")
        except (ValueError, IndexError):
            pass
    return risks


def _next_step(values: dict, breakdown: dict) -> str:
    concept = (values.get("product") or {}).get("normalized") or ""
    if not concept:
        return "先确认客户想要的产品类别，可先发送目录请客户挑选"
    if breakdown["conflicting"]:
        return "优先与客户确认矛盾字段（颜色/数量等），再继续推进"
    blocking = [f for f in ("product", "quantity", "destination_country", "incoterm")
                if not _val(values, f)]
    if blocking:
        return f"补齐报价必需信息：{('、'.join(_LABEL.get(b, b) for b in blocking))}"
    return "信息基本齐全，可进入产品匹配并准备报价"


def build_summary(values: dict, breakdown: dict) -> dict:
    """values: {field: {value, normalized, status, ...}} from RequirementService."""
    concept = (values.get("product") or {}).get("normalized") or ""
    labels = concept_labels(concept)
    quantity = _val(values, "quantity")
    qty_unit = (values.get("quantity") or {}).get("unit") or "pcs"
    known = [f"{_LABEL[f]}：{_val(values, f)}" for f in FIELD_DEFS
             if _val(values, f) and f != "notes"]
    missing = [f for f in breakdown["missing"] if f != "notes"]
    summary = {
        "what": (f"{labels['label_zh']}" + (f"（材质：{_val(values, 'material')}）" if _val(values, "material") else "")
                 + (f"，颜色：{_val(values, 'color')}" if _val(values, "color") else "")) if concept else "",
        "quantity": quantity,
        "destination": " ".join(x for x in [_val(values, "destination_port"), _val(values, "destination_country")] if x),
        "target_price": _val(values, "target_price"),
        "customization": _val(values, "customization"),
        "certification": _val(values, "certification"),
        "lead_time": _val(values, "lead_time"),
        "incoterm": _val(values, "incoterm"),
        "packaging": _val(values, "packaging"),
        "spec": _val(values, "spec"),
        "payment_terms": _val(values, "payment_terms"),
        "known": known,
        "missing_zh": ["、".join([])] and [_LABEL.get(m, m) for m in missing],
        "conflicting_zh": [_LABEL.get(c, c) for c in breakdown["conflicting"]],
        "risks": _risk_flags(values),
        "next_step": _next_step(values, breakdown),
        "completeness": breakdown["score"],
    }
    return summary
