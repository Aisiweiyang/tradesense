"""Import preview token storage (DB-backed, replaces in-process cache)."""
from __future__ import annotations

from datetime import timedelta

from sqlalchemy import select

from .base import Base, OrgMixin, TZDateTime, utcnow
from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

PREVIEW_TTL_MINUTES = 30


class ImportPreview(Base, OrgMixin):
    __tablename__ = "import_previews"

    id: Mapped[int] = mapped_column(primary_key=True)
    token: Mapped[str] = mapped_column(String(40), index=True)
    payload_json: Mapped[str] = mapped_column(Text)
    created_at = mapped_column(TZDateTime, default=utcnow)
    expires_at = mapped_column(TZDateTime, default=lambda: utcnow() + timedelta(minutes=PREVIEW_TTL_MINUTES))


def purge_expired(db) -> int:
    """Lazy cleanup: delete expired preview rows. Returns count removed."""
    rows = db.scalars(select(ImportPreview).where(ImportPreview.expires_at < utcnow())).all()
    for r in rows:
        db.delete(r)
    return len(rows)
