"""Follow-up task model."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, OrgMixin, TZDateTime, TimestampMixin

FOLLOWUP_STATUSES = ["pending", "done", "snoozed", "cancelled"]


class FollowUpTask(Base, OrgMixin, TimestampMixin):
    __tablename__ = "follow_up_tasks"

    id: Mapped[int] = mapped_column(primary_key=True)
    inquiry_id: Mapped[Optional[int]] = mapped_column(ForeignKey("inquiries.id"), nullable=True, index=True)
    customer_id: Mapped[Optional[int]] = mapped_column(ForeignKey("customers.id"), nullable=True, index=True)
    title: Mapped[str] = mapped_column(String(300))
    description: Mapped[str] = mapped_column(Text, default="")
    task_type: Mapped[str] = mapped_column(String(40), default="follow_up")  # ask_missing/send_catalog/sample/quote/check_cert/follow_up/reactivate
    due_at: Mapped[Optional[datetime]] = mapped_column(TZDateTime, nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    priority: Mapped[str] = mapped_column(String(20), default="normal")
    reason_json: Mapped[str] = mapped_column(Text, default="{}")  # why this task was suggested (explainable)
    created_by_user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(TZDateTime, nullable=True)
