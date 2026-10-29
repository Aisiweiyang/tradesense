"""Read-only IMAP over TLS, with an explicit offline demo mode.

When no real mailbox credentials exist, this connector replays a deterministic
fixture inbox so the full pipeline (dedupe, normalization, inquiries) is
exercised WITHOUT pretending a real mailbox was connected:
    account.mode = "simulated", auth_state = "not_authorized_simulated".
"""
from __future__ import annotations

import hashlib
import imaplib
import os
import re
import ssl
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from email import policy
from email.parser import BytesParser
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser

from .base import BaseConnector, PulledMessage, connector_meta


class _HTMLText(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.hidden = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self.hidden += 1
        elif tag in ("p", "br", "div", "li", "tr") and not self.hidden:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in ("script", "style"):
            self.hidden = max(0, self.hidden - 1)
        elif tag in ("p", "div", "li", "tr") and not self.hidden:
            self.parts.append("\n")

    def handle_data(self, data):
        if not self.hidden:
            self.parts.append(data)


# Deterministic simulated inbox (used for demo/tests; cursor slices it)
SIMULATED_INBOX = [
    {
        "external_message_id": "sim-mail-001",
        "thread_external_id": "mailbox1/threads/t-1001",
        "sender": "anna.schmidt@hauskonzept-gmbh.de",
        "subject": "Inquiry: insulated water bottles 500ml",
        "text": ("Subject: Inquiry: insulated water bottles 500ml\n\n"
                 "Dear Sir or Madam,\n\n"
                 "We found your company on Alibaba and are interested in your vacuum insulated "
                 "bottles. We need 5,000 pcs of 500ml double wall stainless steel bottles in matte "
                 "black with our logo printed. Could you quote FOB Hamburg? We target a price "
                 "around USD 4.5 per piece. Delivery within 45 days is required. LFGB certification "
                 "is mandatory for the German market.\n\n"
                 "Best regards,\nAnna Schmidt\nHausKonzept GmbH, Hamburg, Germany"),
    },
    {
        "external_message_id": "sim-mail-002",
        "thread_external_id": "mailbox1/threads/t-1002",
        "sender": "john.miller@kitchendoor-us.com",
        "subject": "BPA free tritan bottles",
        "text": ("Subject: BPA free tritan bottles\n\n"
                 "Hi,\n\n"
                 "Do you make sports bottles in tritan? Please send catalog and best price for "
                 "10,000pcs, ship to Los Angeles. Any color is fine. FDA food grade required.\n\n"
                 "John Miller\nKitchenDoor LLC, United States"),
    },
]


@connector_meta("email_imap", label="邮箱 (IMAP)", channel="email",
                required_config=["mailbox", "host", "port"],
                env_keys=["IMAP_PASSWORD"],
                live_supported=True,
                description="IMAP 只读拉取询盘邮件；默认仅生成草稿，绝不自动发送。")
class SimulatedEmailConnector(BaseConnector):
    # Historical class name retained for existing imports and integrations.
    connector_type = "email_imap"

    @contextmanager
    def _mailbox(self):
        client = None
        try:
            host = str(self.config.get("host") or "").strip()
            mailbox = str(self.config.get("mailbox") or "").strip()
            password = os.environ.get("IMAP_PASSWORD", "")
            port = int(self.config.get("port") or 993)
            if not host or not mailbox or not password or not 0 < port < 65536:
                raise ValueError("missing IMAP configuration")
            client = imaplib.IMAP4_SSL(host, port, timeout=20,
                                      ssl_context=ssl.create_default_context())
            if client.login(mailbox, password)[0] != "OK":
                raise ValueError("IMAP login failed")
            if client.select(str(self.config.get("folder") or "INBOX"), readonly=True)[0] != "OK":
                raise ValueError("IMAP folder unavailable")
            yield client
        except (OSError, imaplib.IMAP4.error, ValueError, TypeError) as exc:
            # Never expose credentials/server diagnostic payloads or silently
            # fall back to fixtures after a live connection failure.
            raise ConnectionError("IMAP 连接或收信失败，请检查 TLS 端口、邮箱授权码和收件文件夹后重试") from exc
        finally:
            if client is not None:
                try:
                    client.logout()
                except (OSError, imaplib.IMAP4.error):
                    pass

    def health_check(self) -> dict:
        if self.account.mode == "simulated":
            base = super().health_check()
            base["note"] = "模拟邮箱连接器：未提供真实 IMAP 授权，展示内置演示邮件"
            return base
        try:
            with self._mailbox():
                pass
            return {"ok": True, "mode": "live", "authorized": True,
                    "note": "IMAP 只读连接已验证"}
        except ConnectionError as exc:
            return {"ok": False, "mode": "live", "authorized": False, "note": str(exc)}

    def pull_messages(self, cursor: str | None) -> tuple[list[PulledMessage], str]:
        if self.account.mode == "live":
            return self._pull_live(cursor)
        start = int(cursor) if (cursor or "").isdigit() else 0
        batch = SIMULATED_INBOX[start:start + 1]
        msgs = []
        for m in batch:
            msgs.append(PulledMessage(
                external_message_id=m["external_message_id"],
                thread_external_id=m["thread_external_id"],
                sender=m["sender"],
                text=m["text"],
                received_at=datetime.now(timezone.utc) - timedelta(hours=2 + start),
                raw={"subject": m["subject"], "simulated": True},
            ))
        next_cursor = str(start + len(batch))
        return msgs, next_cursor

    def _pull_live(self, cursor: str | None) -> tuple[list[PulledMessage], str]:
        identity = [str(self.config.get(k) or "") for k in ("host", "port", "mailbox")]
        identity.append(str(self.config.get("folder") or "INBOX"))
        namespace = hashlib.sha256("\0".join(identity).encode()).hexdigest()[:16]
        with self._mailbox() as client:
            _, values = client.response("UIDVALIDITY")
            validity = values[0].decode("ascii") if values and values[0] else ""
            if not validity.isdigit():
                raise ValueError("IMAP UIDVALIDITY missing")
            prefix = f"imap:{namespace}:{validity}:"
            # Legacy demo cursors and a mailbox identity/UIDVALIDITY change
            # start a fresh UID sequence; they must never skip live mail.
            last_uid = int(cursor[len(prefix):]) if cursor and cursor.startswith(prefix) else 0
            status, data = client.uid("search", None, "UID", f"{last_uid + 1}:*")
            if status != "OK":
                raise ValueError("IMAP search failed")
            # n:* can include the last message even when n exceeds its UID.
            uids = sorted({int(u) for u in (data[0] or b"").split() if int(u) > last_uid})
            messages = []
            for uid in uids[:50]:
                status, payload = client.uid("fetch", str(uid), "(BODY.PEEK[])")
                if status != "OK":
                    raise ValueError("IMAP fetch failed")
                raw = next((p[1] for p in payload if isinstance(p, tuple)
                            and isinstance(p[1], bytes)), None)
                if raw is None:
                    raise ValueError("IMAP returned no message body")
                messages.append(self._parse_mail(raw, f"{prefix}{uid}", namespace))
                last_uid = uid
            return messages, f"{prefix}{last_uid}"

    def _parse_mail(self, raw: bytes, external_id: str, namespace: str) -> PulledMessage:
        mail = BytesParser(policy=policy.default).parsebytes(raw)
        subject = str(mail.get("Subject") or "")
        body = mail.get_body(preferencelist=("plain", "html"))
        text = ""
        if body is not None:
            try:
                text = body.get_content()
            except (LookupError, UnicodeError):
                text = (body.get_payload(decode=True) or b"").decode("utf-8", errors="replace")
            if body.get_content_type() == "text/html":
                parser = _HTMLText()
                parser.feed(text)
                text = "".join(parser.parts).strip()
        try:
            received = parsedate_to_datetime(str(mail.get("Date") or ""))
            received = received.replace(tzinfo=timezone.utc) if received.tzinfo is None else received
            received = received.astimezone(timezone.utc)
        except (ValueError, TypeError, OverflowError):
            received = datetime.now(timezone.utc)
        message_id = str(mail.get("Message-ID") or "")
        refs = re.findall(r"<[^>]+>", str(mail.get("References") or mail.get("In-Reply-To") or ""))
        thread = refs[0] if refs else (message_id or external_id)
        return PulledMessage(
            external_message_id=external_id, thread_external_id=f"imap:{namespace}:{thread}",
            sender=str(mail.get("From") or ""),
            text=f"Subject: {subject}\n\n{text}".strip(), received_at=received,
            attachments=[{"filename": part.get_filename() or "", "content_type": part.get_content_type(),
                          "status": "metadata_only"} for part in mail.iter_attachments()],
            raw={"subject": subject, "message_id": message_id, "body": text, "simulated": False},
        )

    def normalize_message(self, raw: dict) -> PulledMessage:
        return PulledMessage(
            external_message_id=raw.get("external_message_id", ""),
            thread_external_id=raw.get("thread_external_id", ""),
            sender=raw.get("sender", ""), text=raw.get("text", ""),
            received_at=raw.get("received_at", datetime.now(timezone.utc)),
            raw=raw,
        )
