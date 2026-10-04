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
