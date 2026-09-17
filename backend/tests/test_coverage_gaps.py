"""针对覆盖率短板的补测：跟进任务 API、回复草稿全场景、需求服务人工路径、
AI 降级、术语表、公开 webform。全部是行为断言，不为凑数。"""
import json

import pytest

from app.services.ai import ai_polish_reply
from app.services.reply_drafts import TEMPLATES, build_variables, generate_draft
from tests.conftest import auth_headers


# ---------------------------------------------------------------- 跟进任务 API
def test_followup_api_workflow(client):
    h = auth_headers(client)
    w = client.get("/api/followups/workload", headers=h)
    assert w.status_code == 200
    assert {"today_due", "overdue", "quoted_no_reply"} <= set(w.json())

    r = client.post("/api/followups", headers=h, json={
        "title": "回访 Oliver", "task_type": "follow_up", "priority": "normal",
        "reason": {"reason": "测试"}})
    assert r.status_code == 201, r.text
    tid = r.json()["id"]

    r = client.get("/api/followups", headers=h, params={"status": "pending"})
    assert any(x["id"] == tid for x in r.json()["items"])
    r = client.get("/api/followups", headers=h, params={"scope": "due"})
    assert r.status_code == 200

    r = client.post(f"/api/followups/{tid}/status", headers=h, json={"status": "snoozed"})
    assert r.json()["status"] == "snoozed"
    r = client.post(f"/api/followups/{tid}/status", headers=h,
                    json={"status": "done", "due_at": "2026-10-01T00:00:00Z"})
    assert r.json()["status"] == "done"
    r = client.post(f"/api/followups/{tid}/status", headers=h, json={"status": "bogus"})
    assert r.status_code == 422 and r.json()["error"]["code"] == "bad_status"
    assert client.post(f"/api/followups/999999/status", headers=h,
                       json={"status": "done"}).status_code == 404


def test_supplier_api_crud_and_search(client):
    h = auth_headers(client)
    r = client.post("/api/suppliers", headers=h,
                    json={"name": "宏达杯业", "region": "浙江", "reliability_score": 0.9})
    assert r.status_code == 201, r.text
    sid = r.json()["id"]
    r = client.patch(f"/api/suppliers/{sid}", headers=h,
                     json={"name": "宏达杯业二厂", "reliability_score": 0.95})
    assert r.json()["name"] == "宏达杯业二厂"
    r = client.get("/api/suppliers", headers=h, params={"q": "宏达"})
    assert any(x["id"] == sid for x in r.json()["items"])


# ---------------------------------------------------------------- 回复草稿全场景
@pytest.mark.parametrize("kind", sorted(TEMPLATES))
def test_generate_draft_all_kinds(kind):
    values = {f: {"value": "500", "normalized": "500", "source_message_id": 1}
              for f in ("product", "quantity", "spec", "material", "incoterm", "lead_time",
                        "destination_port", "destination_country")}
    variables = build_variables(None, values, {"customer_name": "Anna"})
    out = generate_draft(kind, "formal", variables, values)
    assert out["subject_en"] and out["body_en"] and out["body_zh"]
    assert out["needs_confirmation"], "每个模板都必须有人工确认项"


def test_generate_draft_unknown_kind():
    with pytest.raises(ValueError):
        generate_draft("no_such_kind", "formal", {}, {})


# ---------------------------------------------------------------- AI 降级
def test_ai_polish_disabled_returns_none():
    """无 AI provider：润色返回 None，模板正文原样使用（确定性降级）。"""
    assert ai_polish_reply("first_reply", "some body") is None


# ---------------------------------------------------------------- 术语表
def test_glossary_api(client):
    r = client.get("/api/glossary", params={"q": "FOB"},
                   headers=auth_headers(client))
    assert r.status_code == 200
    body = r.json()
    assert any(t["term"].upper() == "FOB" for t in body["items"])
    assert body["disclaimer"]


# ---------------------------------------------------------------- 需求服务人工路径
def test_requirement_manual_set_lock_unlock_history(db, org):
    from app.models import ConversationThread, Inquiry
    from app.services.requirement_service import RequirementService

    inq = Inquiry(org_id=org.id, title="manual test", status="clarifying", stage="clarifying")
    db.add(inq)
    db.flush()
    svc = RequirementService(db, org.id)
    svc.ensure_state(inq.id)

    ch = svc.manual_set(inq, "color", "black", lock=True)
    assert ch.field == "color"
    vals = svc.active_values(inq.id)
    assert vals["color"]["normalized"] == "black"
    assert vals["color"]["locked"] is True

    db.flush()  # 会话 autoflush=False，查历史前先落
    hist = svc.history(inq.id)
    assert hist, "人工修改必须留痕"
    assert any(h.field == "color" and h.actor == "human" for h in hist)

    svc.manual_unlock(inq, "color")
    db.flush()
    assert svc.active_values(inq.id)["color"]["locked"] is False


# ---------------------------------------------------------------- 公开 webform
def test_webform_public_flow(client, db):
    h = auth_headers(client)
    acct = client.post("/api/connectors", headers=h, json={
        "connector_type": "webform", "name": "官网表单",
        "config": {"site_name": "demo"}})
    assert acct.status_code in (200, 201), acct.text
    account_id = acct.json()["id"]

    # 蜜罐命中：直接忽略
    r = client.post(f"/api/public/webform/{account_id}",
                    json={"name": "bot", "text": "buy mugs", "website_url": "http://spam"})
    assert r.status_code == 200 and r.json().get("ignored") == "honeypot"

    # 空内容 422
    r = client.post(f"/api/public/webform/{account_id}", json={"name": "x", "text": "hi"})
    assert r.status_code == 422

    # 正常提交：无需登录即建询盘
    r = client.post(f"/api/public/webform/{account_id}",
                    json={"name": "Anna", "email": "anna@x.de", "text": "We need 500 mugs FOB Hamburg"})
    assert r.status_code == 200 and r.json()["ok"] is True and r.json()["duplicate"] is False
