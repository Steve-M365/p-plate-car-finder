"""Schemas for tool endpoints (recommendation search, listing fetch)."""

from __future__ import annotations

from pydantic import BaseModel, Field


class RecommendationRequest(BaseModel):
    """Optionally override the built-in search queries."""

    queries: list[str] | None = Field(
        default=None,
        description="Extra/override web-search queries. Defaults to built-in queries.",
    )
    seed_recommended_cars: bool = Field(
        default=True,
        description="Insert/refresh the curated recommended first-car models.",
    )


class FetchRequest(BaseModel):
    provider: str | None = Field(
        default=None,
        description="mock | csv | carsales | auto. Defaults to the configured provider.",
    )
    query: str | None = Field(default=None, description="Optional model search, e.g. 'Toyota Corolla'.")
    limit: int = Field(default=25, ge=1, le=200)


class RunSummaryOut(BaseModel):
    run_id: int | None = None
    provider: str | None = None
    query: str | None = None
    fetched: int = 0
    inserted: int = 0
    updated: int = 0
    skipped: int = 0
    status: str = "ok"
    message: str | None = None
    compliance: dict[str, int] | None = None


class SaveListingRequest(BaseModel):
    """A single listing captured by the user (bookmarklet / extension / paste).

    ``html`` should contain the page's JSON-LD ``<script>`` blocks if available;
    ``text`` is the visible text. Any explicit field values override the parser.
    """

    url: str | None = None
    title: str | None = None
    html: str | None = None
    text: str | None = None
    source: str = "capture"

    make: str | None = None
    model: str | None = None
    variant: str | None = None
    year: int | None = None
    engine_size_cc: int | None = None
    power_kw: float | None = None
    weight_kg: int | None = None
    body_type: str | None = None
    fuel_type: str | None = None
    transmission: str | None = None
    price_aud: int | None = None
    odometer_km: int | None = None
    location: str | None = None
    safety_rating_stars: float | None = None
    safety_rating_year: int | None = None


class ImportUrlRequest(BaseModel):
    """Fetch a single listing URL the user explicitly requested (robots-permitting)."""

    url: str
    overrides: dict | None = None
