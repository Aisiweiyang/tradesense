"""Cross-document rules engine tests (deterministic, evidence-backed)."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest

from app.models import (Customer, Document, DocumentField, DocRuleConfig,
                        Shipment, ShipmentIssue)
from app.services.doc_rules import run_rules


def _mk_world(db, org):
    """Shipment + helper to add docs/fields directly (bypassing PDF pipeline)."""
    shipment = Shipment(org_id=org.id, shipment_no="SH-TEST-0001",
                        port_of_loading="Ningbo", port_of_discharge="Hamburg")
    db.add(shipment)
    db.flush()

    docs: dict[str, Document] = {}

    def doc(dtype):
        if dtype not in docs:
            d = Document(org_id=org.id, shipment_id=shipment.id, doc_type=dtype,
                         version=1, file_path=f"x/{dtype}.pdf", status="extracted", pages=1)
            db.add(d)
            db.flush()
            docs[dtype] = d
        return docs[dtype]

    def field(dtype, name, value, page=1, text="line"):
        f = DocumentField(org_id=org.id, document_id=doc(dtype).id, field_name=name,
                          value=value, confidence=0.9, evidence_page=page,
                          evidence_text=text or f"{name}: {value}", source="extracted")
        db.add(f)
        db.flush()
        return f

    return shipment, field


def _titles(issues):
    return [i["title"] for i in issues]


def _by_rule(issues, code):
    return [i for i in issues if i["rule_code"] == code]


def test_amount_mismatch_high(db, org):
    shipment, field = _mk_world(db, org)
    field("invoice", "total_amount", "48,620.00")
    field("letter_of_credit", "lc_amount", "46,820.00")
    issues = run_rules(db, org.id, shipment)
    hits = _by_rule(issues, "amount_vs_lc")
    assert len(hits) == 1 and hits[0]["severity"] == "high"
    assert "48,620.00" in hits[0]["title"] and "46,820.00" in hits[0]["title"]
    assert len(json.loads(hits[0]["evidence_json"])) == 2


def test_amount_equal_no_issue(db, org):
    shipment, field = _mk_world(db, org)
    field("invoice", "total_amount", "46,820.00")
    field("letter_of_credit", "lc_amount", "46,820.00")
    assert _by_rule(run_rules(db, org.id, shipment), "amount_vs_lc") == []


def test_to_order_consignee(db, org):
    shipment, field = _mk_world(db, org)
    field("bill_of_lading", "consignee", "TO ORDER")
    field("letter_of_credit", "consignee", "TO ORDER OF ABC BANK")
    hits = _by_rule(run_rules(db, org.id, shipment), "lc_consignee")
    assert len(hits) == 1 and hits[0]["severity"] == "high"
    assert hits[0]["expected_value"] == "TO ORDER OF ABC BANK"
    assert hits[0]["actual_value"] == "TO ORDER"


def test_consignee_match_no_issue(db, org):
    shipment, field = _mk_world(db, org)
    field("bill_of_lading", "consignee", "HausKonzept GmbH")
    field("letter_of_credit", "consignee", "HausKonzept GmbH")
    assert _by_rule(run_rules(db, org.id, shipment), "lc_consignee") == []


def test_gross_weight_beyond_tolerance(db, org):
    shipment, field = _mk_world(db, org)
    field("packing_list", "gross_weight", "12,480.00")
    field("bill_of_lading", "gross_weight", "12,840.00")  # ~2.4% off
    hits = _by_rule(run_rules(db, org.id, shipment), "gross_weight_match")
    assert len(hits) == 1 and hits[0]["severity"] == "medium"


def test_gross_weight_within_tolerance(db, org):
    shipment, field = _mk_world(db, org)
    field("packing_list", "gross_weight", "12,480.00")
    field("bill_of_lading", "gross_weight", "12,500.00")  # ~0.16% < 0.5%
    assert _by_rule(run_rules(db, org.id, shipment), "gross_weight_match") == []


def test_gross_weight_tolerance_param_override(db, org):
    shipment, field = _mk_world(db, org)
    db.add(DocRuleConfig(org_id=org.id, rule_code="gross_weight_match", enabled=True,
                         customer_id=None, params_json='{"tolerance_pct": 0.0}'))
    db.flush()
    field("packing_list", "gross_weight", "12,480.00")
    field("bill_of_lading", "gross_weight", "12,500.00")
    assert len(_by_rule(run_rules(db, org.id, shipment), "gross_weight_match")) == 1


def test_hs_code_mismatch(db, org):
    shipment, field = _mk_world(db, org)
    field("invoice", "hs_code", "8467.29")
    field("customs_declaration", "hs_code", "8467.21")
    hits = _by_rule(run_rules(db, org.id, shipment), "hs_code_match")
    assert len(hits) == 1 and hits[0]["severity"] == "medium"


def test_description_difference_low(db, org):
    shipment, field = _mk_world(db, org)
    field("invoice", "description", "Cordless Drill")
    field("letter_of_credit", "description", "Electric Hand Drill")
    hits = _by_rule(run_rules(db, org.id, shipment), "goods_description")
    assert len(hits) == 1 and hits[0]["severity"] == "low"


def test_missing_docs_far_cutoff_medium(db, org):
    shipment, field = _mk_world(db, org)
    shipment.cutoff_at = datetime.now(timezone.utc) + timedelta(days=10)
    field("invoice", "total_amount", "1,000.00")
    hits = _by_rule(run_rules(db, org.id, shipment), "missing_docs")
    assert len(hits) == 1 and hits[0]["severity"] == "medium"
    assert "bill_of_lading" in hits[0]["actual_value"]


def test_missing_docs_within_24h_high(db, org):
    shipment, field = _mk_world(db, org)
    shipment.cutoff_at = datetime.now(timezone.utc) + timedelta(hours=6)
    hits = _by_rule(run_rules(db, org.id, shipment), "missing_docs")
    assert len(hits) == 1 and hits[0]["severity"] == "high"
    assert "24" in hits[0]["title"]


def test_missing_docs_no_cutoff_low(db, org):
    shipment, field = _mk_world(db, org)
    shipment.cutoff_at = None
    hits = _by_rule(run_rules(db, org.id, shipment), "missing_docs")
    assert len(hits) == 1 and hits[0]["severity"] == "low"


def test_rule_disabled_globally(db, org):
    shipment, field = _mk_world(db, org)
    field("invoice", "total_amount", "48,620.00")
    field("letter_of_credit", "lc_amount", "46,820.00")
    db.add(DocRuleConfig(org_id=org.id, rule_code="amount_vs_lc", enabled=False,
                         customer_id=None, params_json="{}"))
    db.commit()
    assert _by_rule(run_rules(db, org.id, shipment), "amount_vs_lc") == []


def test_customer_specific_override_wins(db, org):
    c = Customer(org_id=org.id, company_name="例外客户")
    db.add(c)
    db.flush()
    shipment, field = _mk_world(db, org)
    shipment.customer_id = c.id
    field("invoice", "total_amount", "48,620.00")
    field("letter_of_credit", "lc_amount", "46,820.00")
    # global disables, customer re-enables
    db.add(DocRuleConfig(org_id=org.id, rule_code="amount_vs_lc", enabled=False,
                         customer_id=None, params_json="{}"))
    db.add(DocRuleConfig(org_id=org.id, rule_code="amount_vs_lc", enabled=True,
                         customer_id=c.id, params_json="{}"))
    db.commit()
    assert len(_by_rule(run_rules(db, org.id, shipment), "amount_vs_lc")) == 1


def test_stable_severity_ordering(db, org):
    shipment, field = _mk_world(db, org)
    shipment.cutoff_at = datetime.now(timezone.utc) + timedelta(hours=6)
    field("invoice", "total_amount", "48,620.00")
    field("letter_of_credit", "lc_amount", "46,820.00")
    issues = run_rules(db, org.id, shipment)
    order = {"high": 0, "medium": 1, "low": 2}
    sevs = [order[i["severity"]] for i in issues]
    assert sevs == sorted(sevs)


def test_no_lc_means_no_lc_rules(db, org):
    shipment, field = _mk_world(db, org)
    field("invoice", "total_amount", "48,620.00")
    issues = run_rules(db, org.id, shipment)
    assert _by_rule(issues, "amount_vs_lc") == []
    assert _by_rule(issues, "lc_consignee") == []
    assert _by_rule(issues, "goods_description") == []
