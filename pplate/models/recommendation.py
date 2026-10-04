"""Sources of first-car recommendations (web search results, guides, etc.)."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from pplate.db.base import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class RecommendationSource(Base):
    __tablename__ = "recommendation_sources"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    url: Mapped[str] = mapped_column(String(500), nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Which knowledge area this source supports: "rules" or "first_car".
    category: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    query: Mapped[str | None] = mapped_column(String(300), nullable=True)
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<RecommendationSource {self.id} {self.title[:40]!r}>"
