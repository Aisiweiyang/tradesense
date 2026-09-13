"""Match result model (two-stage retrieval output with explanations)."""
from __future__ import annotations

from typing import Optional

from sqlalchemy import Boolean, Float, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, OrgMixin, TZDateTime, TimestampMixin


class MatchResult(Base, OrgMixin, TimestampMixin):
    __tablename__ = "match_results"

    id: Mapped[int] = mapped_column(primary_key=True)
    inquiry_id: Mapped[int] = mapped_column(ForeignKey("inquiries.id"), index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), index=True)
    batch_no: Mapped[str] = mapped_column(String(40), default="", index=True)
    total_score: Mapped[float] = mapped_column(Float, default=0.0)
    scores_json: Mapped[str] = mapped_column(Text, default="{}")  # per-dimension {score, max, detail}
    met_json: Mapped[str] = mapped_column(Text, default="[]")
    unmet_json: Mapped[str] = mapped_column(Text, default="[]")
    excluded: Mapped[bool] = mapped_column(Boolean, default=False)
    exclude_reason: Mapped[str] = mapped_column(Text, default="")
    is_alternative: Mapped[bool] = mapped_column(Boolean, default=False)
    rank: Mapped[int] = mapped_column(default=0)
    data_snapshot_json: Mapped[str] = mapped_column(Text, default="{}")  # data source + freshness at match time
