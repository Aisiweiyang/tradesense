"""Connector accounts, external messages, sync cursors and sync logs."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, OrgMixin, TZDateTime, TimestampMixin

CONNECTOR_TYPES = ["email_imap", "email_gmail_oauth", "whatsapp_cloud", "webform", "generic_webhook", "platform_csv"]
CONNECTOR_MODES = ["simulated", "live"]
CONNECTOR_STATUSES = ["disconnected", "connected", "error", "unauthorized"]


class ConnectorAccount(Base, OrgMixin, TimestampMixin):
    __tablename__ = "connector_accounts"

    id: Mapped[int] = mapped_column(primary_key=True)
    connector_type: Mapped[str] = mapped_column(String(40), index=True)
    name: Mapped[str] = mapped_column(String(200), default="")
    mode: Mapped[str] = mapped_column(String(20), default="simulated")  # simulated = NOT a real authorization
    status: Mapped[str] = mapped_column(String(20), default="disconnected")
    config_json: Mapped[str] = mapped_column(Text, default="{}")  # secrets come from env, only non-secret config here
    last_sync_at: Mapped[Optional[datetime]] = mapped_column(TZDateTime, nullable=True)
    last_error: Mapped[str] = mapped_column(Text, default="")
    auth_state: Mapped[str] = mapped_column(String(30), default="not_authorized")  # clear: no fake "connected"


class ExternalMessage(Base, OrgMixin, TimestampMixin):
    __tablename__ = "external_messages"

    id: Mapped[int] = mapped_column(primary_key=True)
    connector_account_id: Mapped[int] = mapped_column(ForeignKey("connector_accounts.id"), index=True)
    channel: Mapped[str] = mapped_column(String(40), index=True)
    external_account: Mapped[str] = mapped_column(String(200), default="")
    thread_external_id: Mapped[str] = mapped_column(String(200), default="", index=True)
    external_message_id: Mapped[str] = mapped_column(String(200), default="", index=True)
    sender: Mapped[str] = mapped_column(String(200), default="")
    received_at: Mapped[Optional[datetime]] = mapped_column(TZDateTime, nullable=True)
    raw_content: Mapped[str] = mapped_column(Text, default="")
    normalized_content: Mapped[str] = mapped_column(Text, default="")
    attachments_json: Mapped[str] = mapped_column(Text, default="[]")
    content_hash: Mapped[str] = mapped_column(String(64), default="", index=True)
    process_status: Mapped[str] = mapped_column(String(20), default="pending")  # pending/processed/duplicate/failed
    inquiry_id: Mapped[Optional[int]] = mapped_column(ForeignKey("inquiries.id"), nullable=True, index=True)
    retry_count: Mapped[int] = mapped_column(default=0)
    error: Mapped[str] = mapped_column(Text, default="")


class SyncCursor(Base, OrgMixin, TimestampMixin):
    __tablename__ = "sync_cursors"

    id: Mapped[int] = mapped_column(primary_key=True)
    connector_account_id: Mapped[int] = mapped_column(ForeignKey("connector_accounts.id"), index=True)
    cursor_value: Mapped[str] = mapped_column(String(200), default="")


class SyncLog(Base, OrgMixin, TimestampMixin):
    __tablename__ = "sync_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    connector_account_id: Mapped[int] = mapped_column(ForeignKey("connector_accounts.id"), index=True)
    level: Mapped[str] = mapped_column(String(10), default="info")  # info/warn/error
    event: Mapped[str] = mapped_column(String(100), default="")
    detail_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(TZDateTime, default=datetime.utcnow)
