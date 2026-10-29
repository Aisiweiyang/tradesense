"""Unified connector interface.

Every channel (email / WhatsApp / web form / generic webhook) implements the
same contract so external messages converge into one inquiry model.

Modes are explicit:
  - mode="simulated": clearly labeled, NOT a real authorization, no fake sync
  - mode="live": requires real credentials from environment/config
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field as dc_field
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from ...models import ConnectorAccount, SyncCursor, SyncLog

CONNECTOR_REGISTRY: dict[str, dict] = {}


def connector_meta(connector_type: str, *, label: str, channel: str,
                   required_config: list[str], env_keys: list[str] | None = None,
                   live_supported: bool = False, description: str = ""):
    def deco(cls):
        CONNECTOR_REGISTRY[connector_type] = {
            "label": label, "channel": channel, "class": cls,
            "required_config": required_config, "env_keys": env_keys or [],
            "live_supported": live_supported, "description": description,
        }
        return cls
    return deco


@dataclass
class PulledMessage:
    external_message_id: str
    thread_external_id: str
    sender: str
    text: str
    received_at: datetime
    attachments: list = dc_field(default_factory=list)
    raw: dict = dc_field(default_factory=dict)


class BaseConnector:
    """Subclasses implement pull/normalize; ingestion idempotency is shared."""

    connector_type = "base"

    def __init__(self, db: Session, account: ConnectorAccount):
        self.db = db
        self.account = account
        try:
            self.config = json.loads(account.config_json or "{}")
        except json.JSONDecodeError:
            self.config = {}

    # ------------------------------------------------------------------ api
    def health_check(self) -> dict:
        return {"ok": True, "mode": self.account.mode,
                "authorized": self.account.mode == "live",
                "note": "模拟连接器：未连接真实账号" if self.account.mode == "simulated" else "已配置"}

    def pull_messages(self, cursor: str | None) -> tuple[list[PulledMessage], str]:
        """Return (messages, next_cursor). Simulated connectors yield fixtures."""
        raise NotImplementedError

    def normalize_message(self, raw: dict) -> PulledMessage:
        raise NotImplementedError

    def sync_status(self) -> dict:
        cur = self.db.query(SyncCursor).filter_by(
            org_id=self.account.org_id, connector_account_id=self.account.id).first()
        return {"account_id": self.account.id, "status": self.account.status,
                "mode": self.account.mode, "auth_state": self.account.auth_state,
                "last_sync_at": self.account.last_sync_at.isoformat() if self.account.last_sync_at else None,
                "cursor": cur.cursor_value if cur else None,
                "last_error": self.account.last_error or ""}

    # ------------------------------------------------------------------ log
    def log(self, event: str, level: str = "info", detail: dict | None = None) -> None:
        self.db.add(SyncLog(org_id=self.account.org_id,
                            connector_account_id=self.account.id,
                            level=level, event=event,
                            detail_json=json.dumps(detail or {}, ensure_ascii=False, default=str)))
        self.db.flush()

    def get_cursor(self) -> str:
        cur = self.db.query(SyncCursor).filter_by(
            org_id=self.account.org_id, connector_account_id=self.account.id).first()
        return cur.cursor_value if cur else ""

    def set_cursor(self, value: str) -> None:
        cur = self.db.query(SyncCursor).filter_by(
            org_id=self.account.org_id, connector_account_id=self.account.id).first()
        if cur is None:
            cur = SyncCursor(org_id=self.account.org_id, connector_account_id=self.account.id,
                             cursor_value=value)
            self.db.add(cur)
        cur.cursor_value = value

    def mark_error(self, error: str) -> None:
        self.account.status = "error"
        self.account.last_error = error[:2000]
        self.log("sync_error", "error", {"error": error[:500]})


def run_sync(db: Session, account: ConnectorAccount, ingest_fn) -> dict:
    """Pull + ingest with retry-safe error capture. ingest_fn(payload)->ingest result."""
    meta = CONNECTOR_REGISTRY.get(account.connector_type)
    if meta is None:
        return {"ok": False, "error": f"未知连接器类型 {account.connector_type}"}
    conn: BaseConnector = meta["class"](db, account)
    conn.log("sync_started")
    ingested, skipped = 0, 0
    try:
        messages, next_cursor = conn.pull_messages(conn.get_cursor())
        for m in messages:
            result = ingest_fn({
                "external_message_id": m.external_message_id,
                "thread_external_id": m.thread_external_id,
                "sender": m.sender, "text": m.text,
                "received_at": m.received_at, "attachments": m.attachments,
                "raw_json": m.raw, "external_account": conn.config.get("mailbox") or account.name,
            })
            if result.get("duplicate"):
                skipped += 1
            else:
                ingested += 1
        conn.set_cursor(next_cursor)
        account.last_sync_at = datetime.now(timezone.utc)
        account.status = "connected"
        account.last_error = ""
        account.auth_state = "authorized" if account.mode == "live" else "not_authorized_simulated"
        conn.log("sync_finished", "info", {"ingested": ingested, "skipped_duplicates": skipped})
        return {"ok": True, "ingested": ingested, "skipped_duplicates": skipped}
    except Exception as exc:  # noqa: BLE001 — connector failures must not crash API
        account.status = "error"
        account.auth_state = "not_verified" if account.mode == "live" else "not_authorized_simulated"
        account.last_error = str(exc)[:2000]
        conn.log("sync_error", "error", {"error": str(exc)[:500]})
        return {"ok": False, "error": str(exc)[:300]}
