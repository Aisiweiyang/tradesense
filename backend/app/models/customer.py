"""Customer and contact models (lightweight CRM)."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, OrgMixin, TZDateTime, TimestampMixin

SALES_STAGES = [
    "new", "qualified", "clarifying", "quoted", "sample",
    "negotiating", "won", "lost", "dormant",
]


class Customer(Base, OrgMixin, TimestampMixin):
    __tablename__ = "customers"

    id: Mapped[int] = mapped_column(primary_key=True)
    company_name: Mapped[str] = mapped_column(String(255))
    country: Mapped[str] = mapped_column(String(100), default="")
    source_channel: Mapped[str] = mapped_column(String(50), default="manual")  # email/whatsapp/webform/manual/...
    tags: Mapped[str] = mapped_column(String(500), default="")
    priority: Mapped[str] = mapped_column(String(20), default="normal")  # low/normal/high
    stage: Mapped[str] = mapped_column(String(30), default="new")
    owner_user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)
    last_contact_at: Mapped[Optional[datetime]] = mapped_column(TZDateTime, nullable=True)
    next_follow_up_at: Mapped[Optional[datetime]] = mapped_column(TZDateTime, nullable=True)
    lead_score: Mapped[int] = mapped_column(default=0)
    lead_score_factors: Mapped[str] = mapped_column(Text, default="{}")
    notes: Mapped[str] = mapped_column(Text, default="")

    contacts: Mapped[list["Contact"]] = relationship(back_populates="customer", cascade="all,delete-orphan")


class Contact(Base, OrgMixin, TimestampMixin):
    __tablename__ = "contacts"

    id: Mapped[int] = mapped_column(primary_key=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"), index=True)
    name: Mapped[str] = mapped_column(String(120), default="")
    email: Mapped[str] = mapped_column(String(255), default="")
    phone: Mapped[str] = mapped_column(String(60), default="")
    whatsapp: Mapped[str] = mapped_column(String(60), default="")
    position: Mapped[str] = mapped_column(String(120), default="")
    is_primary: Mapped[bool] = mapped_column(default=False)

    customer: Mapped[Customer] = relationship(back_populates="contacts")
