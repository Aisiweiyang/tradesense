"""Knowledge documents, exchange rates and audit events."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Float, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, OrgMixin, TZDateTime, TimestampMixin


class KnowledgeDocument(Base, OrgMixin, TimestampMixin):
    __tablename__ = "knowledge_documents"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(300))
    content: Mapped[str] = mapped_column(Text, default="")
    tags: Mapped[str] = mapped_column(String(300), default="")


class ExchangeRate(Base, OrgMixin, TimestampMixin):
    """手工维护的汇率（不接外部 API）。存储方向按币种 ISO 代码字母序规范化，
    如 USD/CNY=7.2 表示 1 USD 兑 7.2 CNY；反向查询取倒数。每组织每币种对一行。"""
    __tablename__ = "exchange_rates"

    id: Mapped[int] = mapped_column(primary_key=True)
    base_currency: Mapped[str] = mapped_column(String(3))
    quote_currency: Mapped[str] = mapped_column(String(3))
    rate: Mapped[float] = mapped_column(Float)
    updated_by_user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)


class InquiryAttachment(Base, OrgMixin, TimestampMixin):
    """询盘附件：客户发来的报价单/图片/规格书等，供 AI Intake 提取上下文。"""
    __tablename__ = "inquiry_attachments"

    id: Mapped[int] = mapped_column(primary_key=True)
    inquiry_id: Mapped[int] = mapped_column(ForeignKey("inquiries.id"), index=True)
    file_path: Mapped[str] = mapped_column(String(500), default="")
    original_filename: Mapped[str] = mapped_column(String(300), default="")
    media_type: Mapped[str] = mapped_column(String(50), default="")
    size: Mapped[int] = mapped_column(default=0)
    extracted_text: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(20), default="pending")  # extracted / needs_manual
    uploaded_by_user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)


class AuditEvent(Base, OrgMixin, TimestampMixin):
    __tablename__ = "audit_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)
    action: Mapped[str] = mapped_column(String(100), index=True)  # login / quote.approve / reply.approve ...
    entity_type: Mapped[str] = mapped_column(String(50), default="")
    entity_id: Mapped[str] = mapped_column(String(50), default="")
    detail_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(TZDateTime, default=datetime.utcnow)
