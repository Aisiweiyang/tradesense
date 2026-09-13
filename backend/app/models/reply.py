"""Reply draft model (human-approved before anything is sent)."""
from __future__ import annotations

from typing import Optional

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, OrgMixin, TZDateTime, TimestampMixin

REPLY_KINDS = [
    "first_reply",          # 首次询盘回复
    "ask_missing_info",     # 补充信息询问
    "product_recommend",    # 产品推荐
    "sample",               # 样品沟通
    "quote_send",           # 报价发送
    "quote_follow_up",      # 报价后跟进
    "delay_notice",         # 交期延误说明
    "alternative_offer",    # 无法满足需求的替代方案
    "polite_rejection",     # 礼貌拒绝
    "reactivation",         # 长时间未回复重新激活
]

REPLY_STATUSES = ["draft", "edited", "approved", "sent_manually", "discarded"]


class ReplyDraft(Base, OrgMixin, TimestampMixin):
    __tablename__ = "reply_drafts"

    id: Mapped[int] = mapped_column(primary_key=True)
    inquiry_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("inquiries.id"), nullable=True, index=True)  # nullable: 货件催补等非询盘草稿
    shipment_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("shipments.id"), nullable=True, index=True)
    kind: Mapped[str] = mapped_column(String(40), default="first_reply")
    tone: Mapped[str] = mapped_column(String(20), default="friendly")  # formal/friendly/concise
    subject_en: Mapped[str] = mapped_column(String(300), default="")
    body_en: Mapped[str] = mapped_column(Text, default="")
    body_zh: Mapped[str] = mapped_column(Text, default="")
    variables_json: Mapped[str] = mapped_column(Text, default="{}")
    facts_used_json: Mapped[str] = mapped_column(Text, default="[]")  # [{field, value, source}]
    needs_confirmation_json: Mapped[str] = mapped_column(Text, default="[]")
    status: Mapped[str] = mapped_column(String(20), default="draft")
    created_by_user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)
