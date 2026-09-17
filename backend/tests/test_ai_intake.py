"""AI Intake：提议校验、状态机裁决（锁定/低置信/矛盾）、审计、降级与挂点。"""
import json

import pytest

from app.models import Inquiry, RequirementHistory
from app.services.ai.intake import propose_slots
from app.services.ai.runner import run_intake
from app.services.requirement_service import RequirementService
from tests.conftest import auth_headers


class FakeAI:
    name = "fake"

    def __init__(self, payload):
        self.payload = payload
        self.calls = 0

    def available(self):
        return True

    def chat_json(self, system, user, schema_hint=None, max_tokens=1200):
        self.calls += 1
        return self.payload


def _mk_payload(fields):
    return {"fields": fields}


def _patch_ai(monkeypatch, payload):
    fake = FakeAI(payload)
    import app.services.ai.intake as intake_mod
    import app.services.ai.runner as runner_mod
    monkeypatch.setattr(intake_mod, "get_ai", lambda: fake)
    monkeypatch.setattr(runner_mod, "get_ai", lambda: fake)
    return fake


def test_propose_slots_whitelist_and_evidence(monkeypatch):
    _patch_ai(monkeypatch, _mk_payload([
        {"field": "quantity", "value": "1000", "normalized": "1000",
         "confidence": 0.9, "evidence": "need 1000 pcs"},
        {"field": "brand_x", "value": "hack"},                       # 白名单外 → 丢
        {"field": "color", "value": "blue", "evidence": "not in text"},  # evidence 不在原文 → 丢
        {"field": "product", "value": "x" * 400},                    # 超长 → 丢
        {"field": "incoterm", "value": "FOB"},                       # 无 evidence → 允许
    ]))
    text = "We need 1000 pcs bottles to Hamburg."
    updates = propose_slots(text)
    assert updates is not None
    assert [u.field for u in updates] == ["quantity", "incoterm"]
    assert updates[0].confidence == 0.9
    assert "AI 提议" in updates[0].note


def test_propose_low_confidence_flags_confirmation(monkeypatch):
    _patch_ai(monkeypatch, _mk_payload([
        {"field": "color", "value": "blue", "confidence": 0.4, "evidence": "blue-ish"},
        {"field": "quantity", "value": "500", "confidence": 0.95, "evidence": "500"},
    ]))
    updates = propose_slots("something blue-ish and 500")
    by = {u.field: u for u in updates}
    assert by["color"].status_hint == "needs_confirmation"
    assert by["quantity"].status_hint == "active"


def test_propose_returns_none_without_ai(monkeypatch):
    import app.services.ai.intake as intake_mod
    from app.services.ai import NoneAI
    monkeypatch.setattr(intake_mod, "get_ai", lambda: NoneAI())
    assert propose_slots("any text") is None


def test_propose_provider_crash_returns_none(monkeypatch):
    class Boom:
        name = "boom"

        def available(self):
            return True

        def chat_json(self, *a, **k):
            raise RuntimeError("provider down")
    import app.services.ai.intake as intake_mod
    monkeypatch.setattr(intake_mod, "get_ai", lambda: Boom())
    assert propose_slots("any text") is None


def test_apply_ai_proposals_locked_never_overridden(db, org):
    from app.services.ai.intake import propose_slots  # noqa: F401 (路径存在性)

    inq = Inquiry(org_id=org.id, title="t", status="open", stage="new")
    db.add(inq)
    db.flush()
    svc = RequirementService(db, org.id)
    svc.ensure_state(inq.id)

    # 人工锁定 quantity=500
    from app.services.requirement_engine import SlotUpdate
    svc.apply_ai_proposals(inq, [SlotUpdate(
        field="quantity", raw="500", value="500", normalized="500",
        confidence=0.9, note="初始")], "fake")
    vals = svc.active_values(inq.id)
    assert vals["quantity"]["normalized"] == "500"
    db.add  # noqa: B018
    db.flush()
    # 重新锁定（第二次提议把它锁上）
    vals["quantity"]  # noqa: B018
    from sqlalchemy import select
    from app.models import RequirementSlot
    row = db.scalars(select(RequirementSlot).where(
        RequirementSlot.inquiry_id == inq.id, RequirementSlot.field == "quantity")).one()
    row.locked = True
    db.flush()

    summary = svc.apply_ai_proposals(inq, [SlotUpdate(
        field="quantity", raw="9999", value="9999", normalized="9999",
        confidence=0.99, note="AI 提议")], "fake")
    assert summary["skipped_locked"] == ["quantity"]
    vals = svc.active_values(inq.id)
    assert vals["quantity"]["normalized"] == "500"

    hist = db.query(RequirementHistory).filter_by(inquiry_id=inq.id) \
             .order_by(RequirementHistory.id.desc()).first()
    assert hist.actor.startswith("ai:fake")


def test_apply_ai_low_confidence_goes_to_confirmation(db, org):
    inq = Inquiry(org_id=org.id, title="t2", status="open", stage="new")
    db.add(inq)
    db.flush()
    svc = RequirementService(db, org.id)
    from app.services.requirement_engine import SlotUpdate
    summary = svc.apply_ai_proposals(inq, [SlotUpdate(
        field="color", raw="maybe blue", value="blue", normalized="blue",
        confidence=0.4, note="AI 提议")], "fake")
    assert summary["needs_confirmation"] == ["color"]
    assert svc.active_values(inq.id)["color"]["status"] == "needs_confirmation"


def test_create_inquiry_auto_intake(client, db, monkeypatch):
    fake = _patch_ai(monkeypatch, _mk_payload([
        {"field": "quantity", "value": "800", "normalized": "800",
         "confidence": 0.9, "evidence": "800 pcs"},
        {"field": "certification", "value": "LFGB", "confidence": 0.5,
         "evidence": "LFGB required"},
    ]))
    headers = auth_headers(client)
    r = client.post("/api/inquiries", headers=headers, json={
        "text": "We need 800 pcs bottles to Rotterdam, LFGB required."})
    assert r.status_code == 201
    body = r.json()
    assert body["ai_intake"]["proposed"] == 2
    assert "quantity" in body["ai_intake"]["applied"]
    # certification 规则已置 active，AI 同值合并不降级
    assert "certification" in body["ai_intake"]["applied"]


def test_org_toggle_disables_intake(client, db, monkeypatch):
    fake = _patch_ai(monkeypatch, _mk_payload([
        {"field": "quantity", "value": "800", "normalized": "800",
         "confidence": 0.9, "evidence": "800 pcs"}]))
    headers = auth_headers(client)
    r = client.put("/api/ai/settings", headers=headers, json={"intake_enabled": False})
    assert r.status_code == 200 and r.json()["intake_enabled"] is False
    st = client.get("/api/ai/status", headers=headers).json()
    assert st["intake_enabled"] is False

    r = client.post("/api/inquiries", headers=headers, json={
        "text": "We need 800 pcs bottles."})
    assert r.json()["ai_intake"] is None  # 关闭后走纯规则

    # member 无权改开关
    from app.models import User
    from app.security import hash_password
    db.add(User(org_id=1, email="aimember@test.cn", name="m",
                password_hash=hash_password("password123"), role="member"))
    db.commit()
    member = auth_headers(client, "aimember@test.cn")
    assert client.put("/api/ai/settings", headers=member,
                      json={"intake_enabled": True}).status_code == 403


def test_email_sim_auto_intake(db, org, monkeypatch):
    fake = _patch_ai(monkeypatch, _mk_payload([
        {"field": "destination_port", "value": "Le Havre", "normalized": "Le Havre",
         "confidence": 0.9, "evidence": "to Le Havre"}]))
    from app.models import ConnectorAccount, Inquiry
    from app.services.ingestion import ingest_external_message
    acct = ConnectorAccount(org_id=org.id, connector_type="email_imap",
                            name="sim box", mode="simulated", status="connected",
                            auth_state="authorized", config_json="{}")
    db.add(acct)
    db.flush()
    res = ingest_external_message(db, org.id, acct, {
        "external_message_id": "ai-mail-1",
        "thread_external_id": "ai:lead1",
        "sender": "lead@example.com",
        "text": "Subject: cups\n\nWe need 600 glass cups, shipping to Le Havre.",
        "raw_json": {}})
    assert res["duplicate"] is False
    inq_id = res["inquiry"].id
    vals = RequirementService(db, org.id).active_values(inq_id)
    assert vals["destination_port"]["normalized"] == "Le Havre"
    assert fake.calls >= 1


def test_attachment_upload_extract_and_delete(client, db):
    """PDF 附件：文本层提取 + 自动 AI 解析；非法类型 422；删除 204。"""
    import io as _io
    import uuid
    from pathlib import Path

    from app.seed.docgen import make_invoice

    headers = auth_headers(client)
    inq = client.post("/api/inquiries", headers=headers, json={
        "text": "Quote request for mugs."}).json()

    # 非法类型
    r = client.post(f"/api/inquiries/{inq['id']}/attachments", headers=headers,
                    files={"file": ("x.exe", b"MZ" + b"0" * 60, "application/octet-stream")})
    assert r.status_code == 422 and r.json()["error"]["code"] == "bad_file_type"

    p = Path("data/test_docs") / f"{uuid.uuid4().hex[:8]}-att.pdf"
    p.parent.mkdir(parents=True, exist_ok=True)
    make_invoice(p, invoice_no="ATT-1", total_amount="1,000.00", hs_code="6912.00",
                 description="Ceramic mug", consignee="Test Buyer")
    fake = _patch_ai(monkeypatch_this := __import__("pytest").MonkeyPatch(), _mk_payload([
        {"field": "consignee" if False else "quantity", "value": "2000",
         "normalized": "2000", "confidence": 0.9, "evidence": "Quantity: 2,000"}]))
    try:
        r = client.post(f"/api/inquiries/{inq['id']}/attachments", headers=headers,
                        files={"file": ("invoice.pdf", p.read_bytes(), "application/pdf")})
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["status"] == "extracted"
        assert body["ai_intake"]["proposed"] >= 1

        items = client.get(f"/api/inquiries/{inq['id']}/attachments", headers=headers).json()["items"]
        assert len(items) == 1 and items[0]["status"] == "extracted"

        assert client.delete(f"/api/inquiries/{inq['id']}/attachments/{body['id']}",
                             headers=headers).status_code == 204
        assert client.get(f"/api/inquiries/{inq['id']}/attachments", headers=headers).json()["items"] == []
    finally:
        monkeypatch_this.undo()


def test_attachment_scan_degrades_without_ai(client, db):
    """扫描件（无文本层）+ 无 AI：状态 needs_manual，不阻塞上传。"""
    import uuid
    from pathlib import Path

    from app.seed.docgen import make_scan_like_pdf

    headers = auth_headers(client)
    inq = client.post("/api/inquiries", headers=headers, json={"text": "scan test"}).json()
    p = Path("data/test_docs") / f"{uuid.uuid4().hex[:8]}-scan.pdf"
    p.parent.mkdir(parents=True, exist_ok=True)
    make_scan_like_pdf(p)
    r = client.post(f"/api/inquiries/{inq['id']}/attachments", headers=headers,
                    files={"file": ("scan.pdf", p.read_bytes(), "application/pdf")})
    assert r.status_code == 201
    assert r.json()["status"] == "needs_manual"
    assert r.json()["ai_intake"] is None


def test_attachment_org_isolation(client, other_org):
    headers = auth_headers(client)
    inq = client.post("/api/inquiries", headers=headers, json={"text": "mine"}).json()
    from tests.conftest import auth_headers as ah
    other = ah(client, "owner2@test.cn")
    assert client.get(f"/api/inquiries/{inq['id']}/attachments", headers=other).status_code == 404


def test_ai_crash_does_not_lose_inquiry(client, monkeypatch):
    """红线：AI 在事务中途崩溃，建单主事务必须完好（SAVEPOINT 隔离）。"""
    import app.services.ai.runner as runner_mod

    def boom(db, org_id, inq, user_id):
        raise RuntimeError("provider exploded mid-transaction")
    monkeypatch.setattr(runner_mod, "run_intake", boom)
    headers = auth_headers(client)
    r = client.post("/api/inquiries", headers=headers, json={
        "text": "We need 700 pcs bottles FOB Hamburg."})
    assert r.status_code == 201, r.text
    assert r.json()["ai_intake"] is None
    iid = r.json()["id"]
    assert client.get(f"/api/inquiries/{iid}", headers=headers).status_code == 200
