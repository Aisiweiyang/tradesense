"""RBAC matrix tests + dual-account approval flow (owner approves member)."""
from __future__ import annotations

import pytest

from app.rbac import MATRIX, ROLE_LEVELS
from tests.conftest import auth_headers


@pytest.fixture()
def member_headers(client):
    """Create a member user directly in org 1 (owner's org)."""
    from sqlalchemy import select

    from app.models import Organization, User
    from app.security import hash_password

    db = client.app.state.test_db
    org = db.scalar(select(Organization))
    user = User(org_id=org.id, email="member@test.cn", name="测试成员",
                password_hash=hash_password("password123"), role="member")
    db.add(user)
    db.commit()
    token = client.post("/api/auth/login", json={
        "email": "member@test.cn", "password": "password123"}).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.parametrize("capability,minimum", sorted(MATRIX.items()))
def test_matrix_is_wellformed(capability, minimum):
    assert minimum in ROLE_LEVELS
    assert capability in MATRIX


def test_member_cannot_approve_quote(client, member_headers):
    h = auth_headers(client)
    r = client.post("/api/products", json={
        "sku": "RBAC-1", "name_en": "Bottle", "moq": 500,
        "price_tiers": [{"min_qty": 500, "unit_price": 3.0}]}, headers=h)
    product = r.json()
    inq = client.post("/api/inquiries", json={
        "text": "Need 1,000 insulated bottles, FOB, to Hamburg"}, headers=h).json()
    quote = client.post("/api/quotes", json={
        "inquiry_id": inq["id"], "product_id": product["id"], "quantity": 1000,
        "incoterm": "FOB"}, headers=h).json()
    # member can create quotes (daily work)
    r = client.post("/api/quotes", json={
        "inquiry_id": inq["id"], "product_id": product["id"], "quantity": 500,
        "incoterm": "FOB"}, headers=member_headers)
    assert r.status_code == 201
    # member CANNOT approve (needs manager+)
    r = client.post(f"/api/quotes/{quote['id']}/approve", headers=member_headers)
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "forbidden"
    # member CANNOT set customer price
    r = client.post(f"/api/quotes/{quote['id']}/price",
                    json={"customer_price": 5.0}, headers=member_headers)
    assert r.status_code == 403


def test_owner_can_approve_member_created_quote(client, member_headers):
    h = auth_headers(client)
    product = client.post("/api/products", json={
        "sku": "RBAC-2", "name_en": "Bottle", "moq": 500,
        "price_tiers": [{"min_qty": 500, "unit_price": 3.0}]}, headers=h).json()
    inq = client.post("/api/inquiries", json={
        "text": "Need 1,000 insulated bottles, FOB, to Hamburg, LFGB"}, headers=h).json()
    quote = client.post("/api/quotes", json={
        "inquiry_id": inq["id"], "product_id": product["id"], "quantity": 1000,
        "incoterm": "FOB"}, headers=member_headers).json()
    r = client.post(f"/api/quotes/{quote['id']}/approve", headers=h)  # owner
    assert r.status_code == 200 and r.json()["is_formal"] is True


def test_member_cannot_manage_products(client, member_headers):
    r = client.post("/api/products", json={
        "sku": "RBAC-3", "name_en": "X"}, headers=member_headers)
    assert r.status_code == 403


def test_member_can_read_everything(client, member_headers):
    for path in ("/api/products", "/api/inquiries", "/api/customers", "/api/quotes"):
        assert client.get(path, headers=member_headers).status_code == 200


def test_bad_token_roles_have_no_access(client):
    r = client.get("/api/products", headers={"Authorization": "Bearer fake.token.here"})
    assert r.status_code == 401
