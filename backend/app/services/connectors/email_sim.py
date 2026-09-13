"""Simulated IMAP email connector.

When no real mailbox credentials exist, this connector replays a deterministic
fixture inbox so the full pipeline (dedupe, normalization, inquiries) is
exercised WITHOUT pretending a real mailbox was connected:
    account.mode = "simulated", auth_state = "not_authorized_simulated".
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from .base import BaseConnector, PulledMessage, connector_meta

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
    connector_type = "email_imap"

    def health_check(self) -> dict:
        base = super().health_check()
        if self.account.mode == "simulated":
            base["note"] = "模拟邮箱连接器：未提供真实 IMAP 授权，展示内置演示邮件"
        return base

    def pull_messages(self, cursor: str | None) -> tuple[list[PulledMessage], str]:
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

    def normalize_message(self, raw: dict) -> PulledMessage:
        return PulledMessage(
            external_message_id=raw.get("external_message_id", ""),
            thread_external_id=raw.get("thread_external_id", ""),
            sender=raw.get("sender", ""), text=raw.get("text", ""),
            received_at=raw.get("received_at", datetime.now(timezone.utc)),
            raw=raw,
        )
