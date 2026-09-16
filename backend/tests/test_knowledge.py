"""知识库：CRUD、搜索、组织隔离、草稿引用标注；未指定条目时草稿行为不变。"""
from tests.conftest import auth_headers


def _mk_kb(client, headers, title, content="LFGB test report required.", tags="认证,LFGB"):
    r = client.post("/api/knowledge", json={"title": title, "content": content, "tags": tags},
                    headers=headers)
    assert r.status_code == 201, r.text
    return r.json()


def test_crud_and_member_permission(client):
    owner = auth_headers(client)
    k = _mk_kb(client, owner, "LFGB basics")

    r = client.get("/api/knowledge", headers=owner)
    assert r.status_code == 200
    assert [x["id"] for x in r.json()["items"]] == [k["id"]]

    r = client.patch(f"/api/knowledge/{k['id']}",
                     json={"title": "LFGB basics v2", "content": "updated", "tags": "认证"},
                     headers=owner)
    assert r.status_code == 200 and r.json()["title"] == "LFGB basics v2"

    r = client.delete(f"/api/knowledge/{k['id']}", headers=owner)
    assert r.status_code == 204
    r = client.get(f"/api/knowledge/{k['id']}", headers=owner)
    assert r.status_code == 404


def test_search_matches_title_content_tags(client):
    headers = auth_headers(client)
    _mk_kb(client, headers, "LFGB for German buyers", content="food-contact rule", tags="欧盟")
    _mk_kb(client, headers, "IPPC stamp", content="solid wood packaging needs fumigation", tags="包装,木箱")
    _mk_kb(client, headers, "Payment terms", content="T/T 30/70 default", tags="付款,TT")

    assert len(client.get("/api/knowledge?q=LFGB", headers=headers).json()["items"]) == 1
    # 内容命中
    assert len(client.get("/api/knowledge?q=fumigation", headers=headers).json()["items"]) == 1
    # 标签命中
    assert len(client.get("/api/knowledge?q=付款", headers=headers).json()["items"]) == 1
    # 无命中
    assert client.get("/api/knowledge?q=不存在", headers=headers).json()["items"] == []


def test_org_isolation(client, other_org):
    headers = auth_headers(client)
    k = _mk_kb(client, headers, "internal only")
    other = auth_headers(client, "owner2@test.cn")  # other_org 夹具已建好的账号

    assert client.get(f"/api/knowledge/{k['id']}", headers=other).status_code == 404
    r = client.get("/api/knowledge", headers=other)
    assert all(x["id"] != k["id"] for x in r.json()["items"])
    assert client.patch(f"/api/knowledge/{k['id']}",
                        json={"title": "hijack", "content": "", "tags": ""},
                        headers=other).status_code == 404
    assert client.delete(f"/api/knowledge/{k['id']}", headers=other).status_code == 404


def test_generate_with_knowledge_citation(client):
    headers = auth_headers(client)
    inq = client.post("/api/inquiries",
                      json={"text": "We need 500 stainless steel bottles for German market, food contact."},
                      headers=headers).json()
    k = _mk_kb(client, headers, "LFGB requirement",
               content="German buyers require LFGB test reports for food-contact bottles.")

    r = client.post("/api/replies/generate", headers=headers, json={
        "kind": "first_reply", "tone": "formal",
        "extra": {"inquiry_id": inq["id"], "knowledge_ids": [k["id"]]}})
    assert r.status_code == 201, r.text
    data = r.json()
    assert "Useful notes from our team knowledge base" in data["body_en"]
    assert "> LFGB requirement:" in data["body_en"]
    assert any(f["field"] == f"知识库#{k['id']}" for f in data["facts_used"])
    assert "知识库内容已引用，请人工核对" in data["needs_confirmation"]


def test_generate_without_knowledge_unchanged(client):
    headers = auth_headers(client)
    inq = client.post("/api/inquiries",
                      json={"text": "Please quote 1,000 travel mugs 450ml, FOB Felixstowe."},
                      headers=headers).json()
    _mk_kb(client, headers, "unreferenced entry", content="not cited")

    r = client.post("/api/replies/generate", headers=headers, json={
        "kind": "first_reply", "tone": "formal", "extra": {"inquiry_id": inq["id"]}})
    data = r.json()
    assert "team knowledge base" not in data["body_en"]
    assert all(not f["field"].startswith("知识库#") for f in data["facts_used"])
    assert "知识库内容已引用，请人工核对" not in data["needs_confirmation"]


def test_generate_skips_foreign_and_missing_ids(client, other_org, db):
    headers = auth_headers(client)
    inq = client.post("/api/inquiries", json={"text": "Quote 300 ceramic mugs with logo DDP"},
                      headers=headers).json()
    k = _mk_kb(client, headers, "own entry", content="mine")

    from app.models import KnowledgeDocument
    db.add(KnowledgeDocument(org_id=other_org.id, title="foreign", content="other org", tags=""))
    db.commit()
    foreign_id = db.query(KnowledgeDocument).filter_by(title="foreign").one().id

    # 跨组织 id 与不存在的 id 都被忽略，自己的条目正常引用
    r = client.post("/api/replies/generate", headers=headers, json={
        "kind": "first_reply", "tone": "formal",
        "extra": {"inquiry_id": inq["id"], "knowledge_ids": [k["id"], foreign_id, 99999]}})
    data = r.json()
    assert data["body_en"].count("> ") == 1
    assert "> own entry:" in data["body_en"]


def test_search_wildcards_are_literal(client):
    """% 和 _ 按字面匹配（SQLite 需要显式 ESCAPE 子句，否则通配符转义不生效）。"""
    headers = auth_headers(client)
    _mk_kb(client, headers, "discount rule", content="Save 50 percent on bulk", tags="价")
    _mk_kb(client, headers, "percent literal", content="discount 50% today only", tags="价")

    hits = client.get("/api/knowledge", params={"q": "50%"}, headers=headers).json()["items"]
    assert [x["title"] for x in hits] == ["percent literal"]
    hits = client.get("/api/knowledge", params={"q": "50 percent"}, headers=headers).json()["items"]
    assert [x["title"] for x in hits] == ["discount rule"]
    _mk_kb(client, headers, "snake_case note", content="field order_no", tags="")
    hits = client.get("/api/knowledge", params={"q": "order_no"}, headers=headers).json()["items"]
    assert [x["title"] for x in hits] == ["snake_case note"]
