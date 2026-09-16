"""API-level tests: auth errors, org isolation, quote approval gate, imports."""
import json

from tests.conftest import auth_headers


def _mk_product(client, headers, sku, **kw):
    body = {"sku": sku, "name_en": kw.get("name_en", "Insulated Bottle"),
            "name_zh": "保温杯", "category": kw.get("category", "insulated_bottle"),
            "moq": 500, "price_tiers": [{"min_qty": 500, "unit_price": 3.0}],
            "lead_time_days": 25,
            "certifications": kw.get("certifications", ["FDA", "LFGB"]),
            "unit_weight_kg": 0.35}
    r = client.post("/api/products", json=body, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()


def _mk_inquiry(client, headers, text, **kw):
    r = client.post("/api/inquiries", json={"text": text, **kw}, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()


def test_auth_required(client):
    r = client.get("/api/products")
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "unauthorized"


def test_bad_login(client):
    r = client.post("/api/auth/login", json={"email": "owner@test.cn", "password": "wrong-password"})
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "bad_credentials"


def test_invalid_token(client):
    r = client.get("/api/products", headers={"Authorization": "Bearer garbage"})
    assert r.status_code == 401


def test_validation_error_envelope(client):
    headers = auth_headers(client)
    r = client.post("/api/products", json={"sku": ""}, headers=headers)
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "validation_error"


def test_pagination_and_sorting(client):
    headers = auth_headers(client)
    expected = sorted(f"SKU-{i}" for i in range(5))
    for i in range(5):
        _mk_product(client, headers, f"SKU-{i}")
    r = client.get("/api/products?page=1&page_size=2&sort=sku", headers=headers)
    data = r.json()
    assert data["total"] == 5 and len(data["items"]) == 2
    skus = [p["sku"] for p in data["items"]]
    assert skus == expected[:2]
    r = client.get("/api/products?page=2&page_size=2&sort=sku", headers=headers)
    assert [p["sku"] for p in r.json()["items"]] == expected[2:4]


def test_org_isolation(client, db, other_org):
    headers = auth_headers(client)
    product = _mk_product(client, headers, "ISO-1")
    # create user of other org by logging in directly
    r = client.post("/api/auth/login", json={"email": "owner2@test.cn", "password": "password123"})
    assert r.status_code == 200
    other_headers = {"Authorization": f"Bearer {r.json()['access_token']}"}
    # other org cannot see / modify the product
    r = client.get(f"/api/products/{product['id']}", headers=other_headers)
    assert r.status_code == 404
    r = client.patch(f"/api/products/{product['id']}", json={"moq": 1}, headers=other_headers)
    assert r.status_code == 404
    # other org product list is empty
    r = client.get("/api/products", headers=other_headers)
    assert r.json()["total"] == 0


def test_full_core_flow(client):
    """导入产品→询盘→多轮消息→需求→匹配→追问→报价→草稿→任务 (API e2e)."""
    headers = auth_headers(client)
    _mk_product(client, headers, "E2E-1", name_en="Vacuum Insulated Bottle 500ml")

    inq = _mk_inquiry(client, headers, "I need 500 blue stainless-steel bottles.")
    iid = inq["id"]
    assert inq["requirement"]["fields"]["color"]["value"] == "blue"

    # multi-round: correction
    r = client.post(f"/api/inquiries/{iid}/messages",
                    json={"text": "Actually, make them black, increase to 1,000, ship to Hamburg, FOB, LFGB needed."},
                    headers=headers)
    assert r.status_code == 201
    fields = r.json()["requirement"]["fields"]
    assert fields["color"]["value"] == "black"
    assert fields["quantity"]["value"] == "1,000 pcs"
    assert fields["incoterm"]["value"] == "FOB"

    # matching
    r = client.post(f"/api/inquiries/{iid}/match", headers=headers)
    assert r.status_code == 200
    assert len(r.json()["items"]) >= 1

    # clarification
    r = client.post(f"/api/inquiries/{iid}/clarification", headers=headers)
    primary = r.json()["primary"]
    assert primary is not None and primary["reason"]

    # quote + approval gate
    products = client.get("/api/products?q=E2E-1", headers=headers).json()["items"]
    r = client.post("/api/quotes", json={"inquiry_id": iid, "product_id": products[0]["id"],
                                         "quantity": 1000, "incoterm": "FOB",
                                         "margin_rate": 0.15, "printing": True}, headers=headers)
    quote = r.json()
    assert quote["unit_cost"] > 0 and quote["unit_price"] > quote["unit_cost"]
    r = client.post(f"/api/quotes/{quote['id']}/approve", headers=headers)
    assert r.status_code == 200 and r.json()["is_formal"] is True

    # reply draft
    r = client.post("/api/replies/generate", json={"kind": "quote_send", "tone": "formal",
                                                   "extra": {"inquiry_id": iid}}, headers=headers)
    draft = r.json()
    assert "Quotation" in draft["subject_en"]
    assert draft["body_zh"] and draft["needs_confirmation"]

    # follow-up task
    r = client.post("/api/followups", json={"title": "发送报价", "inquiry_id": iid,
                                            "task_type": "quote_send"}, headers=headers)
    assert r.status_code == 201
    task_id = r.json()["id"]
    r = client.post(f"/api/followups/{task_id}/status", json={"status": "done"}, headers=headers)
    assert r.json()["status"] == "done"

    # history has the full multi-round trail
    hist = client.get(f"/api/inquiries/{iid}/history", headers=headers).json()["items"]
    color_updates = [h for h in hist if h["field"] == "color" and h["change_type"] == "update"]
    assert color_updates and color_updates[0]["old_value"] == "blue"


def test_formal_quote_blocked_without_required_fields(client):
    headers = auth_headers(client)
    _mk_product(client, headers, "E2E-2")
    inq = _mk_inquiry(client, headers, "hello, we want some bottles")  # no qty/dest/incoterm
    products = client.get("/api/products?q=E2E-2", headers=headers).json()["items"]
    r = client.post("/api/quotes", json={"inquiry_id": inq["id"], "product_id": products[0]["id"],
                                         "quantity": 1000, "incoterm": "FOB"}, headers=headers)
    quote = r.json()
    detail = client.get(f"/api/quotes/{quote['id']}", headers=headers).json()
    assert detail["requirement_blockers"]  # warnings must be visible
    r = client.post(f"/api/quotes/{quote['id']}/approve", headers=headers)
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "blocked_by_requirements"


def test_product_import_flow(client):
    headers = auth_headers(client)
    csv_content = ("sku,中文名称,英文名称,类别,材质,起订量,阶梯价格,认证\n"
                   "IMP-1,保温杯,Vacuum Bottle 500ml,保温杯,304不锈钢,500,500:3.2;1000:3.0,\"FDA, LFGB\"\n"
                   "IMP-2,马克杯,Ceramic Mug 350ml,马克杯,陶瓷,1000,1000:1.1,FDA\n"
                   ",缺少SKU行,Nameless,Mug,ceramic,10,1.0,\n").encode("utf-8")
    r = client.post("/api/imports/preview?mapping=", files={"file": ("products.csv", csv_content, "text/csv")},
                    headers=headers)
    preview = r.json()
    assert preview["total"] == 3
    assert preview["valid"] == 2 and preview["errors"] == 1
    bad = [row for row in preview["rows"] if not row["valid"]]
    assert "SKU" in bad[0]["errors"][0]
    r = client.post(f"/api/imports/commit?token={preview['token']}", headers=headers)
    result = r.json()
    assert result["created"] == 2 and len(result["failed"]) == 1
    # re-import same file → duplicate warnings, updates on commit
    r = client.post("/api/imports/preview?mapping=", files={"file": ("products.csv", csv_content, "text/csv")},
                    headers=headers)
    preview2 = r.json()
    dupes = [row for row in preview2["rows"] if row["duplicate_of"]]
    assert len(dupes) == 2
    r = client.post(f"/api/imports/commit?token={preview2['token']}", headers=headers)
    assert r.json()["updated"] == 2


def test_import_commit_bad_token(client):
    headers = auth_headers(client)
    r = client.post("/api/imports/commit?token=nonexistent1234", headers=headers)
    assert r.status_code == 409


def test_below_cost_quote_requires_reapproval(client):
    headers = auth_headers(client)
    product = _mk_product(client, headers, "E2E-3")
    inq = _mk_inquiry(client, headers,
                      "Need 1,000 insulated bottles, FOB, to Hamburg, LFGB, target USD 10/pc")
    r = client.post("/api/quotes", json={"inquiry_id": inq["id"], "product_id": product["id"],
                                         "quantity": 1000, "incoterm": "FOB"}, headers=headers)
    quote = r.json()
    # set customer price below internal cost → auto pending_approval
    r = client.post(f"/api/quotes/{quote['id']}/price",
                    json={"customer_price": quote["unit_cost"] * 0.5}, headers=headers)
    assert r.json()["status"] == "pending_approval"
    r = client.post(f"/api/quotes/{quote['id']}/approve", headers=headers)
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "below_cost"


def test_inquiry_search_wildcards_literal(client):
    """搜索词里的 % / _ 按字面匹配（q=50% 只命中含 50% 的询盘）。"""
    headers = auth_headers(client)
    _mk_inquiry(client, headers, "Quote 500 mugs, we want 50 percent deposit")
    _mk_inquiry(client, headers, "Quote 500 mugs, T/T 50% deposit terms")

    r = client.get("/api/inquiries", params={"q": "50%"}, headers=headers)
    titles = [i["title"] for i in r.json()["items"]]
    assert len(titles) == 1
    assert "T/T 50% deposit" in titles[0]


def test_login_fail_rate_limited(client):
    """同邮箱 60 秒内错 5 次后锁 1 分钟：连正确密码也 429；错的是别的邮箱则不受影响。"""
    for _ in range(5):
        assert client.post("/api/auth/login", json={
            "email": "rl@test.cn", "password": "wrongpw"}).status_code == 401
    r = client.post("/api/auth/login", json={"email": "rl@test.cn", "password": "password123"})
    assert r.status_code == 429
    assert r.json()["error"]["code"] == "rate_limited"
    # 其他邮箱不受牵连
    assert client.post("/api/auth/login", json={
        "email": "owner@test.cn", "password": "password123"}).status_code == 200
