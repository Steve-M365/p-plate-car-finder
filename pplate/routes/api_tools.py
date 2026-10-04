"""JSON API for the tool endpoints: recommendations, listing fetch, rules, logs."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from pplate.config import get_settings
from pplate.db import get_db
from pplate.models import FetchRun, RecommendationSource, SearchRun
from pplate.schemas import (
    FetchRequest,
    ImportUrlRequest,
    RecommendationRequest,
    RunSummaryOut,
    SaveListingRequest,
)
from pplate.services import p_plate_compliance
from pplate.services.external_http import ExternalClient
from pplate.services.listing_fetch import fetch_listings, save_captured_listing
from pplate.services.recommendation_search import run_recommendation_search

router = APIRouter(prefix="/api", tags=["tools"])


@router.get("/rules")
def get_rules():
    """The Victorian P-plate rules this app implements, plus source URLs."""
    settings = get_settings()
    return {
        "summary": p_plate_compliance.RULES_SUMMARY,
        "thresholds": {
            "power_to_mass_limit_kw_per_tonne": settings.pplate_power_to_mass_limit,
            "borderline_lower_kw_per_tonne": settings.pplate_borderline_lower,
            "absolute_power_limit_kw": settings.pplate_absolute_power_limit_kw,
        },
        "sources": p_plate_compliance.RULES_SOURCE_URLS,
        "probationary_vehicle_database": p_plate_compliance.PPV_DATABASE_URL,
        "disclaimer": (
            "Guidance only. Legal compliance is the driver's responsibility. Always "
            "confirm the exact make/model/variant on the official Victorian "
            "probationary vehicle database or with VicRoads before buying or driving."
        ),
    }


@router.post("/tools/recommendations", response_model=RunSummaryOut)
def run_recommendations(payload: RecommendationRequest, db: Session = Depends(get_db)):
    result = run_recommendation_search(
        db,
        queries=payload.queries,
        seed_recommended_cars=payload.seed_recommended_cars,
    )
    return RunSummaryOut(
        provider=result.get("provider"),
        fetched=result.get("web_results", 0),
        inserted=result.get("recommended_inserted", 0),
        updated=result.get("recommended_updated", 0),
        status="ok",
        message=result.get("message"),
    )


@router.post("/tools/fetch-listings", response_model=RunSummaryOut)
def run_fetch(payload: FetchRequest, db: Session = Depends(get_db)):
    result = fetch_listings(db, provider=payload.provider, query=payload.query, limit=payload.limit)
    return RunSummaryOut(
        run_id=result.get("run_id"),
        provider=result.get("provider"),
        query=result.get("query"),
        fetched=result.get("fetched", 0),
        inserted=result.get("inserted", 0),
        updated=result.get("updated", 0),
        skipped=result.get("skipped", 0),
        status=result.get("status", "ok"),
        message=result.get("message"),
        compliance=result.get("compliance"),
    )


@router.post("/tools/save-listing")
def save_listing(payload: SaveListingRequest, db: Session = Depends(get_db)):
    """Save a single listing captured by the user (bookmarklet / extension / paste).

    The user supplies the page they can already see, so nothing is crawled and
    no site protection is circumvented.
    """
    overrides = payload.model_dump(
        exclude={"url", "title", "html", "text", "source"}, exclude_none=True
    )
    return save_captured_listing(
        db,
        url=payload.url,
        title=payload.title,
        html=payload.html,
        text=payload.text,
        overrides=overrides,
        source=payload.source,
    )


@router.post("/tools/import-url")
def import_url(payload: ImportUrlRequest, db: Session = Depends(get_db)):
    """Fetch ONE listing URL the user explicitly chose, robots.txt permitting."""
    settings = get_settings()
    client = ExternalClient(db, rate_limit_seconds=settings.listing_rate_limit_seconds)
    result = client.get(payload.url, provider="import-url")
    if result.allowed_by_robots is False:
        return {
            "saved": False,
            "url": payload.url,
            "message": (
                "robots.txt disallows automated fetching of that URL. "
                "Use the 'Save this listing' bookmarklet instead."
            ),
        }
    if not result.text:
        return {
            "saved": False,
            "url": payload.url,
            "message": f"Fetch failed: {result.error or result.status_code}.",
        }
    return save_captured_listing(
        db, url=payload.url, html=result.text, overrides=payload.overrides or {}
    )


@router.get("/recommendation-sources")
def list_sources(db: Session = Depends(get_db), limit: int = 100):
    rows = db.scalars(
        select(RecommendationSource).order_by(RecommendationSource.fetched_at.desc()).limit(limit)
    ).all()
    return [
        {
            "id": r.id,
            "url": r.url,
            "title": r.title,
            "summary": r.summary,
            "category": r.category,
            "fetched_at": r.fetched_at,
        }
        for r in rows
    ]


@router.get("/search-runs")
def list_search_runs(db: Session = Depends(get_db), limit: int = 50):
    rows = db.scalars(select(SearchRun).order_by(SearchRun.run_at.desc()).limit(limit)).all()
    return [
        {
            "id": r.id,
            "query": r.query,
            "provider": r.provider,
            "result_count": r.result_count,
            "error": r.error,
            "run_at": r.run_at,
        }
        for r in rows
    ]


@router.get("/fetch-runs")
def list_fetch_runs(db: Session = Depends(get_db), limit: int = 50):
    rows = db.scalars(select(FetchRun).order_by(FetchRun.run_at.desc()).limit(limit)).all()
    return [
        {
            "id": r.id,
            "provider": r.provider,
            "query": r.query,
            "fetched": r.fetched_count,
            "inserted": r.inserted_count,
            "updated": r.updated_count,
            "skipped": r.skipped_count,
            "status": r.status,
            "error": r.error,
            "run_at": r.run_at,
        }
        for r in rows
    ]
