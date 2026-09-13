"""Connector idempotency + sync recovery tests."""
import json
from datetime import datetime, timedelta, timezone

from app.models import ConnectorAccount, ExternalMessage
from app.services.connectors import run_sync
from app.services.ingestion import ingest_external_message


def _account(db, org_id, ctype="email_imap", mode="simulated"):
    acct = ConnectorAccount(org_id=org_id, connector_type=ctype, name=f"测试 {ctype}",
                            mode=mode, status="disconnected",
                            auth_state="not_authorized_simulated",
                            config_json=json.dumps({"mailbox": "sales@test.cn"}))
    db.add(acct)
    db.flush()
    return acct


def test_email_sim_sync_ingests_once(db, org):
    acct = _account(db, org.id)

    def ingest(payload):
        res = ingest_external_message(db, org.id, acct, payload)
        db.flush()
        return res

    r1 = run_sync(db, acct, ingest)
    assert r1["ok"] and r1["ingested"] == 1
    # cursor advanced → next sync pulls the SECOND fixture mail, not the same one again
    r2 = run_sync(db, acct, ingest)
    assert r2["ok"] and r2["ingested"] == 1
    # inbox exhausted → nothing more
    r3 = run_sync(db, acct, ingest)
    assert r3["ok"] and r3["ingested"] == 0
    from app.models import ExternalMessage
    exts = db.query(ExternalMessage).filter_by(connector_account_id=acct.id).all()
    assert len(exts) == 2
    assert len({e.external_message_id for e in exts}) == 2


def test_same_external_message_id_is_duplicate(db, org):
    acct = _account(db, org.id)
    payload = {"external_message_id": "ext-1", "thread_external_id": "t1",
               "sender": "a@b.co", "text": "Need 500 insulated bottles FOB",
               "received_at": datetime.now(timezone.utc)}
    r1 = ingest_external_message(db, org.id, acct, payload)
    r2 = ingest_external_message(db, org.id, acct, dict(payload))
    assert not r1["duplicate"] and r2["duplicate"]
    assert "ext-1" in r2["reason"]


def test_same_content_same_thread_is_duplicate(db, org):
    acct = _account(db, org.id)
    payload = {"external_message_id": "", "thread_external_id": "thread-A",
               "sender": "a@b.co", "text": "Need 300 mugs DDP Dubai",
               "received_at": datetime.now(timezone.utc)}
    r1 = ingest_external_message(db, org.id, acct, dict(payload))
    r2 = ingest_external_message(db, org.id, acct, dict(payload))
    assert not r1["duplicate"] and r2["duplicate"]
    assert "identical content" in r2["reason"]


def test_same_content_different_thread_not_duplicate(db, org):
    acct = _account(db, org.id)
    r1 = ingest_external_message(db, org.id, acct, {
        "external_message_id": "m-1", "thread_external_id": "t-1",
        "sender": "a@b.co", "text": "Need 300 mugs DDP Dubai",
        "received_at": datetime.now(timezone.utc)})
    r2 = ingest_external_message(db, org.id, acct, {
        "external_message_id": "m-2", "thread_external_id": "t-2",
        "sender": "c@d.co", "text": "Need 300 mugs DDP Dubai",
        "received_at": datetime.now(timezone.utc)})
    assert not r1["duplicate"] and not r2["duplicate"]


def test_whatsapp_webhook_normalization(db, org):
    acct = _account(db, org.id, "whatsapp_cloud")
    from app.services.connectors import get_connector

    conn = get_connector(db, acct)
    msgs = conn.handle_webhook({
        "entry": [{"changes": [{"value": {
            "contacts": [{"profile": {"name": "Lukas"}}],
            "messages": [{"id": "wamid.X", "from": "4915111", "type": "text",
                          "text": {"body": "Need 800 travel mugs"},
                          "timestamp": "1759900000"}]}}]}]})
    assert len(msgs) == 1
    assert msgs[0]["external_message_id"] == "wamid.X"
    assert msgs[0]["thread_external_id"].startswith("wa:4915111")


def test_sync_failure_recorded(db, org):
    acct = _account(db, org.id, "email_imap")

    def boom(payload):
        raise RuntimeError("IMAP 服务器连接失败")

    result = run_sync(db, acct, boom)
    assert not result["ok"]
    assert acct.status == "error"
    assert "IMAP" in acct.last_error
    from app.models import SyncLog
    logs = db.query(SyncLog).filter_by(connector_account_id=acct.id).all()
    assert any(l.level == "error" for l in logs)


def test_sync_recovery_after_failure(db, org):
    acct = _account(db, org.id)

    state = {"fail": True}

    def flaky(payload):
        if state["fail"]:
            raise RuntimeError("temporary outage")
        return ingest_external_message(db, org.id, acct, payload)

    r1 = run_sync(db, acct, flaky)
    assert not r1["ok"]
    state["fail"] = False
    r2 = run_sync(db, acct, flaky)
    assert r2["ok"] and r2["ingested"] == 1
    assert acct.status == "connected"


def test_simulated_accounts_never_claim_real_auth(db, org):
    acct = _account(db, org.id, mode="simulated")
    assert acct.auth_state == "not_authorized_simulated"
    from app.services.connectors import get_connector

    status = get_connector(db, acct).sync_status()
    assert status["mode"] == "simulated"
