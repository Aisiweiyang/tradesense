"""Quote, quote item and price rule models."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, OrgMixin, TZDateTime, TimestampMixin

QUOTE_STATUSES = ["draft", "pending_approval", "approved", "rejected", "superseded", "sent_manually"]


class Quote(Base, OrgMixin, TimestampMixin):
    __tablename__ = "quotes"

    id: Mapped[int] = mapped_column(primary_key=True)
    inquiry_id: Mapped[int] = mapped_column(ForeignKey("inquiries.id"), index=True)
    product_id: Mapped[Optional[int]] = mapped_column(ForeignKey("products.id"), nullable=True)
    version: Mapped[int] = mapped_column(default=1)
    status: Mapped[str] = mapped_column(String(30), default="draft")
    incoterm: Mapped[str] = mapped_column(String(10), default="FOB")
    currency: Mapped[str] = mapped_column(String(10), default="USD")
    quantity: Mapped[int] = mapped_column(default=0)
    unit_cost: Mapped[float] = mapped_column(default=0.0)  # internal cost, never shown to customer
    unit_price: Mapped[float] = mapped_column(default=0.0)  # suggested quote
    customer_price: Mapped[float] = mapped_column(default=0.0)  # price actually quoted to customer (human editable)
    total_amount: Mapped[float] = mapped_column(default=0.0)
    margin_rate: Mapped[float] = mapped_column(default=0.0)
    breakdown_json: Mapped[str] = mapped_column(Text, default="{}")  # itemized calculation with sources
    assumptions_json: Mapped[str] = mapped_column(Text, default="[]")
    missing_json: Mapped[str] = mapped_column(Text, default="[]")
    risks_json: Mapped[str] = mapped_column(Text, default="[]")
    exchange_rate_json: Mapped[str] = mapped_column(Text, default="{}")
    valid_until: Mapped[Optional[datetime]] = mapped_column(TZDateTime, nullable=True)
    is_formal: Mapped[bool] = mapped_column(Boolean, default=False)  # only after human approval
    approved_by_user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)
    approved_at: Mapped[Optional[datetime]] = mapped_column(TZDateTime, nullable=True)
    created_by_user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)
    notes: Mapped[str] = mapped_column(Text, default="")

    items: Mapped[list["QuoteItem"]] = relationship(back_populates="quote", cascade="all,delete-orphan")


class QuoteItem(Base, OrgMixin, TimestampMixin):
    __tablename__ = "quote_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    quote_id: Mapped[int] = mapped_column(ForeignKey("quotes.id"), index=True)
    product_id: Mapped[Optional[int]] = mapped_column(ForeignKey("products.id"), nullable=True)
    description: Mapped[str] = mapped_column(String(300), default="")
    qty: Mapped[int] = mapped_column(default=0)
    unit_cost: Mapped[float] = mapped_column(default=0.0)
    other_costs_json: Mapped[str] = mapped_column(Text, default="[]")
    unit_price: Mapped[float] = mapped_column(default=0.0)
    subtotal: Mapped[float] = mapped_column(default=0.0)
    margin_rate: Mapped[float] = mapped_column(default=0.0)
    notes: Mapped[str] = mapped_column(Text, default="")

    quote: Mapped[Quote] = relationship(back_populates="items")


class PriceRule(Base, OrgMixin, TimestampMixin):
    __tablename__ = "price_rules"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    rule_type: Mapped[str] = mapped_column(String(50))  # margin / freight_zone / insurance / duty / packaging / printing / mold
    config_json: Mapped[str] = mapped_column(Text, default="{}")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


SHEET_STATUSES = ["draft", "pending_approval", "approved", "rejected", "superseded"]


class QuoteSheet(Base, OrgMixin, TimestampMixin):
    """Merged quotation for one inquiry: multiple quote lines, human approved."""
    __tablename__ = "quote_sheets"

    id: Mapped[int] = mapped_column(primary_key=True)
    inquiry_id: Mapped[int] = mapped_column(ForeignKey("inquiries.id"), index=True)
    sheet_no: Mapped[str] = mapped_column(String(40), default="")
    version: Mapped[int] = mapped_column(default=1)
    status: Mapped[str] = mapped_column(String(30), default="draft", index=True)
    currency: Mapped[str] = mapped_column(String(10), default="USD")
    incoterm: Mapped[str] = mapped_column(String(10), default="FOB")
    lines_json: Mapped[str] = mapped_column(Text, default="[]")
    # line: {quote_id, product_id, sku, name_en, qty, unit_price, subtotal}
    subtotal: Mapped[float] = mapped_column(default=0.0)
    margin_rate: Mapped[float] = mapped_column(default=0.0)
    target_price_json: Mapped[str] = mapped_column(Text, default="{}")
    notes: Mapped[str] = mapped_column(Text, default="")
    is_formal: Mapped[bool] = mapped_column(Boolean, default=False)
    approved_by_user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)
    approved_at: Mapped[Optional[datetime]] = mapped_column(TZDateTime, nullable=True)
    created_by_user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)
