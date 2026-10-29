"""QuoteSheet tests: build, versions, approve gate, PDF invariants."""
from __future__ import annotations

import io
import json

import pdfplumber

import pytest

from tests.conftest import auth_headers


@pytest.fixture()
def inquiry_with_quotes(client):
    """One inquiry + two products with quotes; returns ids."""
    h = auth_headers(client)
    for sku in ("QS-P1", "QS-P2"):
        r = client.post("/api/products", json={
            "sku": sku, "name_en": f"Bottle {sku}", "category": "insulated_bottle",
            "moq": 500, "price_tiers": [{"min_qty": 500, "unit_price": 3.0}],
            "lead_time_days": 25, "unit_weight_kg": 0.35}, headers=h)
        assert r.status_code == 201
    products = client.get("/api/products?q=QS-P", headers=h).json()["items"]
    p1, p2 = products[0], products[1]
    inq = client.post("/api/inquiries", json={
        "text": "Need 1,000 insulated bottles, FOB, to Hamburg, LFGB, "
                "target price USD 6/pc"}, headers=h).json()
    q1 = client.post("/api/quotes", json={
        "inquiry_id": inq["id"], "product_id": p1["id"], "quantity": 500,
        "incoterm": "FOB"}, headers=h).json()
    q2 = client.post("/api/quotes", json={
        "inquiry_id": inq["id"], "product_id": p2["id"], "quantity": 500,
        "incoterm": "FOB"}, headers=h).json()
    return h, inq["id"], q1, q2


def _pdf_text(data: bytes) -> str:
    """Decompress content streams and assert Latin invariants (CJK is
    CID-encoded in the PDF and not human-readable in raw streams)."""
    import re
    import zlib

    text = data.decode("latin-1", errors="ignore")
    stream_re = re.compile(rb"stream\r?\n(.*?)endstream", re.S)
    for m in stream_re.finditer(data):
        try:
            text += "\n" + zlib.decompress(m.group(1)).decode("latin-1", errors="ignore")
        except Exception:
            continue
    return text


def test_build_sheet_and_version_supersede(client, inquiry_with_quotes):
    h, inq_id, q1, q2 = inquiry_with_quotes
    r = client.post("/api/quote-sheets", json={
        "inquiry_id": inq_id, "quote_ids": [q1["id"], q2["id"]]}, headers=h)
    assert r.status_code == 201, r.text
    sheet = r.json()
    assert sheet["sheet_no"].startswith("QS-")
    assert len(sheet["lines"]) == 2
    assert abs(sheet["subtotal"] - sum(l["subtotal"] for l in sheet["lines"])) < 0.01
    # target price present (6 USD set in the inquiry text)
    assert sheet["target"].get("target_unit") == 6.0
    # rebuild → new version, old superseded
    r2 = client.post("/api/quote-sheets", json={
        "inquiry_id": inq_id, "quote_ids": [q1["id"]]}, headers=h)
    assert r2.json()["version"] == sheet["version"] + 1
    sheets = client.get(f"/api/quote-sheets?inquiry_id={inq_id}", headers=h).json()["items"]
    statuses = {s["id"]: s["status"] for s in sheets}
    assert statuses[sheet["id"]] == "superseded"
    assert statuses[r2.json()["id"]] == "draft"


def test_build_sheet_requires_lines(client):
    h = auth_headers(client)
    inq = client.post("/api/inquiries", json={"text": "hello there, we need bottles"},
                      headers=h).json()
    r = client.post("/api/quote-sheets", json={"inquiry_id": inq["id"], "quote_ids": []},
                    headers=h)
    assert r.status_code == 422


@pytest.mark.parametrize("terminal", ["superseded", "rejected"])
def test_closed_sheet_loses_formal_status_and_cannot_be_reapproved(client, inquiry_with_quotes, terminal):
    h, iid, q1, _ = inquiry_with_quotes
    body = {"inquiry_id": iid, "quote_ids": [q1["id"]]}
    sheet = client.post("/api/quote-sheets", json=body, headers=h).json()
    url = f"/api/quote-sheets/{sheet['id']}"
    assert client.post(url + "/approve", headers=h).json()["is_formal"] is True
    if terminal == "superseded":
        client.post("/api/quote-sheets", json=body, headers=h)
    else:
        client.post(url + "/reject", headers=h)
    current = client.get(url, headers=h).json()
    assert current["status"] == terminal and current["is_formal"] is False
    from app.models import QuoteSheet
    row = client.app.state.test_db.get(QuoteSheet, sheet["id"])
    assert row.approved_at is None and row.approved_by_user_id is None
    r = client.post(url + "/approve", headers=h)
    assert r.status_code == 409 and r.json()["error"]["code"] == "quote_closed"


def test_unapproved_pdf_has_watermark_and_no_cost(client, inquiry_with_quotes):
    h, inq_id, q1, q2 = inquiry_with_quotes
    sheet = client.post("/api/quote-sheets", json={
        "inquiry_id": inq_id, "quote_ids": [q1["id"], q2["id"]]}, headers=h).json()
    r = client.get(f"/api/quote-sheets/{sheet['id']}/pdf", headers=h)
    assert r.status_code == 200
    assert r.content[:4] == b"%PDF"
    with pdfplumber.open(io.BytesIO(r.content)) as pdf:
        assert pdf.metadata.get("Subject") == "NOT FORMAL - unapproved draft"
        text = chr(10).join((pg.extract_text() or "") for pg in pdf.pages)
    # internal cost must NEVER appear
    assert "unit_cost" not in text.lower() and "Unit Cost" not in text and "内部成本" not in text
    # customer-facing prices DO appear
    assert "Total" in text and f"{sheet['subtotal']:,.2f}" in text


def test_approved_pdf_has_no_watermark(client, inquiry_with_quotes):
    h, inq_id, q1, q2 = inquiry_with_quotes
    sheet = client.post("/api/quote-sheets", json={
        "inquiry_id": inq_id, "quote_ids": [q1["id"]]}, headers=h).json()
    r = client.post(f"/api/quote-sheets/{sheet['id']}/approve", headers=h)
    assert r.json()["is_formal"] is True
    r = client.get(f"/api/quote-sheets/{sheet['id']}/pdf", headers=h)
    with pdfplumber.open(io.BytesIO(r.content)) as pdf:
        assert pdf.metadata.get("Subject") != "NOT FORMAL - unapproved draft"


def test_pdf_download_via_query_token(client, inquiry_with_quotes):
    """浏览器下载通道：JWT 放 ?access_token= 也能出 PDF；无任何令牌则 401。"""
    h, inq_id, q1, q2 = inquiry_with_quotes
    sheet = client.post("/api/quote-sheets", json={
        "inquiry_id": inq_id, "quote_ids": [q1["id"], q2["id"]]}, headers=h).json()
    token = h["Authorization"].removeprefix("Bearer ")
    r = client.get(f"/api/quote-sheets/{sheet['id']}/pdf?access_token={token}")
    assert r.status_code == 200
    assert r.content[:4] == b"%PDF"
    r = client.get(f"/api/quote-sheets/{sheet['id']}/pdf")
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "unauthorized"


def test_sheet_org_isolation(client, other_org, inquiry_with_quotes):
    h, inq_id, q1, q2 = inquiry_with_quotes
    sheet = client.post("/api/quote-sheets", json={
        "inquiry_id": inq_id, "quote_ids": [q1["id"]]}, headers=h).json()
    other = client.post("/api/auth/login",
                        json={"email": "owner2@test.cn", "password": "password123"})
    oh = {"Authorization": f"Bearer {other.json()['access_token']}"}
    assert client.get(f"/api/quote-sheets/{sheet['id']}", headers=oh).status_code == 404
    assert client.get(f"/api/quote-sheets/{sheet['id']}/pdf", headers=oh).status_code == 404
    assert client.post(f"/api/quote-sheets/{sheet['id']}/approve", headers=oh).status_code == 404


def test_sheet_lines_snapshot_prices_not_live(client, inquiry_with_quotes):
    """Sheet lines freeze the price at build time; later quote edits don't leak in."""
    h, inq_id, q1, q2 = inquiry_with_quotes
    sheet = client.post("/api/quote-sheets", json={
        "inquiry_id": inq_id, "quote_ids": [q1["id"]]}, headers=h).json()
    before = sheet["lines"][0]["unit_price"]
    client.post(f"/api/quotes/{q1['id']}/price",
                json={"customer_price": before * 2}, headers=h)
    detail = client.get(f"/api/quote-sheets/{sheet['id']}", headers=h).json()
    assert detail["lines"][0]["unit_price"] == before


def test_sheet_rejects_quotes_from_other_inquiry(client, inquiry_with_quotes):
    """跨询盘勾选合并：422 拒绝，防止把别家客户的报价混进同一份对客文件。"""
    h, inq_id, q1, q2 = inquiry_with_quotes
    other_inq = client.post("/api/inquiries", json={"text": "Need 500 mugs, FOB"},
                            headers=h).json()
    r = client.post("/api/quote-sheets", json={
        "inquiry_id": other_inq["id"], "quote_ids": [q1["id"]]}, headers=h)
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "quote_mismatch"


def test_sheet_rejects_cross_org_inquiry(client, other_org, inquiry_with_quotes):
    """他司询盘 id：404（与全局隔离口径一致），目标价不得外泄。"""
    from app.models import Product
    h, inq_id, q1, _ = inquiry_with_quotes
    other = auth_headers(client, "owner2@test.cn")
    # 他司自建询盘+产品报价，凑齐合法入参后仍应因询盘不属于他司而 404
    prod = client.post("/api/products", json={
        "sku": "QS-X-1", "name_en": "Mug", "name_zh": "杯", "category": "mug", "moq": 100,
        "price_tiers": [{"min_qty": 100, "unit_price": 1.0}], "lead_time_days": 10,
        "certifications": [], "unit_weight_kg": 0.3}, headers=other).json()
    foreign_inq = client.post("/api/inquiries", json={"text": "quote mugs"}, headers=other).json()
    q = client.post("/api/quotes", json={
        "inquiry_id": foreign_inq["id"], "product_id": prod["id"], "quantity": 100},
        headers=other).json()
    r = client.post("/api/quote-sheets", json={
        "inquiry_id": inq_id, "quote_ids": [q["id"]]}, headers=other)
    assert r.status_code == 404, r.text
