"""看板洞察：渠道转化、首响时长（右删失口径）、目标达成率、隔离与边界。"""
import json
from datetime import timedelta

from app.models import ConversationMessage, ConversationThread, Inquiry, Quote
from app.services.insights import build_insights
from tests.conftest import auth_headers


def _ago(hours: float):
    from datetime import datetime, timezone
    return datetime.now(timezone.utc) - timedelta(hours=hours)


def _inq(db, org_id, channel="email", stage="new", created_h=100, summary=None):
    inq = Inquiry(org_id=org_id, title="ins", status="open", stage=stage,
                  source_channel=channel, summary_json=json.dumps(summary or {}))
    inq.created_at = _ago(created_h)
    db.add(inq)
    db.flush()
    return inq


def _msg(db, org_id, inq, direction, hours_ago):
    t = db.query(ConversationThread).filter_by(inquiry_id=inq.id).first()
    if t is None:
        t = ConversationThread(org_id=org_id, inquiry_id=inq.id, channel="manual")
        db.add(t)
        db.flush()
    db.add(ConversationMessage(org_id=org_id, inquiry_id=inq.id, thread_id=t.id,
                               direction=direction, sender="x" if direction == "out" else "customer",
                               raw_content="...", normalized_content="...",
                               sent_at=_ago(hours_ago)))
    db.flush()


def test_channel_conversion_and_isolation(db, org, other_org):
    _inq(db, org.id, channel="email", stage="quoted", created_h=90)
    _inq(db, org.id, channel="email", stage="new", created_h=90)
    _inq(db, org.id, channel="webform", stage="new", created_h=90)
    out = build_insights(db, org.id)
    ch = {x["channel"]: x for x in out["channels"]}
    assert ch["email"]["total"] == 2 and ch["email"]["reached_quoted"] == 1
    assert ch["email"]["conversion"] == 0.5
    assert ch["webform"]["conversion"] == 0.0
    # 他司看本组织永远为空
    assert build_insights(db, other_org.id)["channels"] == []


def test_first_response_median_and_waiting(db, org):
    a = _inq(db, org.id, created_h=100)
    _msg(db, org.id, a, "in", 95)
    _msg(db, org.id, a, "out", 88)   # 首响 12h（取最早的 out）
    _msg(db, org.id, a, "out", 80)   # 更晚的 out 不影响首响
    b = _inq(db, org.id, created_h=100)
    _msg(db, org.id, b, "out", 60)   # 首响 40h
    _inq(db, org.id, created_h=100)  # 未响应 → waiting，最长等待 ≥100h
    out = build_insights(db, org.id)["first_response"]
    assert out["responded"] == 2
    assert out["median_hours"] == 26.0  # (12+40)/2
    assert out["waiting"] == 1
    assert out["longest_waiting_hours"] >= 100.0


def test_target_hit_rate(db, org):
    inq = _inq(db, org.id, summary={"target_price": "USD 5.0 / pcs"})
    db.add(Quote(org_id=org.id, inquiry_id=inq.id, version=1, status="approved",
                 incoterm="FOB", currency="USD", quantity=100,
                 unit_cost=2.0, unit_price=4.5, customer_price=4.5,
                 total_amount=450.0, margin_rate=0.15))
    inq2 = _inq(db, org.id, summary={"target_price": "USD 3.0 / pcs"})
    db.add(Quote(org_id=org.id, inquiry_id=inq2.id, version=1, status="approved",
                 incoterm="FOB", currency="USD", quantity=100,
                 unit_cost=2.0, unit_price=4.0, customer_price=4.0,
                 total_amount=400.0, margin_rate=0.15))
    db.flush()
    out = build_insights(db, org.id)["target_hit"]
    assert out["hit"] == 1 and out["total"] == 2 and out["rate"] == 0.5


def test_insights_empty_org(db, org):
    out = build_insights(db, org.id)
    assert out["channels"] == []
    assert out["first_response"]["responded"] == 0 and out["first_response"]["waiting"] == 0
    assert out["target_hit"]["total"] == 0 and out["target_hit"]["rate"] is None


def test_insights_api(client, org):
    headers = auth_headers(client)
    r = client.get("/api/analytics/insights", headers=headers)
    assert r.status_code == 200
    body = r.json()
    assert {"channels", "first_response", "target_hit"} <= set(body)
