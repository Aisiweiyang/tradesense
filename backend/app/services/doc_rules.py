"""Deterministic cross-document consistency rules for shipments.

Rules are code (never AI). Each rule can be disabled per-customer/global via
DocRuleConfig; params (e.g. weight tolerance) are per rule too. Every issue
carries explicit evidence: which document, which field, which page, original
line — so a documentary checker can verify by eye.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import (DEFAULT_REQUIRED_DOCS, DocRuleConfig, Document,
                      DocumentField, ShipmentIssue)
from .doc_extractor import as_number, normalize_value

DEFAULT_PARAMS: dict[str, dict] = {
    "gross_weight_match": {"tolerance_pct": 0.5},
}

RULE_LABELS = {
    "amount_vs_lc": "发票金额与信用证不一致",
    "lc_consignee": "提单收货人与信用证要求不一致",
    "gross_weight_match": "装箱单与提单毛重不一致",
    "hs_code_match": "发票与报关单 HS Code 不一致",
    "goods_description": "品名表述与信用证不一致",
    "missing_docs": "必备单证缺失",
}


def rule_enabled(db: Session, org_id: int, customer_id: int | None, rule_code: str) -> tuple[bool, dict]:
    """Customer-specific config overrides global; defaults: enabled + DEFAULT_PARAMS."""
    params = dict(DEFAULT_PARAMS.get(rule_code, {}))
    enabled = True
    rows = db.scalars(select(DocRuleConfig).where(
        DocRuleConfig.org_id == org_id, DocRuleConfig.rule_code == rule_code)).all()
    for row in rows:
        if row.customer_id is not None and row.customer_id != customer_id:
            continue
        try:
            cfg = json.loads(row.params_json or "{}")
        except json.JSONDecodeError:
            cfg = {}
        params.update(cfg)
        enabled = row.enabled
        if row.customer_id is not None:
            break  # customer-specific wins
    return enabled, params


def _field_map(fields: list[DocumentField]) -> dict[tuple[str, str], DocumentField]:
    out: dict[tuple[str, str], DocumentField] = {}
    for f in fields:
        key = (f.document.doc_type, f.field_name)
        if key not in out:  # first (highest-version) document wins
            out[key] = f
    return out


def _ev(field: DocumentField | None) -> list[dict]:
    if field is None:
        return []
    return [{
        "doc_id": field.document_id, "doc_type": field.document.doc_type,
        "field": field.field_name, "page": field.evidence_page,
        "text": field.evidence_text, "value": field.value,
    }]


def run_rules(db: Session, org_id: int, shipment) -> list[dict]:
    """Return fresh issue dicts for the shipment (does not persist)."""
    docs = db.scalars(select(Document).where(
        Document.org_id == org_id, Document.shipment_id == shipment.id,
        Document.status.in_(["extracted", "verified", "needs_manual"]))
        .order_by(Document.version.desc())).all()
    all_fields = db.scalars(select(DocumentField).where(
        DocumentField.org_id == org_id,
        DocumentField.document_id.in_([d.id for d in docs] or [0]))).all()
    fm = _field_map(all_fields)
    doc_type_ids = {d.doc_type: d.id for d in docs}
    uploaded_types = set(doc_type_ids)

    issues: list[dict] = []

    def add(rule_code: str, severity: str, issue_type: str, title: str,
            expected: str, actual: str, evidence: list[dict]):
        issues.append({
            "severity": severity, "issue_type": issue_type, "rule_code": rule_code,
            "title": title, "expected_value": expected, "actual_value": actual,
            "evidence_json": json.dumps(evidence, ensure_ascii=False),
        })

    customer_id = shipment.customer_id

    def check(code: str) -> tuple[bool, dict]:
        return rule_enabled(db, org_id, customer_id, code)

    # ---- 1. invoice amount vs LC amount ---------------------------------
    if check("amount_vs_lc")[0]:
        inv_amt = fm.get(("invoice", "total_amount"))
        lc_amt = fm.get(("letter_of_credit", "lc_amount")) or fm.get(("letter_of_credit", "total_amount"))
        if inv_amt and lc_amt:
            a, b = as_number(inv_amt.value), as_number(lc_amt.value)
            if a is not None and b is not None and abs(a - b) > 0.005:
                add("amount_vs_lc", "high", "conflict",
                    f"商业发票金额 USD {a:,.2f} 与信用证金额 USD {b:,.2f} 不一致",
                    lc_amt.value, inv_amt.value, _ev(inv_amt) + _ev(lc_amt))

    # ---- 2. B/L consignee vs LC requirement ------------------------------
    if check("lc_consignee")[0]:
        bl_con = fm.get(("bill_of_lading", "consignee"))
        lc_con = fm.get(("letter_of_credit", "consignee"))
        if bl_con and lc_con:
            if normalize_value(bl_con.value) != normalize_value(lc_con.value):
                add("lc_consignee", "high", "conflict",
                    f"提单收货人写为 “{bl_con.value}”，信用证要求 “{lc_con.value}”",
                    lc_con.value, bl_con.value, _ev(bl_con) + _ev(lc_con))

    # ---- 3. gross weight: packing list vs B/L ----------------------------
    enabled, params = check("gross_weight_match")
    if enabled:
        pl_gw = fm.get(("packing_list", "gross_weight"))
        bl_gw = fm.get(("bill_of_lading", "gross_weight"))
        if pl_gw and bl_gw:
            a, b = as_number(pl_gw.value), as_number(bl_gw.value)
            tol = float(params.get("tolerance_pct", 0.5))
            if a is not None and b is not None and a > 0:
                if abs(a - b) / max(a, b) * 100 > tol:
                    add("gross_weight_match", "medium", "conflict",
                        f"装箱单总毛重 {a:,.2f} KG 与提单 {b:,.2f} KG 超出允差 {tol}%"
                        .replace("0.5% tol", ""),
                        pl_gw.value, bl_gw.value, _ev(pl_gw) + _ev(bl_gw))

    # ---- 4. HS code: invoice vs customs declaration ------------------------
    if check("hs_code_match")[0]:
        inv_hs = fm.get(("invoice", "hs_code"))
        cus_hs = fm.get(("customs_declaration", "hs_code"))
        if inv_hs and cus_hs:
            if normalize_value(inv_hs.value) != normalize_value(cus_hs.value):
                add("hs_code_match", "medium", "conflict",
                    f"发票 HS Code 为 {inv_hs.value}，报关单为 {cus_hs.value}",
                    inv_hs.value, cus_hs.value, _ev(inv_hs) + _ev(cus_hs))

    # ---- 5. goods description vs LC ---------------------------------------
    if check("goods_description")[0]:
        inv_desc = fm.get(("invoice", "description"))
        lc_desc = fm.get(("letter_of_credit", "description"))
        if inv_desc and lc_desc:
            if normalize_value(inv_desc.value) != normalize_value(lc_desc.value):
                add("goods_description", "low", "conflict",
                    f"品名 “{inv_desc.value}” 与信用证 “{lc_desc.value}” 表述不同",
                    lc_desc.value, inv_desc.value, _ev(inv_desc) + _ev(lc_desc))

    # ---- 6. missing required docs (+ cutoff countdown) ---------------------
    enabled, _ = check("missing_docs")
    if enabled:
        try:
            required = set(json.loads(shipment.required_docs_json or "[]"))
        except json.JSONDecodeError:
            required = set(DEFAULT_REQUIRED_DOCS)
        missing = sorted(required - uploaded_types)
        if missing:
            within_24h = (shipment.cutoff_at is not None and (
                datetime.now(timezone.utc) <= shipment.cutoff_at <=
                datetime.now(timezone.utc) + timedelta(hours=24)))
            evidence = [{"doc_type": t, "field": "-", "page": None, "text": "未上传"}
                        for t in missing]
            if within_24h:
                title = f"单证缺失：{', '.join(missing)}；距截单时间不足 24 小时"
                sev = "high"
            else:
                title = f"必备单证尚未上传：{', '.join(missing)}"
                sev = "medium" if shipment.cutoff_at else "low"
            add("missing_docs", sev, "missing", title, ", ".join(sorted(required)),
                "缺失: " + ", ".join(missing), evidence)

    # sort: severity then rule for stable output
    order = {"high": 0, "medium": 1, "low": 2}
    issues.sort(key=lambda i: (order[i["severity"]], i["rule_code"]))
    return issues


def refresh_issues(db: Session, org_id: int, shipment, actor_user_id: int | None = None) -> int:
    """Regenerate open issues; human-processed issues are never touched."""
    from ..models import ShipmentIssue

    fresh = run_rules(db, org_id, shipment)
    open_issues = db.scalars(select(ShipmentIssue).where(
        ShipmentIssue.org_id == org_id, ShipmentIssue.shipment_id == shipment.id,
        ShipmentIssue.status == "open")).all()
    open_keys = {(i.rule_code, i.expected_value, i.actual_value, i.title) for i in open_issues}
    fresh_keys = {(i["rule_code"], i["expected_value"], i["actual_value"], i["title"]) for i in fresh}
    # remove stale open issues that no longer fire
    for issue in open_issues:
        key = (issue.rule_code, issue.expected_value, issue.actual_value, issue.title)
        if key not in fresh_keys:
            db.delete(issue)
    # add new findings
    created = 0
    for data in fresh:
        key = (data["rule_code"], data["expected_value"], data["actual_value"], data["title"])
        if key in open_keys:
            continue
        db.add(ShipmentIssue(org_id=org_id, shipment_id=shipment.id,
                             handler_user_id=actor_user_id, **data))
        created += 1
    db.flush()
    return created
