"""Inquiry, conversation thread and message models."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, OrgMixin, TZDateTime, TimestampMixin, utcnow

INQUIRY_STATUSES = ["open", "clarifying", "quoted", "won", "lost", "spam"]
PROCESS_STATUSES = ["pending", "processed", "duplicate", "failed"]

# 销售漏斗九阶段：won/lost/dormant 为终态
FUNNEL_STAGES = ["new", "qualified", "clarifying", "quoted", "sample",
                 "negotiating", "won", "lost", "dormant"]
FUNNEL_STAGE_LABELS = {
    "new": "新询盘", "qualified": "有效线索", "clarifying": "澄清中",
    "quoted": "已报价", "sample": "寄样中", "negotiating": "谈判中",
    "won": "已成交", "lost": "已失败", "dormant": "休眠",
}
# 相邻转化率的口径：线性主链上的下一站
FUNNEL_NEXT = {"new": "qualified", "qualified": "clarifying",
               "clarifying": "quoted", "quoted": "sample",
               "sample": "negotiating", "negotiating": "won"}


class Inquiry(Base, OrgMixin, TimestampMixin):
    __tablename__ = "inquiries"

    id: Mapped[int] = mapped_column(primary_key=True)
    customer_id: Mapped[Optional[int]] = mapped_column(ForeignKey("customers.id"), nullable=True, index=True)
    contact_id: Mapped[Optional[int]] = mapped_column(ForeignKey("contacts.id"), nullable=True)
    owner_user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)
    title: Mapped[str] = mapped_column(String(300), default="")
    status: Mapped[str] = mapped_column(String(20), default="open")
    stage: Mapped[str] = mapped_column(String(30), default="new")
    language: Mapped[str] = mapped_column(String(20), default="en")
    raw_text: Mapped[str] = mapped_column(Text, default="")
    summary_json: Mapped[str] = mapped_column(Text, default="{}")
    completeness: Mapped[int] = mapped_column(default=0)
    quality_flag: Mapped[str] = mapped_column(String(30), default="normal")  # normal/low_quality/suspected_fraud
    source_channel: Mapped[str] = mapped_column(String(50), default="manual")
    external_message_id: Mapped[Optional[int]] = mapped_column(ForeignKey("external_messages.id"), nullable=True)
    deleted: Mapped[int] = mapped_column(default=0)

    messages: Mapped[list["ConversationMessage"]] = relationship(
        back_populates="inquiry", cascade="all,delete-orphan", order_by="ConversationMessage.id"
    )


class ConversationThread(Base, OrgMixin, TimestampMixin):
    __tablename__ = "conversation_threads"

    id: Mapped[int] = mapped_column(primary_key=True)
    inquiry_id: Mapped[int] = mapped_column(ForeignKey("inquiries.id"), index=True)
    channel: Mapped[str] = mapped_column(String(50), default="manual")
    external_account: Mapped[str] = mapped_column(String(200), default="")
    external_session_id: Mapped[str] = mapped_column(String(200), default="")


class ConversationMessage(Base, OrgMixin, TimestampMixin):
    __tablename__ = "conversation_messages"

    id: Mapped[int] = mapped_column(primary_key=True)
    inquiry_id: Mapped[int] = mapped_column(ForeignKey("inquiries.id"), index=True)
    thread_id: Mapped[Optional[int]] = mapped_column(ForeignKey("conversation_threads.id"), nullable=True)
    direction: Mapped[str] = mapped_column(String(10), default="in")  # in=outbound-from-customer, out=our reply
    sender: Mapped[str] = mapped_column(String(200), default="")
    sent_at: Mapped[Optional[datetime]] = mapped_column(TZDateTime, nullable=True)
    raw_content: Mapped[str] = mapped_column(Text, default="")
    normalized_content: Mapped[str] = mapped_column(Text, default="")
    attachments_json: Mapped[str] = mapped_column(Text, default="[]")
    external_message_id: Mapped[str] = mapped_column(String(200), default="")
    content_hash: Mapped[str] = mapped_column(String(64), default="", index=True)
    process_status: Mapped[str] = mapped_column(String(20), default="processed")
    parse_json: Mapped[str] = mapped_column(Text, default="{}")

    inquiry: Mapped[Inquiry] = relationship(back_populates="messages")


class InquiryStageEvent(Base, OrgMixin, TimestampMixin):
    """询盘阶段流转事件，销售漏斗的数据源（一次变更一条，append-only）。"""
    __tablename__ = "inquiry_stage_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    inquiry_id: Mapped[int] = mapped_column(ForeignKey("inquiries.id"), index=True)
    from_stage: Mapped[str] = mapped_column(String(30), default="")  # 空串=初次进入
    to_stage: Mapped[str] = mapped_column(String(30), index=True)
    note: Mapped[str] = mapped_column(String(300), default="")
    actor_user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(TZDateTime, default=utcnow)
