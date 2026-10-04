"""Server-rendered UI (Jinja2 templates) for the local app."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm import Session

from pplate.config import get_settings
from pplate.db import get_db
from pplate.models import FetchRun, RecommendationSource, SearchRun
from pplate.models.enums import BODY_TYPES, FUEL_TYPES, TRANSMISSIONS, CarSource, ComplianceStatus
from pplate.schemas import CarCreate, CarFilter, CarUpdate
from pplate.services import car_service
from pplate.services.listing_fetch import fetch_listings
from pplate.services.p_plate_compliance import (
    PPV_DATABASE_URL,
    RULES_SOURCE_URLS,
    RULES_SUMMARY,
)
from pplate.services.recommendation_search import run_recommendation_search

router = APIRouter(tags=["ui"])
settings = get_settings()

TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
templates.env.globals.update(
    app_name=settings.app_name,
    ppv_database_url=PPV_DATABASE_URL,
    rules_sources=RULES_SOURCE_URLS,
    rules_summary=RULES_SUMMARY,
)


# --- helpers ---------------------------------------------------------------
def _to_int(value: str | None) -> int | None:
    if value in (None, "", "None"):
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _to_float(value: str | None) -> float | None:
    if value in (None, "", "None"):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _form_to_car_data(form) -> dict:
    return {
        "make": (form.get("make") or "").strip(),
        "model": (form.get("model") or "").strip(),
        "variant": (form.get("variant") or "").strip() or None,
        "year": _to_int(form.get("year")),
        "engine_size_cc": _to_int(form.get("engine_size_cc")),
        "power_kw": _to_float(form.get("power_kw")),
        "weight_kg": _to_int(form.get("weight_kg")),
        "body_type": (form.get("body_type") or "").strip() or None,
        "fuel_type": (form.get("fuel_type") or "").strip() or None,
        "transmission": (form.get("transmission") or "").strip() or None,
        "price_aud": _to_int(form.get("price_aud")),
        "odometer_km": _to_int(form.get("odometer_km")),
        "location": (form.get("location") or "").strip() or None,
        "safety_rating_stars": _to_float(form.get("safety_rating_stars")),
        "safety_rating_year": _to_int(form.get("safety_rating_year")),
        "listing_url": (form.get("listing_url") or "").strip() or None,
        "recommended": form.get("recommended") == "on",
        "modified": form.get("modified") == "on",
        "modification_notes": (form.get("modification_notes") or "").strip() or None,
        "listed_high_performance": form.get("listed_high_performance") == "on",
        "notes": (form.get("notes") or "").strip() or None,
    }


def _filters_from_query(request: Request) -> CarFilter:
    qp = request.query_params

    def num(name, cast=int):
        v = qp.get(name)
        if v in (None, "", "None"):
            return None
        try:
            return cast(v)
        except (TypeError, ValueError):
            return None

    comp = qp.get("compliance") or None
    compliance = None
    if comp in {c.value for c in ComplianceStatus}:
        compliance = ComplianceStatus(comp)
    recommended = qp.get("recommended")
    return CarFilter(
        q=qp.get("q") or None,
        min_price=num("min_price"),
        max_price=num("max_price"),
        body_type=qp.get("body_type") or None,
        fuel_type=qp.get("fuel_type") or None,
        transmission=qp.get("transmission") or None,
        min_safety=num("min_safety", float),
        compliance=compliance,
        recommended=(True if recommended == "true" else (False if recommended == "false" else None)),
        source=qp.get("source") or None,
        sort=qp.get("sort") or "price_asc",
        limit=num("limit") or 500,
    )


# --- pages -----------------------------------------------------------------
@router.get("/")
def dashboard(request: Request, db: Session = Depends(get_db)):
    filters = _filters_from_query(request)
    cars = car_service.get_cars(db, filters)
    stats = car_service.stats(db)
    sources = db.scalars(
        select(RecommendationSource).order_by(RecommendationSource.fetched_at.desc()).limit(8)
    ).all()
    last_search = db.scalars(select(SearchRun).order_by(SearchRun.run_at.desc()).limit(1)).first()
    last_fetch = db.scalars(select(FetchRun).order_by(FetchRun.run_at.desc()).limit(1)).first()
    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {
            "active": "dashboard",
            "cars": cars,
            "stats": stats,
            "filters": filters,
            "sources": sources,
            "last_search": last_search,
            "last_fetch": last_fetch,
            "msg": request.query_params.get("msg"),
            "body_types": BODY_TYPES,
            "fuel_types": FUEL_TYPES,
            "transmissions": TRANSMISSIONS,
            "sources_enum": [s.value for s in CarSource],
            "compliance_values": [c.value for c in ComplianceStatus],
        },
    )


@router.get("/cars/new")
def new_car_form(request: Request):
    return templates.TemplateResponse(
        request,
        "car_form.html",
        {
            "active": "new",
            "car": None,
            "action": "/cars/new",
            "body_types": BODY_TYPES,
            "fuel_types": FUEL_TYPES,
            "transmissions": TRANSMISSIONS,
        },
    )


@router.post("/cars/new")
async def create_car_form(request: Request, db: Session = Depends(get_db)):
    form = await request.form()
    data = _form_to_car_data(form)
    if not data["make"] or not data["model"]:
        return RedirectResponse("/cars/new?msg=Make+and+model+are+required", status_code=303)
    car = car_service.create_car(db, CarCreate(**data))
    return RedirectResponse(f"/?msg=Added+{car.make}+{car.model}", status_code=303)


@router.get("/cars/{car_id}/edit")
def edit_car_form(car_id: int, request: Request, db: Session = Depends(get_db)):
    car = car_service.get_car(db, car_id)
    if car is None:
        return RedirectResponse("/?msg=Car+not+found", status_code=303)
    return templates.TemplateResponse(
        request,
        "car_form.html",
        {
            "active": "edit",
            "car": car,
            "action": f"/cars/{car_id}/edit",
            "body_types": BODY_TYPES,
            "fuel_types": FUEL_TYPES,
            "transmissions": TRANSMISSIONS,
        },
    )


@router.post("/cars/{car_id}/edit")
async def update_car_form(car_id: int, request: Request, db: Session = Depends(get_db)):
    car = car_service.get_car(db, car_id)
    if car is None:
        return RedirectResponse("/?msg=Car+not+found", status_code=303)
    form = await request.form()
    data = _form_to_car_data(form)
    car_service.update_car(db, car, CarUpdate(**data))
    return RedirectResponse(f"/?msg=Updated+{car.make}+{car.model}", status_code=303)


@router.post("/cars/{car_id}/delete")
def delete_car_form(car_id: int, db: Session = Depends(get_db)):
    car = car_service.get_car(db, car_id)
    if car is not None:
        car_service.delete_car(db, car)
    return RedirectResponse("/?msg=Car+deleted", status_code=303)


@router.post("/tools/recommendations")
def run_recommendations_ui(db: Session = Depends(get_db)):
    result = run_recommendation_search(db, seed_recommended_cars=True)
    return RedirectResponse(f"/?msg={result['message']}", status_code=303)


@router.post("/tools/fetch-listings")
async def run_fetch_ui(request: Request, db: Session = Depends(get_db)):
    form = await request.form()
    provider = (form.get("provider") or "").strip() or None
    query = (form.get("query") or "").strip() or None
    result = fetch_listings(db, provider=provider, query=query, limit=25)
    return RedirectResponse(f"/?msg={result['message']}", status_code=303)


@router.get("/rules")
def rules_page(request: Request):
    return templates.TemplateResponse(
        request,
        "rules.html",
        {"active": "rules"},
    )


@router.get("/sources")
def sources_page(request: Request, db: Session = Depends(get_db)):
    sources = db.scalars(
        select(RecommendationSource).order_by(RecommendationSource.fetched_at.desc())
    ).all()
    searches = db.scalars(select(SearchRun).order_by(SearchRun.run_at.desc()).limit(25)).all()
    fetches = db.scalars(select(FetchRun).order_by(FetchRun.run_at.desc()).limit(25)).all()
    return templates.TemplateResponse(
        request,
        "sources.html",
        {
            "active": "sources",
            "sources": sources,
            "searches": searches,
            "fetches": fetches,
        },
    )
