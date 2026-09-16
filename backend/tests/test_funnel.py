"""销售漏斗：转化率、停留时长（右删失）、边界、组织隔离与阶段事件写入。"""
from datetime import timedelta

from tests.conftest import auth_headers

from app.models import Inquiry, InquiryStageEvent
from app.services.funnel import build_funnel


def _utcnow():
    from datetime import datetime, timezone
    return datetime.now(timezone.utc)


def _h_ago(hours: float):
    return _utcnow() - timedelta(hours=hours)


def _stage_map(result):
    return {s["stage"]: s for s in result["stages"]}


def _mk_inquiry(db, org_id, stage="new", days_ago=0):
    inq = Inquiry(org_id=org_id, title="funnel test", status="open", stage=stage)
    if days_ago:
        inq.created_at = _utcnow() - timedelta(days=days_ago)
    db.add(inq)
    db.flush()
    return inq


def _evt(db, org_id, inq_id, to_stage, hours_ago, from_stage=""):
    db.add(InquiryStageEvent(org_id=org_id, inquiry_id=inq_id, from_stage=from_stage,
                             to_stage=to_stage, occurred_at=_h_ago(hours_ago)))
    db.flush()


def test_empty_funnel(db, org):
    out = build_funnel(db, org.id)
    assert len(out["stages"]) == 9
    for s in out["stages"]:
        assert s["count"] == 0 and s["reached"] == 0
        assert s["conversion_to_next"] is None and s["median_dwell_hours"] is None


def test_conversion_rates(db, org):
    # 4 个询盘进过 new，其中 2 个到 qualified，其中 1 个到 clarifying
    for i in range(4):
        inq = _mk_inquiry(db, org.id, stage="new" if i >= 2 else "clarifying")
        _evt(db, org.id, inq.id, "new", hours_ago=100 - i)
        if i < 2:
            _evt(db, org.id, inq.id, "qualified", hours_ago=90 - i, from_stage="new")
        if i < 1:
            _evt(db, org.id, inq.id, "clarifying", hours_ago=80, from_stage="qualified")
    m = _stage_map(build_funnel(db, org.id))
    assert m["new"]["reached"] == 4
    assert m["qualified"]["reached"] == 2
    assert m["new"]["conversion_to_next"] == 0.5
    assert m["qualified"]["conversion_to_next"] == 0.5
    assert m["clarifying"]["conversion_to_next"] == 0.0  # 触达过但没人到 quoted


def test_conversion_none_when_denominator_zero(db, org):
    inq = _mk_inquiry(db, org.id, stage="quoted")
    _evt(db, org.id, inq.id, "new", hours_ago=48)
    _evt(db, org.id, inq.id, "qualified", hours_ago=40, from_stage="new")
    m = _stage_map(build_funnel(db, org.id))
    assert m["sample"]["reached"] == 0
    assert m["sample"]["conversion_to_next"] is None


def test_median_dwell_odd_and_even(db, org):
    # 询盘 A：new 停 10h → qualified 停 15h；询盘 B：new 停 20h；询盘 C：new 停 30h
    a = _mk_inquiry(db, org.id, stage="quoted")
    _evt(db, org.id, a.id, "new", hours_ago=25)
    _evt(db, org.id, a.id, "qualified", hours_ago=15, from_stage="new")
    _evt(db, org.id, a.id, "quoted", hours_ago=0, from_stage="qualified")
    b = _mk_inquiry(db, org.id)
    _evt(db, org.id, b.id, "new", hours_ago=20)
    c = _mk_inquiry(db, org.id)
    _evt(db, org.id, c.id, "new", hours_ago=30)
    m = _stage_map(build_funnel(db, org.id))
    # new 样本 [30, 20, 10]（还在 new 的 B/C 按至今时长计入）→ 偶数个取平均
    assert m["new"]["median_dwell_hours"] == 20.0
    assert m["qualified"]["median_dwell_hours"] == 15.0


def test_right_censored_dwell_uses_now(db, org):
    # 单事件且仍在 new：停留时长按"至今"计，为右删失的保守下界
    inq = _mk_inquiry(db, org.id, days_ago=2)
    _evt(db, org.id, inq.id, "new", hours_ago=40)
    m = _stage_map(build_funnel(db, org.id))
    assert 40.0 <= m["new"]["median_dwell_hours"] <= 48.5


def test_no_event_inquiry_falls_back_to_current_stage(db, org):
    # 存量兜底：无事件的询盘按当前阶段触达 + 创建至今停留
    _mk_inquiry(db, org.id, stage="quoted", days_ago=3)
    m = _stage_map(build_funnel(db, org.id))
    assert m["quoted"]["reached"] == 1
    assert m["quoted"]["count"] == 1
    assert m["quoted"]["median_dwell_hours"] >= 71.0


def test_org_isolation(db, org, other_org):
    inq = _mk_inquiry(db, org.id, stage="quoted")
    _evt(db, org.id, inq.id, "new", hours_ago=48)
    _evt(db, org.id, inq.id, "quoted", hours_ago=10, from_stage="new")
    mine = _stage_map(build_funnel(db, org.id))
    theirs = _stage_map(build_funnel(db, other_org.id))
    assert mine["quoted"]["reached"] == 1
    assert theirs["quoted"]["reached"] == 0


def test_create_and_status_write_events(client, db):
    headers = auth_headers(client)
    r = client.post("/api/inquiries", json={"text": "Please quote 500 vacuum bottles 500ml FOB"},
                    headers=headers)
    inq_id = r.json()["id"]

    def events():
        return db.query(InquiryStageEvent).filter_by(inquiry_id=inq_id) \
                 .order_by(InquiryStageEvent.id).all()

    assert [(e.from_stage, e.to_stage) for e in events()] == [("", "new")]

    # 阶段变化写事件，重复设置不写
    client.post(f"/api/inquiries/{inq_id}/status", json={"stage": "quoted"}, headers=headers)
    client.post(f"/api/inquiries/{inq_id}/status", json={"stage": "quoted"}, headers=headers)
    assert [(e.from_stage, e.to_stage) for e in events()] == [("", "new"), ("new", "quoted")]

    # won/lost 终态自动同步阶段并写事件
    client.post(f"/api/inquiries/{inq_id}/status", json={"status": "won"}, headers=headers)
    db.expire_all()
    assert [(e.from_stage, e.to_stage) for e in events()][-1] == ("quoted", "won")
    assert db.get(Inquiry, inq_id).stage == "won"

    client.post(f"/api/inquiries/{inq_id}/status", json={"status": "lost"}, headers=headers)
    db.expire_all()
    assert db.get(Inquiry, inq_id).stage == "lost"


def test_status_rejects_invalid_stage(client):
    """传了不存在的阶段：422 明确拒绝，不静默吞掉。"""
    headers = auth_headers(client)
    inq = client.post("/api/inquiries", json={"text": "Quote 500 bottles FOB"},
                      headers=headers).json()
    r = client.post(f"/api/inquiries/{inq['id']}/status",
                    json={"stage": "frobnicating"}, headers=headers)
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "invalid_stage"


def test_status_rejects_invalid_status_and_quality_flag(client):
    """status / quality_flag 传非法值：422 拒绝（与 stage 同口径），不再静默忽略。"""
    headers = auth_headers(client)
    inq = client.post("/api/inquiries", json={"text": "Quote 300 glass cups FOB"},
                      headers=headers).json()
    for payload, code in (
        ({"status": "archived"}, "invalid_status"),
        ({"quality_flag": "excellent"}, "invalid_quality_flag"),
    ):
        r = client.post(f"/api/inquiries/{inq['id']}/status", json=payload, headers=headers)
        assert r.status_code == 422, payload
        assert r.json()["error"]["code"] == code
    # 合法值不受影响
    r = client.post(f"/api/inquiries/{inq['id']}/status",
                    json={"status": "clarifying", "quality_flag": "normal"}, headers=headers)
    assert r.status_code == 200
    assert r.json()["status"] == "clarifying"


def test_ingested_inquiry_gets_first_event(db, org):
    """渠道进来的询盘也写首个阶段事件，漏斗触达与手动创建口径一致。"""
    from app.models import ConnectorAccount
    from app.services.ingestion import ingest_external_message

    acct = ConnectorAccount(org_id=org.id, connector_type="generic_webhook",
                            name="test webhook", mode="live", status="connected",
                            auth_state="authorized", config_json="{}")
    db.add(acct)
    db.flush()
    res = ingest_external_message(db, org.id, acct, {
        "external_message_id": "evt-1",
        "thread_external_id": "wh:new-lead",
        "sender": "lead@example.com",
        "text": "Subject: New inquiry\n\nWe need 500 vacuum bottles, FOB.",
        "raw_json": {},
    })
    assert res["duplicate"] is False
    inq_id = int(res["inquiry_id"]) if "inquiry_id" in res else None
    if inq_id is None:
        from app.models import Inquiry
        inq_id = db.query(Inquiry).filter_by(org_id=org.id).order_by(
            Inquiry.id.desc()).first().id
    evts = db.query(InquiryStageEvent).filter_by(inquiry_id=inq_id).all()
    assert [(e.from_stage, e.to_stage) for e in evts] == [("", "new")]
