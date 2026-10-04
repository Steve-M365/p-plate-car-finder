"""The Car model - the central record of the application."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Enum as SAEnum, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from pplate.db.base import Base
from pplate.models.enums import CarSource, ComplianceStatus


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Car(Base):
    __tablename__ = "cars"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    make: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    model: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    variant: Mapped[str | None] = mapped_column(String(120), nullable=True)
    year: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)

    engine_size_cc: Mapped[int | None] = mapped_column(Integer, nullable=True)
    power_kw: Mapped[float | None] = mapped_column(Float, nullable=True)
    weight_kg: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Stored derived value: power (kW) / mass (tonnes). Recalculated on write.
    power_to_weight: Mapped[float | None] = mapped_column(Float, nullable=True)

    body_type: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    fuel_type: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    transmission: Mapped[str | None] = mapped_column(String(40), nullable=True)
    cylinders: Mapped[int | None] = mapped_column(Integer, nullable=True)

    price_aud: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    odometer_km: Mapped[int | None] = mapped_column(Integer, nullable=True)
    location: Mapped[str | None] = mapped_column(String(120), nullable=True)

    safety_rating_stars: Mapped[float | None] = mapped_column(Float, nullable=True)
    safety_rating_year: Mapped[int | None] = mapped_column(Integer, nullable=True)

    listing_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    source: Mapped[str] = mapped_column(
        SAEnum(CarSource, native_enum=False, length=24),
        default=CarSource.MANUAL,
        nullable=False,
    )
    external_id: Mapped[str | None] = mapped_column(String(200), nullable=True, index=True)

    # --- Victorian P-plate evaluation -------------------------------------
    p_plate_compliant: Mapped[str] = mapped_column(
        SAEnum(ComplianceStatus, native_enum=False, length=24),
        default=ComplianceStatus.UNKNOWN,
        nullable=False,
        index=True,
    )
    p_plate_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    # True when the model/variant appears on the regulator's high-performance list.
    listed_high_performance: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # Engine modified to increase performance (only factory mods are allowed).
    modified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    modification_notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # --- Curated fields ----------------------------------------------------
    recommended: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"<Car {self.id} {self.year} {self.make} {self.model}>"
