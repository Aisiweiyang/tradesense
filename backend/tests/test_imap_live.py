"""IMAP protocol tests use a fake server; no real mailbox or network access."""
import json
from email.message import EmailMessage

import pytest

from app.models import ConnectorAccount
from app.services.connectors import get_connector, run_sync
from tests.conftest import auth_headers


class FakeIMAP:
    def __init__(self):
        self.calls = []
        self.validity = b"100"
        self.messages = {1: self.mail("one"), 2: self.mail("two")}
        self.fail = None

    @staticmethod
    def mail(subject, html=False):
        m = EmailMessage()
        m["Subject"] = "询盘 " + subject
        m["From"] = "客户 <buyer@example.com>"
        m["Date"] = "Fri, 30 Oct 2026 09:00:00 +0800"
        m["Message-ID"] = f"<{subject}@example.com>"
        m.set_content("<p>Need 500 bottles</p>" if html else "Need 500 bottles", subtype="html" if html else "plain")
        return m.as_bytes()

    def login(self, user, password):
        self.calls.append(("login", user))
        if self.fail == "login":
            raise OSError("test authentication failure")
        assert password == "test-only-password"
        return "OK", [b"logged in"]

    def select(self, folder, readonly=False):
        self.calls.append(("select", folder, readonly))
        return ("NO", []) if self.fail == "select" else ("OK", [b"2"])

    def response(self, name):
        assert name == "UIDVALIDITY"
        return name, [self.validity]

    def uid(self, command, *args):
        self.calls.append((command, *args))
        if self.fail == command:
            return "NO", [b"server failure"]
        if command == "search":
            # Servers may include the latest UID for an out-of-range n:* search.
            return "OK", [b" ".join(str(k).encode() for k in self.messages)]
        if command == "fetch":
            uid = int(args[0])
            return "OK", [(b"1 (BODY[])", self.messages[uid]), b")"]
        raise AssertionError(command)

    def logout(self):
        self.calls.append(("logout",))
        return "BYE", []


@pytest.fixture()
def imap_case(db, org, monkeypatch):
    import imaplib
    fake = FakeIMAP()
    def connect(host, port, **kw):
        assert (host, port) == ("imap.example.com", 993)
        assert kw["timeout"] > 0
        assert kw["ssl_context"].check_hostname is True
        fake.calls.append(("connect", host, port))
        return fake
    monkeypatch.setattr(imaplib, "IMAP4_SSL", connect)
    monkeypatch.setenv("IMAP_PASSWORD", "test-only-password")
    a = ConnectorAccount(org_id=org.id, connector_type="email_imap", name="test mailbox",
        mode="live", status="disconnected", auth_state="not_verified",
        config_json=json.dumps({"mailbox": "sales@example.com", "host": "imap.example.com", "port": "993"}))
    db.add(a)
    db.flush()
    return a, fake, get_connector(db, a)


def test_live_pull_uses_readonly_imap_and_uid_cursor(imap_case):
    _, fake, conn = imap_case
    msgs, cursor = conn.pull_messages("")
    assert len(msgs) == 2 and all(m.raw["simulated"] is False for m in msgs)
    assert msgs[0].sender == "客户 <buyer@example.com>"
    assert "询盘 one" in msgs[0].text and "Need 500 bottles" in msgs[0].text
    assert msgs[0].received_at.isoformat() == "2026-10-30T01:00:00+00:00"
    assert ("select", "INBOX", True) in fake.calls
    assert all("BODY.PEEK[]" in c[2] for c in fake.calls if c[0] == "fetch")
    assert cursor.startswith("imap:")
    again, cursor2 = conn.pull_messages(cursor)
    assert again == [] and cursor2 == cursor
    fake.messages[3] = fake.mail("three", html=True)
    newer, _ = conn.pull_messages(cursor)
    assert len(newer) == 1 and "<p>" not in newer[0].text


def test_uidvalidity_reset_restarts_without_id_collision(imap_case):
    _, fake, conn = imap_case
    old, cursor = conn.pull_messages("")
    fake.validity = b"200"
    new, _ = conn.pull_messages(cursor)
    assert len(new) == 2
    assert {m.external_message_id for m in old}.isdisjoint(m.external_message_id for m in new)


def test_live_sync_batches_and_clears_stale_error(db, imap_case):
    account, fake, conn = imap_case
    account.last_error = "previous temporary failure"
    fake.messages = {i: fake.mail(str(i)) for i in range(1, 53)}
    seen = []
    def ingest(payload):
        seen.append(payload["external_message_id"])
        return {"duplicate": False}
    assert run_sync(db, account, ingest)["ingested"] == 50
    assert account.last_error == "" and account.auth_state == "authorized"
    assert run_sync(db, account, ingest)["ingested"] == 2
    assert run_sync(db, account, ingest)["ingested"] == 0
    assert len(set(seen)) == 52


def test_missing_uidvalidity_fails_without_ingestion(db, imap_case):
    account, fake, conn = imap_case
    fake.validity = None
    result = run_sync(db, account, lambda payload: pytest.fail("ambiguous mailbox must not ingest"))
    assert result["ok"] is False and conn.get_cursor() == ""


def test_attachment_metadata_and_html_do_not_import_script(imap_case):
    _, fake, conn = imap_case
    m = EmailMessage()
    m["Subject"] = "HTML enquiry"
    m.set_content("<p>Need <b>500</b> bottles</p><script>do not import</script>", subtype="html")
    m.add_attachment(b"example", maintype="application", subtype="pdf", filename="spec.pdf")
    fake.messages = {1: m.as_bytes()}
    msgs, _ = conn.pull_messages("")
    assert "Need 500 bottles" in msgs[0].text and "do not import" not in msgs[0].text
    assert msgs[0].attachments == [{"filename": "spec.pdf", "content_type": "application/pdf", "status": "metadata_only"}]


@pytest.mark.parametrize("failure", ["login", "select", "search", "fetch"])
def test_live_failure_never_replays_demo_or_advances_cursor(db, imap_case, failure):
    account, fake, conn = imap_case
    fake.fail = failure
    result = run_sync(db, account, lambda payload: pytest.fail("must not ingest demo data"))
    assert result["ok"] is False
    assert account.status == "error"
    assert conn.get_cursor() == ""
    assert "test-only-password" not in json.dumps(result)
    assert ("logout",) in fake.calls


def test_create_mailbox_is_unverified_until_connection_test(client, imap_case):
    _, fake, _ = imap_case
    h = auth_headers(client)
    r = client.post("/api/connectors", headers=h, json={
        "connector_type": "email_imap", "name": "Live inbox",
        "config": {"mailbox": "sales@example.com", "host": "imap.example.com", "port": "993"},
    })
    assert r.status_code == 201, r.text
    assert r.json()["auth_state"] == "not_verified"
    url = f"/api/connectors/{r.json()['id']}"
    assert client.post(url + "/test", headers=h).json()["authorized"] is True
    assert client.get(url + "/status", headers=h).json()["auth_state"] == "authorized"
    fake.fail = "login"
    assert client.post(url + "/test", headers=h).json()["authorized"] is False
    status = client.get(url + "/status", headers=h).json()
    assert status["status"] == "error" and status["auth_state"] != "authorized"
    assert status["last_error"]
