"""单证版本差异：同 doc_type 重复上传生成字段差异；无差异为空；版本链；组织隔离。"""
from __future__ import annotations

import uuid
from pathlib import Path

from app.seed import docgen
from tests.conftest import auth_headers
from tests.test_shipments_api import shipment as shipment_fixture  # noqa: F401 (pytest fixture)


def _mk_invoice(name: str, total: str, inv_no: str = "TS-INV-1") -> bytes:
    """Build a real invoice PDF with the given total so extraction differs."""
    p = Path("data") / "test_docs" / f"{uuid.uuid4().hex[:8]}-{name}"
    p.parent.mkdir(parents=True, exist_ok=True)
    docgen.make_invoice(p, invoice_no=inv_no, total_amount=total,
                        hs_code="8467.29", description="Cordless Drill Set",
                        consignee="HausKonzept GmbH")
    return p.read_bytes()


def _upload(client, headers, shipment_id, filename, content):
    return client.post(f"/api/shipments/{shipment_id}/documents",
                       files={"file": (filename, content, "application/pdf")},
                       headers=headers)


def test_first_upload_has_no_diff(client, shipment_fixture):
    h = auth_headers(client)
    r = _upload(client, h, shipment_fixture["id"], "invoice.pdf", _mk_invoice("a.pdf", "48,620.00"))
    assert r.status_code == 201, r.text
    doc_id = r.json()["id"]
    d = client.get(f"/api/shipments/documents/{doc_id}/diff", headers=h).json()
    assert d["version"] == 1 and d["prev_version"] is None and d["items"] == []


def test_reupload_generates_changed_diff(client, shipment_fixture):
    h = auth_headers(client)
    v1 = _upload(client, h, shipment_fixture["id"], "invoice.pdf", _mk_invoice("a.pdf", "48,620.00")).json()
    v2 = _upload(client, h, shipment_fixture["id"], "invoice-2.pdf", _mk_invoice("b.pdf", "49,990.00")).json()
    assert (v1["version"], v2["version"]) == (1, 2)

    d = client.get(f"/api/shipments/documents/{v2['id']}/diff", headers=h).json()
    assert d["prev_version"] == 1
    by_field = {i["field_name"]: i for i in d["items"]}
    changed = {k: v for k, v in by_field.items() if v["change_type"] == "changed"}
    assert changed, "总价变化必须生成差异记录"
    total = by_field.get("total_amount")
    assert total and total["old_value"] == "48,620.00" and total["new_value"] == "49,990.00"
    assert total["changed_at"]


def test_no_difference_yields_empty_diff(client, shipment_fixture):
    h = auth_headers(client)
    _upload(client, h, shipment_fixture["id"], "invoice.pdf", _mk_invoice("a.pdf", "48,620.00"))
    v2 = _upload(client, h, shipment_fixture["id"], "invoice-2.pdf", _mk_invoice("b.pdf", "48,620.00")).json()
    d = client.get(f"/api/shipments/documents/{v2['id']}/diff", headers=h).json()
    assert d["items"] == [] and d["prev_version"] == 1


def test_added_and_removed_fields_recorded(client, shipment_fixture):
    h = auth_headers(client)
    _upload(client, h, shipment_fixture["id"], "invoice.pdf",
            _mk_invoice("a.pdf", "48,620.00", inv_no="TS-INV-1"))
    v2 = _upload(client, h, shipment_fixture["id"], "invoice-2.pdf",
                 _mk_invoice("b.pdf", "48,620.00", inv_no="TS-INV-77")).json()
    d = client.get(f"/api/shipments/documents/{v2['id']}/diff", headers=h).json()
    types = {(i["field_name"], i["change_type"]) for i in d["items"]}
    assert ("invoice_no", "changed") in types
    # invoice_no 从 TS-INV-1 → TS-INV-77 记录新旧值
    row = next(i for i in d["items"] if i["field_name"] == "invoice_no")
    assert (row["old_value"], row["new_value"]) == ("TS-INV-1", "TS-INV-77")


def test_version_chain_via_field_changes(client, shipment_fixture):
    h = auth_headers(client)
    _upload(client, h, shipment_fixture["id"], "invoice.pdf", _mk_invoice("a.pdf", "48,620.00"))
    v2 = _upload(client, h, shipment_fixture["id"], "invoice-2.pdf", _mk_invoice("b.pdf", "49,990.00")).json()
    v3 = _upload(client, h, shipment_fixture["id"], "invoice-3.pdf", _mk_invoice("c.pdf", "51,000.00")).json()
    rows = client.get(f"/api/shipments/{shipment_fixture['id']}/field-changes", headers=h).json()["items"]
    assert {r["prev_version"] for r in rows} == {1, 2}
    assert all(r["document_id"] in (v2["id"], v3["id"]) for r in rows)
    v3_total = [r for r in rows if r["document_id"] == v3["id"]
                and r["field_name"] == "total_amount"]
    assert v3_total and v3_total[0]["old_value"] == "49,990.00"


def test_diff_org_isolation(client, shipment_fixture, other_org, db):
    from app.models import Organization, User
    from app.security import hash_password
    h = auth_headers(client)
    doc = _upload(client, h, shipment_fixture["id"], "invoice.pdf", _mk_invoice("a.pdf", "48,620.00")).json()

    # 另一组织用户登录
    u2 = User(org_id=other_org.id, email="owner2b@test.cn", name="他司",
              password_hash=hash_password("password123"))
    db.add(u2)
    db.commit()
    h2 = auth_headers(client, email="owner2b@test.cn")
    r = client.get(f"/api/shipments/documents/{doc['id']}/diff", headers=h2)
    assert r.status_code == 404
    r2 = client.get(f"/api/shipments/{shipment_fixture['id']}/field-changes", headers=h2)
    assert r2.status_code == 404


def test_diff_missing_document_404(client):
    r = client.get("/api/shipments/documents/99999/diff", headers=auth_headers(client))
    assert r.status_code == 404
