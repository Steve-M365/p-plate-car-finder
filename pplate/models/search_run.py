"""Log of recommendation web-search runs."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from pplate.db.base import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class SearchRun(Base):
    __tablename__ = "search_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    query: Mapped[str] = mapped_column(String(400), nullable=False)
    provider: Mapped[str | None] = mapped_column(String(60), nullable=True)
    result_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    run_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False, index=True
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<SearchRun {self.id} {self.query[:40]!r} -> {self.result_count}>"
