"""Pydantic schemas for cars (request/response models)."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from pplate.models.enums import CarSource, ComplianceStatus


class CarBase(BaseModel):
    make: str = Field(..., min_length=1, max_length=80)
    model: str = Field(..., min_length=1, max_length=120)
    variant: str | None = Field(default=None, max_length=120)
    year: int | None = Field(default=None, ge=1900, le=2100)

    engine_size_cc: int | None = Field(default=None, ge=0, le=20000)
    power_kw: float | None = Field(default=None, ge=0, le=2000)
    weight_kg: int | None = Field(default=None, ge=0, le=10000)

    body_type: str | None = Field(default=None, max_length=40)
    fuel_type: str | None = Field(default=None, max_length=40)
    transmission: str | None = Field(default=None, max_length=40)
    cylinders: int | None = Field(default=None, ge=0, le=16)

    price_aud: int | None = Field(default=None, ge=0)
    odometer_km: int | None = Field(default=None, ge=0)
    location: str | None = Field(default=None, max_length=120)

    safety_rating_stars: float | None = Field(default=None, ge=0, le=5)
    safety_rating_year: int | None = Field(default=None, ge=1990, le=2100)

    listing_url: str | None = Field(default=None, max_length=500)
    source: CarSource = CarSource.MANUAL
    external_id: str | None = Field(default=None, max_length=200)

    listed_high_performance: bool = False
    modified: bool = False
    modification_notes: str | None = None

    recommended: bool = False
    notes: str | None = None

    @field_validator(
        "body_type", "fuel_type", "transmission", "location", "variant", mode="before"
    )
    @classmethod
    def _blank_to_none(cls, v: object) -> object:
        if isinstance(v, str) and not v.strip():
            return None
        return v


class CarCreate(CarBase):
    pass


class CarUpdate(BaseModel):
    """All fields optional - only provided fields are applied (PATCH/PUT)."""

    make: str | None = Field(default=None, min_length=1, max_length=80)
    model: str | None = Field(default=None, min_length=1, max_length=120)
    variant: str | None = Field(default=None, max_length=120)
    year: int | None = Field(default=None, ge=1900, le=2100)

    engine_size_cc: int | None = Field(default=None, ge=0, le=20000)
    power_kw: float | None = Field(default=None, ge=0, le=2000)
    weight_kg: int | None = Field(default=None, ge=0, le=10000)

    body_type: str | None = Field(default=None, max_length=40)
    fuel_type: str | None = Field(default=None, max_length=40)
    transmission: str | None = Field(default=None, max_length=40)
    cylinders: int | None = Field(default=None, ge=0, le=16)

    price_aud: int | None = Field(default=None, ge=0)
    odometer_km: int | None = Field(default=None, ge=0)
    location: str | None = Field(default=None, max_length=120)

    safety_rating_stars: float | None = Field(default=None, ge=0, le=5)
    safety_rating_year: int | None = Field(default=None, ge=1990, le=2100)

    listing_url: str | None = Field(default=None, max_length=500)
    listed_high_performance: bool | None = None
    modified: bool | None = None
    modification_notes: str | None = None
    recommended: bool | None = None
    notes: str | None = None


class CarOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    make: str
    model: str
    variant: str | None
    year: int | None

    engine_size_cc: int | None
    power_kw: float | None
    weight_kg: int | None
    power_to_weight: float | None

    body_type: str | None
    fuel_type: str | None
    transmission: str | None
    cylinders: int | None

    price_aud: int | None
    odometer_km: int | None
    location: str | None

    safety_rating_stars: float | None
    safety_rating_year: int | None

    listing_url: str | None
    source: CarSource
    external_id: str | None

    p_plate_compliant: ComplianceStatus
    p_plate_reason: str | None
    listed_high_performance: bool
    modified: bool
    modification_notes: str | None

    recommended: bool
    notes: str | None

    created_at: datetime
    updated_at: datetime


class CarFilter(BaseModel):
    """Query filters for listing / searching cars."""

    q: str | None = None
    min_price: int | None = None
    max_price: int | None = None
    body_type: str | None = None
    fuel_type: str | None = None
    transmission: str | None = None
    min_safety: float | None = None
    compliance: ComplianceStatus | None = None
    recommended: bool | None = None
    source: str | None = None
    sort: str = "price_asc"
    limit: int = 500
    offset: int = 0


class StatsOut(BaseModel):
    total: int
    compliant: int
    non_compliant: int
    unknown: int
    recommended: int
