"""Structured requirement state: slots + history + clarification log."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, OrgMixin, TZDateTime, TimestampMixin

SLOT_STATUSES = [
    "unknown", "active", "replaced", "unconstrained", "conflicting", "needs_confirmation",
]

# Canonical requirement fields (single source of truth, see services/fields.py)
FIELD_NAMES = [
    "product", "material", "color", "spec", "quantity", "target_price",
    "destination_country", "destination_port", "incoterm", "packaging",
    "customization", "certification", "lead_time", "payment_terms",
    "sample", "shipping_method", "notes",
]


class RequirementState(Base, OrgMixin, TimestampMixin):
    __tablename__ = "requirement_states"

    id: Mapped[int] = mapped_column(primary_key=True)
    inquiry_id: Mapped[int] = mapped_column(ForeignKey("inquiries.id"), index=True)
    revision: Mapped[int] = mapped_column(Integer, default=1)

    slots: Mapped[list["RequirementSlot"]] = relationship(
        back_populates="state", cascade="all,delete-orphan"
    )


class RequirementSlot(Base, OrgMixin, TimestampMixin):
    __tablename__ = "requirement_slots"
    __table_args__ = (
        # one row per (state, field); unique index created in migration for perf
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    state_id: Mapped[int] = mapped_column(ForeignKey("requirement_states.id"), index=True)
    inquiry_id: Mapped[int] = mapped_column(ForeignKey("inquiries.id"), index=True)
    field: Mapped[str] = mapped_column(String(50), index=True)
    raw_value: Mapped[str] = mapped_column(Text, default="")
    value: Mapped[str] = mapped_column(Text, default="")
    normalized_value: Mapped[str] = mapped_column(Text, default="")
    unit: Mapped[str] = mapped_column(String(30), default="")
    status: Mapped[str] = mapped_column(String(30), default="unknown")
    confidence: Mapped[float] = mapped_column(default=0.0)
    source_message_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("conversation_messages.id"), nullable=True
    )
    history_values: Mapped[str] = mapped_column(Text, default="[]")  # [{value, message_id, at}]
    locked: Mapped[bool] = mapped_column(Boolean, default=False)
    confirmed: Mapped[bool] = mapped_column(Boolean, default=False)

    state: Mapped[RequirementState] = relationship(back_populates="slots")


class RequirementHistory(Base, OrgMixin, TimestampMixin):
    __tablename__ = "requirement_history"

    id: Mapped[int] = mapped_column(primary_key=True)
    inquiry_id: Mapped[int] = mapped_column(ForeignKey("inquiries.id"), index=True)
    slot_id: Mapped[Optional[int]] = mapped_column(ForeignKey("requirement_slots.id"), nullable=True)
    field: Mapped[str] = mapped_column(String(50))
    change_type: Mapped[str] = mapped_column(String(30))  # set/update/replace/conflict/unconstrained/lock/unlock/manual_set/locked_ignored/reaffirmed
    old_value: Mapped[str] = mapped_column(Text, default="")
    new_value: Mapped[str] = mapped_column(Text, default="")
    old_status: Mapped[str] = mapped_column(String(30), default="")
    new_status: Mapped[str] = mapped_column(String(30), default="")
    source_message_id: Mapped[Optional[int]] = mapped_column(nullable=True)
    actor: Mapped[str] = mapped_column(String(30), default="system")  # system/human/ai
    note: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(TZDateTime, default=datetime.utcnow)


class ClarificationLog(Base, OrgMixin, TimestampMixin):
    __tablename__ = "clarification_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    inquiry_id: Mapped[int] = mapped_column(ForeignKey("inquiries.id"), index=True)
    field: Mapped[str] = mapped_column(String(50))
    question_en: Mapped[str] = mapped_column(Text, default="")
    question_zh: Mapped[str] = mapped_column(Text, default="")
    reason: Mapped[str] = mapped_column(Text, default="")
    priority_score: Mapped[float] = mapped_column(default=0.0)
    status: Mapped[str] = mapped_column(String(20), default="open")  # open/answered/dismissed
