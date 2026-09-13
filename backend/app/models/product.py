"""Product, supplier and certification models."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, OrgMixin, TZDateTime, TimestampMixin


class Product(Base, OrgMixin, TimestampMixin):
    __tablename__ = "products"

    id: Mapped[int] = mapped_column(primary_key=True)
    sku: Mapped[str] = mapped_column(String(80), index=True)
    name_zh: Mapped[str] = mapped_column(String(300), default="")
    name_en: Mapped[str] = mapped_column(String(300), default="")
    category: Mapped[str] = mapped_column(String(80), default="", index=True)  # canonical concept e.g. insulated_bottle
    description: Mapped[str] = mapped_column(Text, default="")
    material: Mapped[str] = mapped_column(String(200), default="")  # normalized, comma separated
    spec: Mapped[str] = mapped_column(String(300), default="")  # capacity/size spec
    size: Mapped[str] = mapped_column(String(200), default="")
    color: Mapped[str] = mapped_column(String(300), default="")  # available colors, comma separated
    packaging: Mapped[str] = mapped_column(String(200), default="")
    moq: Mapped[int] = mapped_column(default=1)
    price_tiers_json: Mapped[str] = mapped_column(Text, default="[]")  # [{min_qty, unit_price}]
    currency: Mapped[str] = mapped_column(String(10), default="USD")
    stock_status: Mapped[str] = mapped_column(String(30), default="made_to_order")  # in_stock/made_to_order/low
    lead_time_days: Mapped[int] = mapped_column(default=30)
    customization: Mapped[str] = mapped_column(String(300), default="")  # logo/printing/odm/oem
    certifications_json: Mapped[str] = mapped_column(Text, default="[]")  # ["FDA","LFGB",...]
    supplier_id: Mapped[Optional[int]] = mapped_column(ForeignKey("suppliers.id"), nullable=True)
    image_url: Mapped[str] = mapped_column(String(500), default="")
    keywords: Mapped[str] = mapped_column(Text, default="")  # extra search keywords incl. zh/en synonyms
    data_source: Mapped[str] = mapped_column(String(100), default="manual")
    markets: Mapped[str] = mapped_column(String(300), default="")  # allowed/known markets; empty = unrestricted
    unit_weight_kg: Mapped[Optional[float]] = mapped_column(default=None)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_verified_at: Mapped[Optional[datetime]] = mapped_column(TZDateTime, nullable=True)

    variants: Mapped[list["ProductVariant"]] = relationship(back_populates="product", cascade="all,delete-orphan")


class ProductVariant(Base, OrgMixin, TimestampMixin):
    __tablename__ = "product_variants"

    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), index=True)
    sku: Mapped[str] = mapped_column(String(80), default="")
    attributes_json: Mapped[str] = mapped_column(Text, default="{}")
    price_delta: Mapped[float] = mapped_column(default=0.0)
    moq: Mapped[int] = mapped_column(default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    product: Mapped[Product] = relationship(back_populates="variants")


class Supplier(Base, OrgMixin, TimestampMixin):
    __tablename__ = "suppliers"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    region: Mapped[str] = mapped_column(String(100), default="")
    contact_name: Mapped[str] = mapped_column(String(120), default="")
    phone: Mapped[str] = mapped_column(String(60), default="")
    email: Mapped[str] = mapped_column(String(255), default="")
    categories_json: Mapped[str] = mapped_column(Text, default="[]")
    reliability_score: Mapped[float] = mapped_column(default=0.8)  # 0-1
    notes: Mapped[str] = mapped_column(Text, default="")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class SupplierProduct(Base, OrgMixin, TimestampMixin):
    __tablename__ = "supplier_products"

    id: Mapped[int] = mapped_column(primary_key=True)
    supplier_id: Mapped[int] = mapped_column(ForeignKey("suppliers.id"), index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), index=True)
    supplier_sku: Mapped[str] = mapped_column(String(80), default="")
    cost_price: Mapped[float] = mapped_column(default=0.0)
    currency: Mapped[str] = mapped_column(String(10), default="CNY")
    moq: Mapped[int] = mapped_column(default=0)
    lead_time_days: Mapped[int] = mapped_column(default=30)
    last_quoted_at: Mapped[Optional[datetime]] = mapped_column(TZDateTime, nullable=True)


class Certification(Base, OrgMixin, TimestampMixin):
    __tablename__ = "certifications"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(50))  # FDA / LFGB / CE ...
    name: Mapped[str] = mapped_column(String(200), default="")
    region: Mapped[str] = mapped_column(String(100), default="")
    description: Mapped[str] = mapped_column(Text, default="")
