"""Shipment & document verification models (Phase 4 — 单证工作台)."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, OrgMixin, TZDateTime, TimestampMixin

SHIPMENT_STATUSES = [
    "preparing", "docs_making", "ready_to_ship", "shipped",
    "blocked", "settled", "cancelled",
]
TRANSPORT_MODES = ["sea", "air", "rail", "express"]
DOC_TYPES = [
    "invoice", "packing_list", "bill_of_lading", "customs_declaration",
    "letter_of_credit", "origin_certificate", "other",
]
DOC_STATUSES = ["uploaded", "extracting", "extracted", "needs_manual", "verified", "failed"]
ISSUE_SEVERITIES = ["high", "medium", "low"]
ISSUE_TYPES = ["conflict", "missing", "low_confidence"]
ISSUE_STATUSES = ["open", "adopted", "manual_fixed", "ignored", "resolved"]

# built-in deterministic rules
RULE_CODES = [
    "amount_vs_lc",          # 发票金额 vs 信用证金额
    "lc_consignee",          # 提单收货人 vs 信用证要求（TO ORDER OF ...）
    "gross_weight_match",    # 装箱单毛重 vs 提单毛重（允差）
    "hs_code_match",         # 发票 HS Code vs 报关单
    "goods_description",     # 品名归一化后一致性
    "missing_docs",          # 必备单证缺失 + 截单倒计时
]

DEFAULT_REQUIRED_DOCS = ["invoice", "packing_list", "bill_of_lading"]


class Shipment(Base, OrgMixin, TimestampMixin):
    __tablename__ = "shipments"

    id: Mapped[int] = mapped_column(primary_key=True)
    shipment_no: Mapped[str] = mapped_column(String(40), index=True)
    inquiry_id: Mapped[Optional[int]] = mapped_column(ForeignKey("inquiries.id"), nullable=True)
    quote_id: Mapped[Optional[int]] = mapped_column(ForeignKey("quotes.id"), nullable=True)
    customer_id: Mapped[Optional[int]] = mapped_column(ForeignKey("customers.id"), nullable=True, index=True)
    order_no: Mapped[str] = mapped_column(String(80), default="")
    transport_mode: Mapped[str] = mapped_column(String(20), default="sea")
    port_of_loading: Mapped[str] = mapped_column(String(100), default="")
    port_of_discharge: Mapped[str] = mapped_column(String(100), default="")
    incoterm: Mapped[str] = mapped_column(String(10), default="FOB")
    etd: Mapped[Optional[datetime]] = mapped_column(TZDateTime, nullable=True)
    cutoff_at: Mapped[Optional[datetime]] = mapped_column(TZDateTime, nullable=True)
    owner_user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="docs_making", index=True)
    required_docs_json: Mapped[str] = mapped_column(Text, default='["invoice", "packing_list", "bill_of_lading"]')
    notes: Mapped[str] = mapped_column(Text, default="")

    documents: Mapped[list["Document"]] = relationship(
        back_populates="shipment", cascade="all,delete-orphan", order_by="Document.id")
    issues: Mapped[list["ShipmentIssue"]] = relationship(
        back_populates="shipment", cascade="all,delete-orphan", order_by="ShipmentIssue.id")


class Document(Base, OrgMixin, TimestampMixin):
    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(primary_key=True)
    shipment_id: Mapped[int] = mapped_column(ForeignKey("shipments.id"), index=True)
    doc_type: Mapped[str] = mapped_column(String(40), index=True)
    version: Mapped[int] = mapped_column(default=1)
    file_path: Mapped[str] = mapped_column(String(500), default="")
    original_filename: Mapped[str] = mapped_column(String(300), default="")
    status: Mapped[str] = mapped_column(String(20), default="uploaded", index=True)
    extract_error: Mapped[str] = mapped_column(Text, default="")
    pages: Mapped[int] = mapped_column(default=0)
    has_text_layer: Mapped[bool] = mapped_column(Boolean, default=True)
    uploaded_by_user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)

    shipment: Mapped[Shipment] = relationship(back_populates="documents")
    fields: Mapped[list["DocumentField"]] = relationship(
        back_populates="document", cascade="all,delete-orphan")


class DocumentField(Base, OrgMixin, TimestampMixin):
    __tablename__ = "document_fields"

    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id"), index=True)
    field_name: Mapped[str] = mapped_column(String(60), index=True)
    value: Mapped[str] = mapped_column(Text, default="")
    confidence: Mapped[float] = mapped_column(Float, default=0.9)
    evidence_page: Mapped[Optional[int]] = mapped_column(nullable=True)  # 1-based
    evidence_text: Mapped[str] = mapped_column(Text, default="")
    source: Mapped[str] = mapped_column(String(20), default="extracted")  # extracted/manual
    modified_by_user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)

    document: Mapped[Document] = relationship(back_populates="fields")


class ShipmentIssue(Base, OrgMixin, TimestampMixin):
    __tablename__ = "shipment_issues"

    id: Mapped[int] = mapped_column(primary_key=True)
    shipment_id: Mapped[int] = mapped_column(ForeignKey("shipments.id"), index=True)
    severity: Mapped[str] = mapped_column(String(10), default="medium", index=True)
    issue_type: Mapped[str] = mapped_column(String(20), default="conflict")
    rule_code: Mapped[str] = mapped_column(String(40), default="", index=True)
    title: Mapped[str] = mapped_column(String(300), default="")
    expected_value: Mapped[str] = mapped_column(Text, default="")
    actual_value: Mapped[str] = mapped_column(Text, default="")
    evidence_json: Mapped[str] = mapped_column(Text, default="[]")  # [{doc_id, doc_type, field, page, text}]
    status: Mapped[str] = mapped_column(String(20), default="open", index=True)
    assigned_to_user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)
    handler_user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)
    resolution_note: Mapped[str] = mapped_column(Text, default="")
    resolved_at: Mapped[Optional[datetime]] = mapped_column(TZDateTime, nullable=True)

    shipment: Mapped[Shipment] = relationship(back_populates="issues")


class DocRuleConfig(Base, OrgMixin, TimestampMixin):
    """Customer-overridable enablement/params for the built-in rule set."""
    __tablename__ = "doc_rule_configs"

    id: Mapped[int] = mapped_column(primary_key=True)
    customer_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("customers.id"), nullable=True, index=True)  # NULL = 全局默认
    rule_code: Mapped[str] = mapped_column(String(40), index=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    params_json: Mapped[str] = mapped_column(Text, default="{}")  # e.g. {"weight_tolerance_pct": 0.5}
    updated_by_user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)
