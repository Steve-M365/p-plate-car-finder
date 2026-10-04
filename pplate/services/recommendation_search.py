"""Recommendation search: Victorian P-plate rules + commonly recommended first cars.

Two data sources are combined:

1. **Web search** (optional). If ``TAVILY_API_KEY`` is set the Tavily API is used.
   Otherwise the app falls back to a bundled, curated knowledge base of
   authoritative sources. (DuckDuckGo HTML search is available via
   ``provider="duckduckgo"`` but is best-effort and robots-respecting.)
2. **A curated first-car dataset** - small, safe, cheap-to-run Japanese/Korean
   models that are comfortably under the Victorian 130 kW/tonne limit. These are
   upserted into the ``cars`` table with ``source="recommendation"``.

Every search is logged in ``search_runs``; every source in
``recommendation_sources``. External calls go through :class:`ExternalClient`
and are rate-limited, cached and logged.
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from pplate.config import get_settings
from pplate.models import Car, RecommendationSource, SearchRun
from pplate.models.enums import CarSource
from pplate.services.car_service import apply_compliance
from pplate.services.external_http import ExternalClient

logger = logging.getLogger("pplate.recommendations")

# ---------------------------------------------------------------------------
# Search queries
# ---------------------------------------------------------------------------
RULE_QUERIES = [
    "Victoria P plate prohibited vehicles power to mass 130 kW per tonne VicRoads",
    "VicRoads probationary vehicle database approved banned under review",
    "Victorian P1 P2 high performance vehicle restrictions 2026",
    "can a P plater drive a turbo car Victoria power to weight",
]

CAR_QUERIES = [
    "best first cars for P plate drivers Australia under $15000",
    "safest cheap used cars for young drivers Australia small hatch",
    "cheap to run first car Victoria P plate legal ANCAP 5 star",
]

# ---------------------------------------------------------------------------
# Curated authoritative sources (always stored, even offline)
# ---------------------------------------------------------------------------
STATIC_SOURCES: list[dict[str, str]] = [
    {
        "url": "https://transport.vic.gov.au/road-and-active-transport/registration-and-licensing/licences/probationary-licence/vehicles-for-probationary-drivers",
        "title": "Transport Victoria - Vehicles for probationary drivers",
        "summary": (
            "Primary government rule. A vehicle is banned for probationary drivers if "
            "it is rated 'banned' in the probationary vehicle database, has a power to "
            "mass ratio of more than 130 kW per tonne, or has a performance-increasing "
            "engine modification (unless factory)."
        ),
        "category": "rules",
    },
    {
        "url": "https://vicroadssafevehicles.carsalesnetwork.com.au/#/search",
        "title": "Victorian probationary vehicles database (Approved / Banned / Under review)",
        "summary": (
            "Authoritative make/model/variant lookup for probationary drivers. If a car "
            "is not listed, calculate power-to-mass yourself; borderline cars should be "
            "checked here."
        ),
        "category": "rules",
    },
    {
        "url": "https://www.vicroads.vic.gov.au/ls-and-ps/driving-on-your-ps",
        "title": "VicRoads - Driving on your Ps",
        "summary": "P1/P2 conditions including prohibited vehicles and demerit rules.",
        "category": "rules",
    },
    {
        "url": "https://www4.austlii.edu.au/au/legis/vic/num_reg/rsr2019n100o2019403/s57.html",
        "title": "Road Safety (Drivers) Regulations 2019 (Vic), reg 57",
        "summary": "Statutory basis for power-to-mass and high-powered modification declarations.",
        "category": "rules",
    },
    {
        "url": "https://www.carsales.com.au/editorial/details/p-plate-prohibited-vehicles-update-100374/",
        "title": "carsales - P-plate prohibited vehicles update",
        "summary": "Industry summary of the 130 kW/tonne power-to-weight rule across states.",
        "category": "rules",
    },
]

# ---------------------------------------------------------------------------
# Curated first-car dataset
# ---------------------------------------------------------------------------
# Prices are indicative used-market ranges in AUD (Victoria, 2026). Specs are
# typical for the generation; individual listings vary by variant, so the app
# recalculates compliance from whatever power/weight is entered.
CURATED_FIRST_CARS: list[dict[str, Any]] = [
    {
        "make": "Toyota", "model": "Corolla", "variant": "Ascent (hatch/sedan)",
        "year": 2015, "engine_size_cc": 1798, "power_kw": 103, "weight_kg": 1280,
        "body_type": "hatch", "fuel_type": "petrol", "transmission": "CVT",
        "safety_rating_stars": 5.0, "safety_rating_year": 2014,
        "price_low": 8000, "price_high": 16000,
        "pros": "Bulletproof reliability, cheap servicing, 5-star ANCAP, huge parts availability.",
        "cons": "Not exciting to drive; some older examples are basic inside.",
    },
    {
        "make": "Mazda", "model": "Mazda3", "variant": "Maxx/Neo",
        "year": 2015, "engine_size_cc": 1998, "power_kw": 114, "weight_kg": 1270,
        "body_type": "hatch", "fuel_type": "petrol", "transmission": "automatic",
        "safety_rating_stars": 5.0, "safety_rating_year": 2014,
        "price_low": 9000, "price_high": 17000,
        "pros": "Sharp handling, quality interior, strong safety, reliable.",
        "cons": "Firm ride; rear visibility in the hatch is average.",
    },
    {
        "make": "Hyundai", "model": "i30", "variant": "Active",
        "year": 2015, "engine_size_cc": 1797, "power_kw": 107, "weight_kg": 1290,
        "body_type": "hatch", "fuel_type": "petrol", "transmission": "automatic",
        "safety_rating_stars": 5.0, "safety_rating_year": 2013,
        "price_low": 8000, "price_high": 15000,
        "pros": "Great value, 5-star safety, roomy, cheap parts.",
        "cons": "Average fuel economy; base models are plain.",
    },
    {
        "make": "Kia", "model": "Cerato", "variant": "S/Si",
        "year": 2015, "engine_size_cc": 1999, "power_kw": 112, "weight_kg": 1300,
        "body_type": "sedan", "fuel_type": "petrol", "transmission": "automatic",
        "safety_rating_stars": 5.0, "safety_rating_year": 2013,
        "price_low": 8000, "price_high": 15000,
        "pros": "Long warranty history, spacious, 5-star ANCAP, easy to own.",
        "cons": "Resale a touch below Toyota/Mazda; uninspiring dynamics.",
    },
    {
        "make": "Hyundai", "model": "Accent", "variant": "Active",
        "year": 2015, "engine_size_cc": 1591, "power_kw": 91, "weight_kg": 1150,
        "body_type": "hatch", "fuel_type": "petrol", "transmission": "automatic",
        "safety_rating_stars": 5.0, "safety_rating_year": 2011,
        "price_low": 6000, "price_high": 12000,
        "pros": "Very cheap to buy and run, light on fuel, easy to park.",
        "cons": "Small boot; modest power is fine for a first car.",
    },
    {
        "make": "Kia", "model": "Rio", "variant": "S/Si",
        "year": 2015, "engine_size_cc": 1396, "power_kw": 74, "weight_kg": 1120,
        "body_type": "hatch", "fuel_type": "petrol", "transmission": "automatic",
        "safety_rating_stars": 4.0, "safety_rating_year": 2011,
        "price_low": 6000, "price_high": 12000,
        "pros": "Tiny running costs, reliable, cheap insurance.",
        "cons": "Only 4-star on older tests; small and slow.",
    },
    {
        "make": "Suzuki", "model": "Swift", "variant": "GL",
        "year": 2015, "engine_size_cc": 1242, "power_kw": 70, "weight_kg": 990,
        "body_type": "hatch", "fuel_type": "petrol", "transmission": "automatic",
        "safety_rating_stars": 5.0, "safety_rating_year": 2011,
        "price_low": 7000, "price_high": 13000,
        "pros": "Light, frugal, fun to drive, parts are cheap.",
        "cons": "Basic interior; small boot.",
    },
    {
        "make": "Toyota", "model": "Yaris", "variant": "Ascent",
        "year": 2015, "engine_size_cc": 1298, "power_kw": 63, "weight_kg": 1000,
        "body_type": "hatch", "fuel_type": "petrol", "transmission": "automatic",
        "safety_rating_stars": 5.0, "safety_rating_year": 2011,
        "price_low": 7000, "price_high": 13000,
        "pros": "Toyota reliability, cheap to run, 5-star safety.",
        "cons": "Slow; small rear seat.",
    },
    {
        "make": "Honda", "model": "Jazz", "variant": "VTi",
        "year": 2014, "engine_size_cc": 1497, "power_kw": 88, "weight_kg": 1060,
        "body_type": "hatch", "fuel_type": "petrol", "transmission": "CVT",
        "safety_rating_stars": 5.0, "safety_rating_year": 2008,
        "price_low": 7000, "price_high": 14000,
        "pros": "Magic seats, big interior for its size, reliable.",
        "cons": "Older ANCAP year; CVT drones under acceleration.",
    },
    {
        "make": "Mazda", "model": "Mazda2", "variant": "Neo/Maxx",
        "year": 2015, "engine_size_cc": 1496, "power_kw": 79, "weight_kg": 1030,
        "body_type": "hatch", "fuel_type": "petrol", "transmission": "automatic",
        "safety_rating_stars": 4.0, "safety_rating_year": 2014,
        "price_low": 7000, "price_high": 13000,
        "pros": "Nippy, frugal, good build quality.",
        "cons": "4-star on some variants; small boot.",
    },
    {
        "make": "Toyota", "model": "Corolla", "variant": "Ascent (2019+)",
        "year": 2019, "engine_size_cc": 1798, "power_kw": 103, "weight_kg": 1300,
        "body_type": "hatch", "fuel_type": "petrol", "transmission": "CVT",
        "safety_rating_stars": 5.0, "safety_rating_year": 2018,
        "price_low": 16000, "price_high": 24000,
        "pros": "Modern safety tech (AEB), hybrid option, excellent reliability.",
        "cons": "Higher price; hybrid adds cost.",
    },
    {
        "make": "Toyota", "model": "Camry", "variant": "Altise/Ascent",
        "year": 2015, "engine_size_cc": 2494, "power_kw": 133, "weight_kg": 1470,
        "body_type": "sedan", "fuel_type": "petrol", "transmission": "automatic",
        "safety_rating_stars": 5.0, "safety_rating_year": 2011,
        "price_low": 9000, "price_high": 18000,
        "pros": "Comfortable, roomy, 5-star safety, cheap to run for its size.",
        "cons": "Larger to park; thirstier in traffic.",
    },
    {
        "make": "Subaru", "model": "Impreza", "variant": "2.0i",
        "year": 2014, "engine_size_cc": 1995, "power_kw": 110, "weight_kg": 1380,
        "body_type": "hatch", "fuel_type": "petrol", "transmission": "CVT",
        "safety_rating_stars": 5.0, "safety_rating_year": 2011,
        "price_low": 9000, "price_high": 16000,
        "pros": "All-wheel drive grip, 5-star safety, solid build.",
        "cons": "Higher fuel use; CVT not sporty.",
    },
    {
        "make": "Volkswagen", "model": "Polo", "variant": "Trendline/Comfortline",
        "year": 2015, "engine_size_cc": 1197, "power_kw": 66, "weight_kg": 1080,
        "body_type": "hatch", "fuel_type": "petrol", "transmission": "automatic",
        "safety_rating_stars": 5.0, "safety_rating_year": 2010,
        "price_low": 7000, "price_high": 13000,
        "pros": "Quality feel, safe, efficient.",
        "cons": "Servicing can cost more than Japanese rivals.",
    },
    {
        "make": "Nissan", "model": "Pulsar", "variant": "ST",
        "year": 2015, "engine_size_cc": 1798, "power_kw": 96, "weight_kg": 1240,
        "body_type": "hatch", "fuel_type": "petrol", "transmission": "CVT",
        "safety_rating_stars": 5.0, "safety_rating_year": 2014,
        "price_low": 7000, "price_high": 13000,
        "pros": "Roomy, 5-star safety, cheap to buy.",
        "cons": "Average dynamics and resale.",
    },
]


# ---------------------------------------------------------------------------
# Web search providers
# ---------------------------------------------------------------------------
def _tavily_search(client: ExternalClient, query: str, max_results: int = 6) -> list[dict]:
    settings = get_settings()
    if not settings.tavily_api_key:
        return []
    import httpx

    try:
        resp = httpx.post(
            "https://api.tavily.com/search",
            json={
                "api_key": settings.tavily_api_key,
                "query": query,
                "max_results": max_results,
                "search_depth": "basic",
            },
            timeout=settings.external_request_timeout_seconds,
        )
        resp.raise_for_status()
        data = resp.json()
        return [
            {"url": r.get("url"), "title": r.get("title"), "summary": r.get("content")}
            for r in data.get("results", [])
            if r.get("url")
        ]
    except Exception as exc:  # noqa: BLE001
        logger.warning("Tavily search failed for %r: %s", query, exc)
        return []


def _duckduckgo_search(client: ExternalClient, query: str, max_results: int = 6) -> list[dict]:
    """Best-effort DuckDuckGo HTML search (robots-respecting via ExternalClient)."""
    from bs4 import BeautifulSoup

    result = client.get(
        "https://html.duckduckgo.com/html/",
        provider="duckduckgo",
        params={"q": query},
    )
    if not result.text:
        return []
    soup = BeautifulSoup(result.text, "html.parser")
    out: list[dict] = []
    for a in soup.select("a.result__a")[:max_results]:
        title = a.get_text(" ", strip=True)
        href = a.get("href")
        if not href:
            continue
        snippet_el = a.find_parent("div", class_="result")
        snippet = snippet_el.get_text(" ", strip=True) if snippet_el else ""
        out.append({"url": href, "title": title, "summary": snippet[:500]})
    return out


def _search(
    client: ExternalClient, query: str, provider: str
) -> list[dict]:
    if provider == "tavily":
        return _tavily_search(client, query)
    if provider == "duckduckgo":
        return _duckduckgo_search(client, query)
    return []


# ---------------------------------------------------------------------------
# Upserts
# ---------------------------------------------------------------------------
def _upsert_source(
    db: Session, *, url: str, title: str, summary: str | None, category: str, query: str | None
) -> bool:
    existing = db.scalar(select(RecommendationSource).where(RecommendationSource.url == url))
    if existing:
        existing.title = title or existing.title
        existing.summary = summary or existing.summary
        existing.category = category or existing.category
        return False
    db.add(
        RecommendationSource(
            url=url, title=title or url, summary=summary, category=category, query=query
        )
    )
    return True


def _upsert_curated_car(db: Session, spec: dict, *, refresh_all: bool) -> str:
    external_id = f"reco:{spec['make'].lower()}:{spec['model'].lower()}:{spec.get('variant','').lower()}"
    existing = db.scalar(select(Car).where(Car.external_id == external_id))
    price_range = f"Typical used range ${spec['price_low']:,}-${spec['price_high']:,} AUD."
    notes = f"{spec['pros']} CONS: {spec['cons']} {price_range}"

    if existing:
        if not refresh_all:
            return "unchanged"
        existing.make = spec["make"]
        existing.model = spec["model"]
        existing.variant = spec.get("variant")
        existing.year = spec.get("year")
        existing.engine_size_cc = spec.get("engine_size_cc")
        existing.power_kw = spec.get("power_kw")
        existing.weight_kg = spec.get("weight_kg")
        existing.body_type = spec.get("body_type")
        existing.fuel_type = spec.get("fuel_type")
        existing.transmission = spec.get("transmission")
        existing.safety_rating_stars = spec.get("safety_rating_stars")
        existing.safety_rating_year = spec.get("safety_rating_year")
        existing.price_aud = spec.get("price_low")
        existing.recommended = True
        existing.notes = notes
        apply_compliance(existing)
        return "updated"

    car = Car(
        make=spec["make"],
        model=spec["model"],
        variant=spec.get("variant"),
        year=spec.get("year"),
        engine_size_cc=spec.get("engine_size_cc"),
        power_kw=spec.get("power_kw"),
        weight_kg=spec.get("weight_kg"),
        body_type=spec.get("body_type"),
        fuel_type=spec.get("fuel_type"),
        transmission=spec.get("transmission"),
        safety_rating_stars=spec.get("safety_rating_stars"),
        safety_rating_year=spec.get("safety_rating_year"),
        price_aud=spec.get("price_low"),
        source=CarSource.RECOMMENDATION,
        external_id=external_id,
        recommended=True,
        notes=notes,
    )
    apply_compliance(car)
    db.add(car)
    return "inserted"


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------
def run_recommendation_search(
    db: Session,
    *,
    queries: list[str] | None = None,
    seed_recommended_cars: bool = True,
    provider: str | None = None,
) -> dict:
    settings = get_settings()
    if provider is None:
        provider = "tavily" if settings.tavily_api_key else "static"

    client = ExternalClient(db, rate_limit_seconds=settings.search_rate_limit_seconds)

    # 1. Always store the curated authoritative sources.
    sources_added = 0
    for src in STATIC_SOURCES:
        if _upsert_source(
            db,
            url=src["url"],
            title=src["title"],
            summary=src["summary"],
            category=src["category"],
            query=None,
        ):
            sources_added += 1

    # 2. Run the web queries (if a live provider is configured).
    search_queries = queries if queries is not None else (RULE_QUERIES + CAR_QUERIES)
    results_found = 0
    if provider in {"tavily", "duckduckgo"}:
        for query in search_queries:
            results = _search(client, query, provider)
            results_found += len(results)
            db.add(
                SearchRun(query=query, provider=provider, result_count=len(results), error=None)
            )
            for r in results:
                if _upsert_source(
                    db,
                    url=r["url"],
                    title=r.get("title") or r["url"],
                    summary=r.get("summary"),
                    category="web",
                    query=query,
                ):
                    sources_added += 1
            db.commit()

    # 3. Seed/refresh the curated first cars.
    inserted = updated = 0
    if seed_recommended_cars:
        for spec in CURATED_FIRST_CARS:
            outcome = _upsert_curated_car(db, spec, refresh_all=True)
            if outcome == "inserted":
                inserted += 1
            elif outcome == "updated":
                updated += 1
        db.commit()

    total_sources = db.scalar(select(func.count(RecommendationSource.id))) or 0
    return {
        "provider": provider,
        "queries_run": len(search_queries) if provider in {"tavily", "duckduckgo"} else 0,
        "web_results": results_found,
        "sources_added": sources_added,
        "total_sources": total_sources,
        "recommended_inserted": inserted,
        "recommended_updated": updated,
        "message": (
            f"Used '{provider}' provider. Stored {sources_added} new source(s); "
            f"seeded {inserted} new and refreshed {updated} recommended car(s)."
        ),
    }
