"""Organization and user models."""
from __future__ import annotations

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, OrgMixin, TZDateTime, TimestampMixin


class Organization(Base, TimestampMixin):
    __tablename__ = "organizations"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    default_locale: Mapped[str] = mapped_column(String(10), default="zh-CN")
    default_currency: Mapped[str] = mapped_column(String(10), default="USD")
    settings_json: Mapped[str] = mapped_column(Text, default="{}")  # scoring weights, freight, margins


class Role(Base, TimestampMixin):
    __tablename__ = "roles"

    id: Mapped[int] = mapped_column(primary_key=True)
    org_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), index=True)
    code: Mapped[str] = mapped_column(String(50))  # owner / manager / member / viewer
    name: Mapped[str] = mapped_column(String(100))


class User(Base, OrgMixin, TimestampMixin):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(100), default="")
    password_hash: Mapped[str] = mapped_column(String(300))
    role: Mapped[str] = mapped_column(String(30), default="owner")  # owner/manager/member/viewer
    locale: Mapped[str] = mapped_column(String(10), default="zh-CN")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
