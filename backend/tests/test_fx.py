"""汇率配置：查表命中、反向对、回退+missing、同币种、归一化等价、报价集成、隔离。"""
import pytest

from tests.conftest import auth_headers

from app.models import ExchangeRate, Supplier
from app.services.fx import resolve


def _set_rate(db, org_id, base, quote, rate, by=None):
    db.add(ExchangeRate(org_id=org_id, base_currency=base, quote_currency=quote,
                        rate=rate, updated_by_user_id=by))
    db.commit()


def test_same_currency_is_one(db, org):
    rate, note = resolve(db, org.id, "USD", "USD")
    assert rate == 1.0 and note == ""
    rate, note = resolve(db, org.id, "usd", "USD")
    assert rate == 1.0 and note == ""


def test_hit_and_reverse(db, org):
    _set_rate(db, org.id, "CNY", "USD", 1 / 7.2)  # 规范化存储：等值 USD/CNY=7.2
    # CNY→USD 是存储正向
    rate, note = resolve(db, org.id, "CNY", "USD")
    assert rate == pytest.approx(1 / 7.2)
    assert "汇率表" in note
    # USD→CNY 是存储反向：读时取倒数
    rate, note = resolve(db, org.id, "USD", "CNY")
    assert rate == pytest.approx(7.2)
    assert "反向" in note


def test_missing_falls_back_with_note(db, org):
    rate, note = resolve(db, org.id, "EUR", "CNY")
    assert rate == 1.0
    assert note.startswith("missing:")


def test_set_api_normalizes_pair(client, org, db):
    # 录入方向 USD→CNY=7.2，存储规范化为 CNY/USD=1/7.2；两个方向读都对
    owner = auth_headers(client)
    r = client.put("/api/fx", json={"base_currency": "USD", "quote_currency": "CNY", "rate": 7.2},
                   headers=owner)
    assert r.status_code == 200, r.text
    row = db.query(ExchangeRate).filter_by(org_id=org.id).one()
    assert (row.base_currency, row.quote_currency) == ("CNY", "USD")
    assert row.rate == pytest.approx(1 / 7.2)
    assert resolve(db, org.id, "USD", "CNY")[0] == pytest.approx(7.2)
    assert resolve(db, org.id, "CNY", "USD")[0] == pytest.approx(1 / 7.2)

    # 反方向再录入同一路径是更新而不是新增
    client.put("/api/fx", json={"base_currency": "CNY", "quote_currency": "USD", "rate": 1 / 7.4},
               headers=owner)
    assert db.query(ExchangeRate).filter_by(org_id=org.id).count() == 1
    assert resolve(db, org.id, "USD", "CNY")[0] == pytest.approx(7.4)


def test_org_isolation(db, org, other_org):
    _set_rate(db, org.id, "CNY", "USD", 1 / 7.2)
    rate, note = resolve(db, other_org.id, "USD", "CNY")
    assert rate == 1.0 and note.startswith("missing:")


def _mk_product(client, headers, sku):
    r = client.post("/api/products", json={
        "sku": sku, "name_en": "Mug", "name_zh": "马克杯", "category": "mug", "moq": 500,
        "price_tiers": [{"min_qty": 500, "unit_price": 1.0}], "lead_time_days": 20,
        "certifications": [], "unit_weight_kg": 0.4}, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()


def _mk_supplier_quote(db, org, product_id, cost, currency="CNY"):
    sup = Supplier(org_id=org.id, name="汇率测试供应商", reliability_score=0.8)
    db.add(sup)
    db.flush()
    return {"supplier_id": sup.id, "cost_price": cost, "currency": currency,
            "moq": 500, "lead_time_days": 20}


def test_quote_integration_fx_table_and_explicit_override(client, org, other_org, db):
    headers = auth_headers(client)
    prod = _mk_product(client, headers, "FX-MUG-1")
    sup = Supplier(org_id=org.id, name="汇率测试供应商", reliability_score=0.8)
    db.add(sup)
    db.commit()
    sq = client.post(f"/api/products/{prod['id']}/supplier-quotes",
                     json={"supplier_id": sup.id, "cost_price": 7.2, "currency": "CNY",
                           "moq": 500, "lead_time_days": 20}, headers=headers).json()
    inq = client.post("/api/inquiries", json={"text": "Please quote 1000 mugs, FOB"},
                      headers=headers).json()

    _set_rate(db, org.id, "CNY", "USD", 0.14)

    # 未显式给汇率：按表 0.14 折算并叠加缓冲；显式 1.0：不换算、无缓冲、无记录
    common = {"inquiry_id": inq["id"], "product_id": prod["id"], "quantity": 1000,
              "incoterm": "FOB", "supplier_product_id": sq["id"]}
    q_table = client.post("/api/quotes", headers=headers, json=dict(common)).json()
    q_explicit = client.post("/api/quotes", headers=headers,
                             json={**common, "exchange_rate": 1.0}).json()
    t = client.get(f"/api/quotes/{q_table['id']}", headers=headers).json()
    e = client.get(f"/api/quotes/{q_explicit['id']}", headers=headers).json()
    # compute_quote 的 unit_cost 保留 4 位小数，用 1e-4 相对容差
    assert t["unit_cost"] == pytest.approx(e["unit_cost"] * 0.14 * 1.02, rel=1e-4)
    assert t["exchange"]["applied"] == pytest.approx(0.14 * 1.02, abs=1e-6)
    assert e["exchange"] == {}
    assert any("汇率表" in a for a in t["assumptions"])

    # 表中无配置的组织：回退 1:1 且 missing 提示（不阻塞报价）
    other = auth_headers(client, "owner2@test.cn")  # other_org 夹具账号
    prod2 = _mk_product(client, other, "FX-MUG-2")
    sup2 = Supplier(org_id=other_org.id, name="无配置组织供应商", reliability_score=0.8)
    db.add(sup2)
    db.commit()
    sq2 = client.post(f"/api/products/{prod2['id']}/supplier-quotes",
                      json={"supplier_id": sup2.id, "cost_price": 7.2, "currency": "CNY",
                            "moq": 500, "lead_time_days": 20}, headers=other).json()
    inq2 = client.post("/api/inquiries", json={"text": "quote mugs"}, headers=other).json()
    q3 = client.post("/api/quotes", headers=other, json={
        "inquiry_id": inq2["id"], "product_id": prod2["id"], "quantity": 1000,
        "incoterm": "FOB", "supplier_product_id": sq2["id"]}).json()
    d3 = client.get(f"/api/quotes/{q3['id']}", headers=other).json()
    assert d3["exchange"] == {}
    assert any("汇率" in m for m in d3["missing"])


def test_resolve_endpoint_visible_to_all_logged_in(client, db):
    """报价面板的汇率预览：member 可读，未配置时 configured=false 且回退 1.0。"""
    from app.models import User
    from app.security import hash_password
    db.add(User(org_id=1, email="fxmember2@test.cn", name="m2",
                password_hash=hash_password("password123"), role="member"))
    db.commit()
    member = auth_headers(client, "fxmember2@test.cn")

    r = client.get("/api/fx/resolve", params={"from_ccy": "USD", "to_ccy": "CNY"}, headers=member)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["configured"] is False and body["rate"] == 1.0

    _set_rate(db, 1, "CNY", "USD", 1 / 7.2)
    body = client.get("/api/fx/resolve", params={"from_ccy": "USD", "to_ccy": "cny"},
                      headers=member).json()
    assert body["configured"] is True
    assert body["rate"] == pytest.approx(7.2)


def test_fx_api_permission(client, db):
    from app.models import User
    from app.security import hash_password
    db.add(User(org_id=1, email="fxmember@test.cn", name="m",
                password_hash=hash_password("password123"), role="member"))
    db.commit()
    member = auth_headers(client, "fxmember@test.cn")
    assert client.get("/api/fx", headers=member).status_code == 403
    assert client.put("/api/fx", json={"base_currency": "USD", "quote_currency": "CNY",
                                       "rate": 7.2}, headers=member).status_code == 403

    owner = auth_headers(client)
    # 同币种拒绝
    assert client.put("/api/fx", json={"base_currency": "USD", "quote_currency": "usd",
                                       "rate": 1.0}, headers=owner).status_code == 422

    # 删除
    r = client.put("/api/fx", json={"base_currency": "EUR", "quote_currency": "USD", "rate": 1.08},
                   headers=owner)
    rid = r.json()["id"]
    assert client.delete(f"/api/fx/{rid}", headers=owner).status_code == 204
    assert client.get("/api/fx", headers=owner).json()["items"] == []
