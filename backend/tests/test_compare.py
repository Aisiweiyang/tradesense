"""Multi-supplier comparison tests: scoring, stability, isolation, API."""
from __future__ import annotations

import json

import pytest

from app.models import Product, Supplier, SupplierProduct
from app.services.compare import compare_suppliers, recommend_reason
from tests.conftest import auth_headers


def _mk(db, org, sku="CMP-1", suppliers: list[tuple] = (), product_kwargs=None):
    p = Product(org_id=org.id, sku=sku, name_en="Vacuum Bottle", name_zh="保温杯",
                category="insulated_bottle", moq=500,
                price_tiers_json='[{"min_qty": 500, "unit_price": 3.0}]', is_active=True)
    db.add(p)
    db.flush()
    for i, (cost, lead, rel) in enumerate(suppliers):
        s = Supplier(org_id=org.id, name=f"供应商{chr(65 + i)}", reliability_score=rel)
        db.add(s)
        db.flush()
        db.add(SupplierProduct(org_id=org.id, product_id=p.id, supplier_id=s.id,
                               cost_price=cost, currency="CNY", moq=500,
                               lead_time_days=lead))
    db.commit()
    return p


def _names(rows):
    return [q.supplier.name for q in rows]


def test_cheapest_wins_with_explanations(db, org):
    p = _mk(db, org, suppliers=[(28.0, 30, 0.8), (25.0, 35, 0.75)])
    rows = compare_suppliers(db, org.id, p)
    assert _names(rows)[0] == "供应商B"  # cheaper → top
    cost = rows[0].scores["cost"]
    assert cost["score"] == 100.0
    assert "最低" in cost["detail"]
    assert rows[0].total > rows[1].total


def test_lead_time_and_reliability_can_flip_rank(db, org):
    # A is cheapest but slow & unreliable; B is pricier, fast, reliable
    p = _mk(db, org, sku="CMP-2", suppliers=[(25.0, 40, 0.5), (26.5, 20, 0.95)])
    rows = compare_suppliers(db, org.id, p)
    assert _names(rows)[0] == "供应商B"
    reason = recommend_reason(rows)
    assert "供应商B" in reason and ("交期最快" in reason or "最可靠" in reason)


def test_equal_offers_stable_order(db, org):
    p = _mk(db, org, sku="CMP-3", suppliers=[(25.0, 30, 0.8), (25.0, 30, 0.8)])
    rows = compare_suppliers(db, org.id, p)
    assert _names(rows) == ["供应商A", "供应商B"]  # id tie-break, deterministic


def test_single_supplier_returns_one_row(db, org):
    p = _mk(db, org, sku="CMP-4", suppliers=[(25.0, 30, 0.8)])
    rows = compare_suppliers(db, org.id, p)
    assert len(rows) == 1
    # cost & lead are trivially best (only offer), reliability stays absolute
    assert rows[0].scores["cost"]["score"] == 100.0
    assert rows[0].scores["reliability"]["score"] == 80.0
    assert rows[0].total == 96.0


def test_recommend_reason_empty(db, org):
    p = _mk(db, org, sku="CMP-5", suppliers=[])
    assert compare_suppliers(db, org.id, p) == []
    assert recommend_reason([]) == ""


# ---------------------------------------------------------------- API
def test_supplier_quotes_api_and_isolation(client, org, db, other_org):
    h = auth_headers(client)
    p = _mk(db, org, sku="CMP-API", suppliers=[(28.0, 30, 0.8), (25.0, 35, 0.75)])
    r = client.get(f"/api/products/{p.id}/supplier-quotes", headers=h)
    items = r.json()["items"]
    assert len(items) == 2
    assert items[0]["total"] >= items[1]["total"]
    assert "recommend_reason" in r.json()

    other = client.post("/api/auth/login",
                        json={"email": "owner2@test.cn", "password": "password123"})
    oh = {"Authorization": f"Bearer {other.json()['access_token']}"}
    assert client.get(f"/api/products/{p.id}/supplier-quotes", headers=oh).status_code == 404


def test_add_and_delete_supplier_quote_api(client, org, db):
    h = auth_headers(client)
    p = _mk(db, org, sku="CMP-API2", suppliers=[])
    sup = Supplier(org_id=org.id, name="供应商Z", reliability_score=0.8)
    db.add(sup)
    db.commit()
    r = client.post(f"/api/products/{p.id}/supplier-quotes",
                    json={"supplier_id": sup.id, "cost_price": 26.0,
                          "currency": "CNY", "moq": 500, "lead_time_days": 25},
                    headers=h)
    assert r.status_code == 201
    row_id = r.json()["id"]
    items = client.get(f"/api/products/{p.id}/supplier-quotes", headers=h).json()["items"]
    assert len(items) == 1 and items[0]["supplier_name"] == "供应商Z"
    r = client.delete(f"/api/products/{p.id}/supplier-quotes/{row_id}", headers=h)
    assert r.status_code == 200
    assert client.get(f"/api/products/{p.id}/supplier-quotes", headers=h).json()["items"] == []


def test_quote_with_supplier_cost_source(client, org, db):
    h = auth_headers(client)
    p = _mk(db, org, sku="CMP-API3", suppliers=[])
    sup = Supplier(org_id=org.id, name="供应商Y", reliability_score=0.9)
    db.add(sup)
    db.flush()
    sp = SupplierProduct(org_id=org.id, product_id=p.id, supplier_id=sup.id,
                         cost_price=2.6, currency="CNY", moq=500, lead_time_days=22)
    db.add(sp)
    db.commit()
    inq = client.post("/api/inquiries", json={
        "text": "Need 1,000 insulated bottles, FOB, to Hamburg, LFGB"}, headers=h).json()
    r = client.post("/api/quotes", json={
        "inquiry_id": inq["id"], "product_id": p.id, "quantity": 1000,
        "incoterm": "FOB", "supplier_product_id": sp.id}, headers=h)
    quote = r.json()
    assert quote["unit_cost"] > 0
    breakdown = json.loads(quote["breakdown_json"])
    cost_line = next(b for b in breakdown if "供应商报价" in b["item"])
    assert "供应商Y" in cost_line["source"]
