"""Shipment workbench API tests: upload pipeline, issues, rules, chase email."""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.seed import docgen
from tests.conftest import auth_headers


def _pdf_bytes(name: str, **kw) -> bytes:
    """Generate a real sample PDF and return its bytes."""
    p = Path("data") / "test_docs" / f"{uuid.uuid4().hex[:8]}-{name}.pdf"
    p.parent.mkdir(parents=True, exist_ok=True)
    builders = {
        "invoice.pdf": lambda: docgen.make_invoice(p, **{
            "invoice_no": "TS-INV-1", "total_amount": "48,620.00", "hs_code": "8467.29",
            "description": "Cordless Drill Set", "consignee": "HausKonzept GmbH", **kw}),
        "packing.pdf": lambda: docgen.make_packing_list(p, gross_weight=kw.get("gross_weight", "12,480.00")),
        "bl.pdf": lambda: docgen.make_bill_of_lading(p, consignee=kw.get("consignee", "TO ORDER"),
                                                     gross_weight=kw.get("bl_gross_weight", "12,480.00")),
        "lc.pdf": lambda: docgen.make_letter_of_credit(p, lc_amount=kw.get("lc_amount", "46,820.00"),
                                                       consignee=kw.get("lc_consignee", "TO ORDER OF ABC BANK"),
                                                       description=kw.get("lc_description", "Electric Hand Drill Set")),
        "cus.pdf": lambda: docgen.make_customs_declaration(p, hs_code=kw.get("cus_hs", "8467.21")),
        "scan.pdf": lambda: docgen.make_scan_like_pdf(p),
    }
    for key, build in builders.items():
        if name.endswith(key) or name == key:
            build()
            return p.read_bytes()
    raise ValueError(f"unknown doc name {name}")


@pytest.fixture()
def shipment(client):
    """A shipment with cutoff within 24h + the classic Hamburg document set."""
    cutoff = (datetime.now(timezone.utc) + timedelta(hours=6)).isoformat()
    r = client.post("/api/shipments", json={
        "order_no": "PO-TEST-1", "transport_mode": "sea",
        "port_of_loading": "Ningbo", "port_of_discharge": "Hamburg",
        "incoterm": "FOB", "cutoff_at": cutoff,
        "required_docs": ["invoice", "packing_list", "bill_of_lading"],
    }, headers=auth_headers(client))
    assert r.status_code == 201, r.text
    return r.json()


def _upload(client, headers, shipment_id, filename, content: bytes):
    return client.post(f"/api/shipments/{shipment_id}/documents",
                       files={"file": (filename, content, "application/pdf")}, headers=headers)


def test_create_and_get_shipment(client, shipment):
    assert shipment["shipment_no"].startswith("SH-")
    detail = client.get(f"/api/shipments/{shipment['id']}", headers=auth_headers(client)).json()
    assert detail["order_no"] == "PO-TEST-1"
    assert detail["documents"] == []


def test_create_shipment_without_optional_fields(client):
    r = client.post("/api/shipments", json={}, headers=auth_headers(client))
    assert r.status_code == 201
    assert r.json()["transport_mode"] == "sea"


def test_shipment_update(client, shipment):
    r = client.patch(f"/api/shipments/{shipment['id']}",
                     json={"status": "shipped", "notes": "改约"}, headers=auth_headers(client))
    assert r.json()["status"] == "shipped"


def test_org_isolation(client, other_org):
    headers = auth_headers(client)
    shipment = client.post("/api/shipments", json={}, headers=headers).json()
    other = client.post("/api/auth/login",
                        json={"email": "owner2@test.cn", "password": "password123"})
    oh = {"Authorization": f"Bearer {other.json()['access_token']}"}
    assert client.get(f"/api/shipments/{shipment['id']}", headers=oh).status_code == 404
    assert client.post(f"/api/shipments/{shipment['id']}/recheck", headers=oh).status_code == 404


def test_upload_invoice_extracted(client, shipment):
    headers = auth_headers(client)
    r = _upload(client, headers, shipment["id"], "invoice-0842.pdf", _pdf_bytes("invoice.pdf"))
    assert r.status_code == 201, r.text
    assert r.json()["status"] == "extracted"
    fields = client.get(f"/api/shipments/{shipment['id']}/fields", headers=headers).json()["items"]
    names = {f["field_name"] for f in fields}
    assert {"invoice_no", "total_amount", "hs_code", "description", "consignee"} <= names
    ev = next(f for f in fields if f["field_name"] == "total_amount")
    assert ev["evidence_page"] == 1 and "Total Amount" in ev["evidence_text"]


def test_upload_rejects_non_pdf(client, shipment):
    r = _upload(client, auth_headers(client), shipment["id"], "note.txt", b"hello")
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "bad_file_type"


def test_upload_oversize_rejected(client, shipment, monkeypatch):
    from app.services import doc_service
    monkeypatch.setattr(doc_service, "MAX_UPLOAD_MB", 1)
    big = _pdf_bytes("invoice.pdf") + b"\0" * (2 * 1024 * 1024)
    r = _upload(client, auth_headers(client), shipment["id"], "big.pdf", big)
    assert r.status_code == 413


def test_upload_scan_needs_manual(client, shipment):
    r = _upload(client, auth_headers(client), shipment["id"], "scan-inv.pdf", _pdf_bytes("scan.pdf"))
    assert r.json()["status"] == "needs_manual"


def test_second_upload_increments_version(client, shipment):
    h = auth_headers(client)
    v1 = _upload(client, h, shipment["id"], "invoice.pdf", _pdf_bytes("invoice.pdf")).json()
    v2 = _upload(client, h, shipment["id"], "invoice.pdf", _pdf_bytes("invoice.pdf")).json()
    assert v2["version"] == v1["version"] + 1


def test_classic_conflicts_detected(client, shipment):
    h = auth_headers(client)
    _upload(client, h, shipment["id"], "invoice.pdf", _pdf_bytes("invoice.pdf"))
    _upload(client, h, shipment["id"], "packing.pdf", _pdf_bytes("packing.pdf"))
    _upload(client, h, shipment["id"], "bl.pdf", _pdf_bytes("bl.pdf"))
    _upload(client, h, shipment["id"], "lc.pdf", _pdf_bytes("lc.pdf"))
    _upload(client, h, shipment["id"], "cus.pdf", _pdf_bytes("cus.pdf"))
    detail = client.get(f"/api/shipments/{shipment['id']}", headers=h).json()
    codes = {i["rule_code"]: i for i in detail["issues"]}
    assert "amount_vs_lc" in codes and codes["amount_vs_lc"]["severity"] == "high"
    assert "lc_consignee" in codes
    assert "gross_weight_match" not in codes  # within tolerance
    assert "hs_code_match" in codes
    assert "goods_description" in codes
    assert "missing_docs" not in codes  # all three required uploaded
    assert detail["risk"] == "high"
    # evidence carries page + text for UI jump
    ev = json.loads(json.dumps(codes["amount_vs_lc"]["evidence"]))
    assert ev and all(e["page"] == 1 and e["text"] for e in ev)


def test_manual_field_fix_resolves_conflict(client, shipment):
    h = auth_headers(client)
    _upload(client, h, shipment["id"], "invoice.pdf", _pdf_bytes("invoice.pdf"))
    _upload(client, h, shipment["id"], "packing.pdf", _pdf_bytes("packing.pdf"))
    _upload(client, h, shipment["id"], "bl.pdf", _pdf_bytes("bl.pdf"))
    _upload(client, h, shipment["id"], "lc.pdf", _pdf_bytes("lc.pdf"))
    fields = client.get(f"/api/shipments/{shipment['id']}/fields", headers=h).json()["items"]
    inv_amount = next(f for f in fields if f["doc_type"] == "invoice"
                      and f["field_name"] == "total_amount")
    r = client.patch(f"/api/shipments/fields/{inv_amount['id']}",
                     json={"value": "46,820.00"}, headers=h)
    assert r.json()["source"] == "manual"
    detail = client.get(f"/api/shipments/{shipment['id']}", headers=h).json()
    assert "amount_vs_lc" not in {i["rule_code"] for i in detail["issues"]}


def test_field_set_rejects_empty(client, shipment):
    h = auth_headers(client)
    _upload(client, h, shipment["id"], "invoice.pdf", _pdf_bytes("invoice.pdf"))
    fields = client.get(f"/api/shipments/{shipment['id']}/fields", headers=h).json()["items"]
    r = client.patch(f"/api/shipments/fields/{fields[0]['id']}", json={"value": ""}, headers=h)
    assert r.status_code == 422


def test_adopt_updates_target_field(client, shipment):
    h = auth_headers(client)
    _upload(client, h, shipment["id"], "invoice.pdf", _pdf_bytes("invoice.pdf"))
    _upload(client, h, shipment["id"], "packing.pdf", _pdf_bytes("packing.pdf"))
    _upload(client, h, shipment["id"], "bl.pdf", _pdf_bytes("bl.pdf"))
    _upload(client, h, shipment["id"], "lc.pdf", _pdf_bytes("lc.pdf"))
    detail = client.get(f"/api/shipments/{shipment['id']}", headers=h).json()
    issue = next(i for i in detail["issues"] if i["rule_code"] == "amount_vs_lc")
    r = client.post(f"/api/shipments/issues/{issue['id']}/action",
                    json={"action": "adopt"}, headers=h)
    assert r.json()["status"] == "adopted"
    fields = client.get(f"/api/shipments/{shipment['id']}/fields", headers=h).json()["items"]
    inv_amount = next(f for f in fields if f["doc_type"] == "invoice"
                      and f["field_name"] == "total_amount")
    assert inv_amount["value"] == issue["expected_value"]
    detail = client.get(f"/api/shipments/{shipment['id']}", headers=h).json()
    open_amounts = [i for i in detail["issues"]
                    if i["rule_code"] == "amount_vs_lc" and i["status"] == "open"]
    assert open_amounts == []  # conflict resolved
    adopted = [i for i in detail["issues"] if i["status"] == "adopted"]
    assert adopted and adopted[0]["resolution_note"]  # audit trail kept


def test_adopt_without_target_422(client, shipment):
    h = auth_headers(client)
    shipment_detail = client.get(f"/api/shipments/{shipment['id']}", headers=h).json()
    # missing docs issue has no adoptable field
    assert shipment_detail["issues"], "缺件异常应存在"
    missing_issue = next(i for i in shipment_detail["issues"] if i["issue_type"] == "missing")
    r = client.post(f"/api/shipments/issues/{missing_issue['id']}/action",
                    json={"action": "adopt"}, headers=h)
    assert r.status_code == 422


def test_ignore_requires_note(client, shipment):
    h = auth_headers(client)
    detail = client.get(f"/api/shipments/{shipment['id']}", headers=h).json()
    issue = detail["issues"][0]
    r = client.post(f"/api/shipments/issues/{issue['id']}/action",
                    json={"action": "ignore", "note": ""}, headers=h)
    assert r.status_code == 422
    r = client.post(f"/api/shipments/issues/{issue['id']}/action",
                    json={"action": "ignore", "note": "客户书面确认豁免"}, headers=h)
    assert r.json()["status"] == "ignored"


def test_assign_issue(client, shipment):
    h = auth_headers(client)
    detail = client.get(f"/api/shipments/{shipment['id']}", headers=h).json()
    issue = detail["issues"][0]
    r = client.post(f"/api/shipments/issues/{issue['id']}/action",
                    json={"action": "assign", "user_id": 1}, headers=h)
    assert r.json()["assigned_to_user_id"] == 1


def test_recheck_returns_new_issues(client, shipment):
    h = auth_headers(client)
    _upload(client, h, shipment["id"], "invoice.pdf", _pdf_bytes("invoice.pdf"))
    r = client.post(f"/api/shipments/{shipment['id']}/recheck", headers=h)
    assert r.status_code == 200
    codes = {i["rule_code"] for i in r.json()["issues"]}
    assert "missing_docs" in codes


def test_rules_list_and_disable(client, shipment):
    h = auth_headers(client)
    rules = client.get("/api/shipments/rules", headers=h).json()["items"]
    assert len(rules) == 6
    code = rules[0]["rule_code"]
    r = client.put(f"/api/shipments/rules/{code}",
                   json={"enabled": False, "params": {}}, headers=h)
    assert r.json()["enabled"] is False
    rules = client.get("/api/shipments/rules", headers=h).json()["items"]
    assert next(x for x in rules if x["rule_code"] == code)["has_override"] is True


def test_chase_email_references_issues(client, shipment):
    h = auth_headers(client)
    _upload(client, h, shipment["id"], "invoice.pdf", _pdf_bytes("invoice.pdf"))
    _upload(client, h, shipment["id"], "packing.pdf", _pdf_bytes("packing.pdf"))
    _upload(client, h, shipment["id"], "bl.pdf", _pdf_bytes("bl.pdf"))
    _upload(client, h, shipment["id"], "lc.pdf", _pdf_bytes("lc.pdf"))
    r = client.post(f"/api/shipments/{shipment['id']}/chase-email", headers=h)
    assert r.status_code == 201
    body = r.json()
    assert shipment["shipment_no"] in body["subject_en"]
    assert "48,620.00" in body["body_en"] and "46,820.00" in body["body_en"]
    assert "截单时间" in body["body_zh"]
    assert body["needs_confirmation"]


def test_get_document_file(client, shipment):
    h = auth_headers(client)
    doc = _upload(client, h, shipment["id"], "invoice.pdf", _pdf_bytes("invoice.pdf")).json()
    r = client.get(f"/api/shipments/documents/{doc['id']}/file", headers=h)
    assert r.status_code == 200
    assert r.content[:4] == b"%PDF"


def test_risk_first_sorting(client, shipment):
    h = auth_headers(client)
    _upload(client, h, shipment["id"], "invoice.pdf", _pdf_bytes("invoice.pdf"))
    items = client.get("/api/shipments?page_size=50", headers=h).json()["items"]
    assert items[0]["id"] == shipment["id"]  # has high issue → first
    assert items[0]["risk"] == "high"


def test_org_isolation_upload_and_field(client, other_org):
    h = auth_headers(client)
    shipment = client.post("/api/shipments", json={}, headers=h).json()
    doc = _upload(client, h, shipment["id"], "invoice.pdf", _pdf_bytes("invoice.pdf")).json()
    fields = client.get(f"/api/shipments/{shipment['id']}/fields", headers=h).json()["items"]
    other = client.post("/api/auth/login",
                        json={"email": "owner2@test.cn", "password": "password123"})
    oh = {"Authorization": f"Bearer {other.json()['access_token']}"}
    assert client.get(f"/api/shipments/documents/{doc['id']}/file", headers=oh).status_code == 404
    r = client.patch(f"/api/shipments/fields/{fields[0]['id']}",
                     json={"value": "hack"}, headers=oh)
    assert r.status_code == 404


def test_rules_customer_level_config(client):
    h = auth_headers(client)
    c = client.post("/api/customers", json={"company_name": "规则客户"}, headers=h).json()
    r = client.put("/api/shipments/rules/amount_vs_lc",
                   json={"enabled": False, "customer_id": c["id"]}, headers=h)
    assert r.json()["enabled"] is False
    rules_for_customer = client.get("/api/shipments/rules",
                                    params={"customer_id": c["id"]}, headers=h).json()["items"]
    item = next(x for x in rules_for_customer if x["rule_code"] == "amount_vs_lc")
    assert item["has_override"] is True and item["enabled"] is False
    # other customers keep the global default (enabled)
    rules_global = client.get("/api/shipments/rules", headers=h).json()["items"]
    assert next(x for x in rules_global if x["rule_code"] == "amount_vs_lc")["enabled"] is True


def test_shipment_search_and_get_detail_flags(client, shipment):
    h = auth_headers(client)
    _upload(client, h, shipment["id"], "invoice-scan.pdf", _pdf_bytes("scan.pdf"))
    items = client.get("/api/shipments", params={"q": shipment["shipment_no"]},
                       headers=h).json()["items"]
    assert len(items) == 1 and items[0]["id"] == shipment["id"]
    detail = client.get(f"/api/shipments/{shipment['id']}", headers=h).json()
    scan = next(d for d in detail["documents"] if d["doc_type"] == "invoice")
    assert scan["status"] == "needs_manual" and scan["has_text_layer"] is False
    assert scan["extract_error"]


def test_chase_email_no_issues(client):
    h = auth_headers(client)
    # cutoff far in future, no docs required
    cutoff = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()
    s = client.post("/api/shipments", json={
        "cutoff_at": cutoff, "required_docs": []}, headers=h).json()
    r = client.post(f"/api/shipments/{s['id']}/chase-email", headers=h)
    assert r.status_code == 201
    assert "No open items" in r.json()["body_en"]


def test_invoice_port_and_incoterm_fields(client, shipment):
    h = auth_headers(client)
    _upload(client, h, shipment["id"], "invoice.pdf", _pdf_bytes("invoice.pdf"))
    fields = client.get(f"/api/shipments/{shipment['id']}/fields", headers=h).json()["items"]
    names = {f["field_name"] for f in fields}
    assert {"incoterm", "port_of_loading", "port_of_discharge", "unit_price"} <= names


def test_issue_action_unknown_and_bad_action(client, shipment):
    h = auth_headers(client)
    assert client.post("/api/shipments/issues/999999/action",
                       json={"action": "adopt"}, headers=h).status_code == 404
    detail = client.get(f"/api/shipments/{shipment['id']}", headers=h).json()
    issue = detail["issues"][0]
    r = client.post(f"/api/shipments/issues/{issue['id']}/action",
                    json={"action": "explode"}, headers=h)
    assert r.status_code == 422


def test_doc_type_sniffed_from_content(client, shipment):
    """文件名无类型线索时，按单证标题内容识别为 invoice（消除 other）。"""
    h = auth_headers(client)
    r = _upload(client, h, shipment["id"], "scan-2026-001.pdf", _pdf_bytes("invoice.pdf"))
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["doc_type"] == "invoice", body
    assert body["status"] == "extracted"


def test_sniffed_type_versions_increment_per_type(client, shipment):
    """无类型线索的文件名传两版不同发票：都识别为 invoice，版本按 invoice 递增且产生差异。"""
    h = auth_headers(client)
    v1 = _upload(client, h, shipment["id"], "upload_01.pdf", _pdf_bytes("invoice.pdf")).json()
    v2 = _upload(client, h, shipment["id"], "upload_02.pdf",
                 _pdf_bytes("invoice.pdf", invoice_no="TS-INV-9")).json()
    assert v1["doc_type"] == v2["doc_type"] == "invoice"
    assert v2["version"] == v1["version"] + 1
    changes = client.get(f"/api/shipments/{shipment['id']}/field-changes",
                         headers=h).json()["items"]
    assert any(c["field_name"] == "invoice_no" and c["old_value"] == "TS-INV-1"
               and c["new_value"] == "TS-INV-9" for c in changes)
