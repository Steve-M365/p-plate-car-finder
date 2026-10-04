"""Fetch and normalise used-car listings into the local database.

Providers
---------
* ``mock``      - deterministic synthetic listings for demos/tests (offline).
* ``csv``       - import from a CSV file (the safe, always-available path).
* ``carsales``  - best-effort live fetch of carsales.com.au, subject to
                  robots.txt / terms. If blocked it logs and returns nothing
                  rather than circumventing the block.

``auto`` tries a CSV if one exists, otherwise falls back to mock. Carsales is
only used when explicitly requested, to keep default behaviour respectful of
site terms. Every provider returns a list of normalised car dicts; the same
upsert + compliance pipeline then runs for all of them.
"""

from __future__ import annotations

import csv
import json
import logging
import random
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from pplate.config import get_settings
from pplate.models import Car, FetchRun
from pplate.models.enums import CarSource, ComplianceStatus
from pplate.services.car_service import apply_compliance
from pplate.services.external_http import ExternalClient
from pplate.services.listing_parser import parse_listing

logger = logging.getLogger("pplate.listings")

# ---------------------------------------------------------------------------
# Mock data (offline demo). Mix of compliant / non-compliant / borderline.
# ---------------------------------------------------------------------------
_MOCK_POOL: list[dict[str, Any]] = [
    {"make": "Toyota", "model": "Corolla", "variant": "Ascent", "year": 2016, "engine_size_cc": 1798, "power_kw": 103, "weight_kg": 1280, "body_type": "hatch", "fuel_type": "petrol", "transmission": "CVT", "safety_rating_stars": 5.0, "safety_rating_year": 2014},
    {"make": "Mazda", "model": "Mazda3", "variant": "Maxx", "year": 2017, "engine_size_cc": 1998, "power_kw": 114, "weight_kg": 1270, "body_type": "hatch", "fuel_type": "petrol", "transmission": "automatic", "safety_rating_stars": 5.0, "safety_rating_year": 2014},
    {"make": "Hyundai", "model": "i30", "variant": "Active", "year": 2015, "engine_size_cc": 1797, "power_kw": 107, "weight_kg": 1290, "body_type": "hatch", "fuel_type": "petrol", "transmission": "automatic", "safety_rating_stars": 5.0, "safety_rating_year": 2013},
    {"make": "Kia", "model": "Rio", "variant": "Si", "year": 2016, "engine_size_cc": 1396, "power_kw": 74, "weight_kg": 1120, "body_type": "hatch", "fuel_type": "petrol", "transmission": "automatic", "safety_rating_stars": 4.0, "safety_rating_year": 2011},
    {"make": "Suzuki", "model": "Swift", "variant": "GL", "year": 2017, "engine_size_cc": 1242, "power_kw": 70, "weight_kg": 990, "body_type": "hatch", "fuel_type": "petrol", "transmission": "automatic", "safety_rating_stars": 5.0, "safety_rating_year": 2011},
    {"make": "Honda", "model": "Jazz", "variant": "VTi", "year": 2015, "engine_size_cc": 1497, "power_kw": 88, "weight_kg": 1060, "body_type": "hatch", "fuel_type": "petrol", "transmission": "CVT", "safety_rating_stars": 5.0, "safety_rating_year": 2008},
    {"make": "Hyundai", "model": "Accent", "variant": "Active", "year": 2016, "engine_size_cc": 1591, "power_kw": 91, "weight_kg": 1150, "body_type": "hatch", "fuel_type": "petrol", "transmission": "automatic", "safety_rating_stars": 5.0, "safety_rating_year": 2011},
    {"make": "Nissan", "model": "Pulsar", "variant": "ST", "year": 2015, "engine_size_cc": 1798, "power_kw": 96, "weight_kg": 1240, "body_type": "hatch", "fuel_type": "petrol", "transmission": "CVT", "safety_rating_stars": 5.0, "safety_rating_year": 2014},
    {"make": "Kia", "model": "Cerato", "variant": "Si", "year": 2016, "engine_size_cc": 1999, "power_kw": 112, "weight_kg": 1300, "body_type": "sedan", "fuel_type": "petrol", "transmission": "automatic", "safety_rating_stars": 5.0, "safety_rating_year": 2013},
    {"make": "Toyota", "model": "Camry", "variant": "Altise", "year": 2015, "engine_size_cc": 2494, "power_kw": 133, "weight_kg": 1470, "body_type": "sedan", "fuel_type": "petrol", "transmission": "automatic", "safety_rating_stars": 5.0, "safety_rating_year": 2011},
    # --- Non-compliant / borderline examples (so the demo shows the logic) ---
    {"make": "Toyota", "model": "86", "variant": "GT", "year": 2016, "engine_size_cc": 1998, "power_kw": 152, "weight_kg": 1230, "body_type": "coupe", "fuel_type": "petrol", "transmission": "manual", "safety_rating_stars": 5.0, "safety_rating_year": 2012},
    {"make": "Mazda", "model": "MX-5", "variant": "Roadster GT", "year": 2016, "engine_size_cc": 1998, "power_kw": 135, "weight_kg": 1058, "body_type": "convertible", "fuel_type": "petrol", "transmission": "manual", "safety_rating_stars": 4.0, "safety_rating_year": 2015},
    {"make": "Subaru", "model": "WRX", "variant": "Premium", "year": 2015, "engine_size_cc": 1998, "power_kw": 195, "weight_kg": 1455, "body_type": "sedan", "fuel_type": "petrol", "transmission": "manual", "safety_rating_stars": 5.0, "safety_rating_year": 2014},
    {"make": "Honda", "model": "Civic", "variant": "Type R", "year": 2018, "engine_size_cc": 1996, "power_kw": 228, "weight_kg": 1380, "body_type": "hatch", "fuel_type": "petrol", "transmission": "manual", "safety_rating_stars": 5.0, "safety_rating_year": 2017},
    {"make": "Volkswagen", "model": "Golf", "variant": "R", "year": 2016, "engine_size_cc": 1984, "power_kw": 221, "weight_kg": 1435, "body_type": "hatch", "fuel_type": "petrol", "transmission": "dual-clutch", "safety_rating_stars": 5.0, "safety_rating_year": 2014},
]

_MOCK_SUBURBS = [
    "Werribee VIC", "Dandenong VIC", "Geelong VIC", "Frankston VIC",
    "Bundoora VIC", "Sunshine VIC", "Ringwood VIC", "Berwick VIC",
    "Craigieburn VIC", "Epping VIC",
]


def _normalise_minimum(rec: dict[str, Any], source: str, external_id: str) -> dict[str, Any]:
    return {
        "make": rec.get("make", "").strip(),
        "model": rec.get("model", "").strip(),
        "variant": (rec.get("variant") or None),
        "year": rec.get("year"),
        "engine_size_cc": rec.get("engine_size_cc"),
        "power_kw": rec.get("power_kw"),
        "weight_kg": rec.get("weight_kg"),
        "body_type": rec.get("body_type"),
        "fuel_type": rec.get("fuel_type"),
        "transmission": rec.get("transmission"),
        "cylinders": rec.get("cylinders"),
        "price_aud": rec.get("price_aud"),
        "odometer_km": rec.get("odometer_km"),
        "location": rec.get("location"),
        "safety_rating_stars": rec.get("safety_rating_stars"),
        "safety_rating_year": rec.get("safety_rating_year"),
        "listing_url": rec.get("listing_url"),
        "source": source,
        "external_id": external_id,
    }


# ---------------------------------------------------------------------------
# Providers
# ---------------------------------------------------------------------------
def _iter_feed_entries(text: str, fmt: str):
    """Yield {title, link, summary, price, odometer} from an RSS/Atom/JSON feed."""
    hint = (fmt or "auto").lower()
    stripped = text.lstrip()
    is_json = hint == "json" or (hint == "auto" and stripped[:1] in "[{")
    if is_json:
        data = json.loads(text)
        items = data if isinstance(data, list) else (
            data.get("items") or data.get("results") or data.get("listings") or []
        )
        for it in items:
            if not isinstance(it, dict):
                continue
            yield {
                "title": it.get("title") or it.get("name"),
                "link": it.get("url") or it.get("link"),
                "summary": it.get("description") or it.get("summary"),
                "price": it.get("price"),
                "odometer": it.get("odometer") or it.get("mileage"),
            }
        return
    root = ET.fromstring(text)
    for el in root.iter():
        if el.tag.split("}")[-1] not in ("item", "entry"):
            continue
        rec: dict[str, Any] = {}
        for child in el:
            tag = child.tag.split("}")[-1]
            if tag == "title":
                rec["title"] = child.text
            elif tag == "link":
                rec["link"] = child.text or child.get("href")
            elif tag in ("description", "summary"):
                rec["summary"] = child.text
        yield rec


def _feed_provider(
    client: ExternalClient, url: str, fmt: str, limit: int
) -> tuple[list[dict], str | None]:
    result = client.get(url, provider="feed")
    if not result.text:
        return [], f"Feed fetch failed: {result.error or 'no content'}."
    try:
        entries = list(_iter_feed_entries(result.text, fmt))
    except Exception as exc:  # noqa: BLE001
        return [], f"Could not parse feed ({fmt}): {exc}"

    def _num(value: Any) -> int | None:
        try:
            return int(
                float(str(value).replace(",", "").replace("$", "").replace("km", "").strip())
            )
        except (TypeError, ValueError):
            return None

    records: list[dict] = []
    for entry in entries[:limit]:
        combined = " ".join(filter(None, [entry.get("title"), entry.get("summary")]))
        rec = parse_listing(
            url=entry.get("link"), title=entry.get("title"), text=combined, source=CarSource.FEED.value
        )
        if _num(entry.get("price")):
            rec["price_aud"] = _num(entry.get("price"))
        if _num(entry.get("odometer")):
            rec["odometer_km"] = _num(entry.get("odometer"))
        if rec.get("make") and rec.get("model"):
            records.append(rec)
    return records, (None if records else "Feed contained no parseable car listings.")


def _ebay_provider(
    client: ExternalClient, settings, query: str | None, limit: int
) -> tuple[list[dict], str | None]:
    if not settings.ebay_oauth_token:
        return [], (
            "eBay provider needs EBAY_OAUTH_TOKEN (create a free eBay developer app "
            "and use a Browse API OAuth token)."
        )
    data, result = client.get_json(
        "https://api.ebay.com/buy/browse/v1/item_summary/search",
        provider="ebay",
        params={"q": query or "car", "limit": min(limit, 50), "filter": "itemLocationCountry:AU"},
        headers={
            "Authorization": f"Bearer {settings.ebay_oauth_token}",
            "X-EBAY-C-MARKETPLACE-ID": settings.ebay_marketplace_id,
        },
        respect_robots=False,
    )
    if data is None:
        return [], f"eBay API request failed: {result.error or result.status_code}."

    records: list[dict] = []
    for item in (data.get("itemSummaries") or [])[:limit]:
        title = item.get("title")
        rec = parse_listing(
            url=item.get("itemWebUrl"), title=title, text=title or "", source=CarSource.EBAY.value
        )
        price = (item.get("price") or {}).get("value")
        if price:
            try:
                rec["price_aud"] = int(float(price))
            except (TypeError, ValueError):
                pass
        loc = item.get("itemLocation") or {}
        loc_str = ", ".join(filter(None, [loc.get("city"), loc.get("state"), loc.get("country")]))
        if loc_str:
            rec["location"] = loc_str
        if rec.get("make") and rec.get("model"):
            records.append(rec)
    return records, (None if records else "eBay returned no parseable car listings for that query.")


def _mock_provider(query: str | None, limit: int) -> list[dict]:
    pool = _MOCK_POOL
    if query:
        q = query.lower()
        pool = [p for p in pool if q in f"{p['make']} {p['model']} {p.get('variant','')}".lower()] or _MOCK_POOL
    rng = random.Random(42)
    # Sample across the pool so a small limit still shows a realistic mix of
    # compliant / borderline / non-compliant examples (deterministic).
    chosen = pool if len(pool) <= limit else rng.sample(pool, limit)
    out: list[dict] = []
    for i, base in enumerate(chosen):
        rec = dict(base)
        rec["odometer_km"] = rng.randint(40_000, 160_000)
        # Used price decays with odometer from a rough new-ish anchor.
        rec["price_aud"] = max(4000, 22_000 - rec["odometer_km"] // 20 + rng.randint(-1500, 2500))
        rec["location"] = rng.choice(_MOCK_SUBURBS)
        rec["listing_url"] = f"https://example.invalid/listing/{i+1}"
        ext = f"mock:{rec['make'].lower()}:{rec['model'].lower()}:{(rec.get('variant') or '').lower()}"
        out.append(_normalise_minimum(rec, CarSource.MOCK.value, ext))
    return out


def _csv_provider(path: str, limit: int) -> list[dict]:
    p = Path(path)
    if not p.exists():
        return []
    out: list[dict] = []
    with p.open(newline="", encoding="utf-8") as fh:
        for i, row in enumerate(csv.DictReader(fh)):
            if i >= limit:
                break

            def num(key: str, cast=float):
                v = row.get(key)
                if v in (None, "", "None"):
                    return None
                try:
                    return cast(v)
                except (TypeError, ValueError):
                    return None

            rec = {
                "make": row.get("make"),
                "model": row.get("model"),
                "variant": row.get("variant"),
                "year": num("year", int),
                "engine_size_cc": num("engine_size_cc", int),
                "power_kw": num("power_kw", float),
                "weight_kg": num("weight_kg", int),
                "body_type": row.get("body_type") or None,
                "fuel_type": row.get("fuel_type") or None,
                "transmission": row.get("transmission") or None,
                "price_aud": num("price_aud", int),
                "odometer_km": num("odometer_km", int),
                "location": row.get("location") or None,
                "safety_rating_stars": num("safety_rating_stars", float),
                "safety_rating_year": num("safety_rating_year", int),
                "listing_url": row.get("listing_url") or None,
            }
            ext = row.get("external_id") or f"csv:{i+1}"
            out.append(_normalise_minimum(rec, CarSource.CSV.value, ext))
    return out


def _carsales_provider(client: ExternalClient, query: str | None, limit: int) -> tuple[list[dict], str | None]:
    """Best-effort carsales fetch. Returns (records, message)."""
    import json

    from bs4 import BeautifulSoup

    q = (query or "hatch").strip().replace(" ", "+")
    search_url = f"https://www.carsales.com.au/cars/?q={q}"
    result = client.get(search_url, provider="carsales")
    if result.allowed_by_robots is False:
        return [], "carsales robots.txt disallows automated access; skipped (use CSV import instead)."
    if not result.text:
        return [], f"carsales fetch failed: {result.error or 'no content'}"

    soup = BeautifulSoup(result.text, "html.parser")
    records: list[dict] = []
    # Carsales embeds JSON-LD (schema.org Car) blocks on listing pages.
    for tag in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(tag.string or "{}")
        except json.JSONDecodeError:
            continue
        items = data if isinstance(data, list) else [data]
        for item in items:
            if not isinstance(item, dict):
                continue
            if item.get("@type") not in {"Car", "Product", "Vehicle"}:
                continue
            offers = item.get("offers") or {}
            name = item.get("name") or ""
            price = None
            if isinstance(offers, dict):
                price = offers.get("price")
            try:
                price = int(float(price)) if price is not None else None
            except (TypeError, ValueError):
                price = None
            parts = name.split()
            year = next((int(p) for p in parts if p.isdigit() and len(p) == 4), None)
            records.append(
                _normalise_minimum(
                    {
                        "make": parts[1] if len(parts) > 1 else name,
                        "model": parts[2] if len(parts) > 2 else "",
                        "year": year,
                        "price_aud": price,
                        "listing_url": item.get("url"),
                    },
                    CarSource.CARSALES.value,
                    item.get("sku") or item.get("url") or name,
                )
            )
            if len(records) >= limit:
                break
        if len(records) >= limit:
            break

    if not records:
        return [], "carsales responded but no parseable listings were found (page structure may have changed)."
    return records, None


# ---------------------------------------------------------------------------
# Upsert + run
# ---------------------------------------------------------------------------
def _upsert_car(db: Session, rec: dict) -> tuple[Car, str]:
    external_id = rec.get("external_id")
    existing = None
    if external_id:
        existing = db.scalar(select(Car).where(Car.external_id == external_id))
    if existing:
        for k, v in rec.items():
            if k in {"source", "external_id"}:
                continue
            setattr(existing, k, v)
        apply_compliance(existing)
        return existing, "updated"
    car = Car(**rec)
    apply_compliance(car)
    db.add(car)
    return car, "inserted"


def upsert_record(db: Session, rec: dict) -> tuple[Car, str]:
    """Public upsert used by the capture flow, feeds and single-URL import."""
    return _upsert_car(db, rec)


def save_captured_listing(
    db: Session,
    *,
    url: str | None = None,
    title: str | None = None,
    html: str | None = None,
    text: str | None = None,
    overrides: dict | None = None,
    source: str = CarSource.CAPTURE.value,
) -> dict:
    """Parse a user-captured listing, upsert it and tag P-plate compliance.

    This is the ToS-friendly "real data" path: the user saves a page they can
    already see (carsales, Gumtree, Facebook Marketplace, a dealer site), so no
    site crawl or access control is circumvented.
    """
    rec = parse_listing(
        url=url, title=title, html=html, text=text, source=source, overrides=overrides
    )
    if not rec.get("make") or not rec.get("model"):
        return {
            "saved": False,
            "message": (
                "Could not detect a make/model. Re-save with the page fully loaded, "
                "or add the car manually."
            ),
            "parsed": rec,
        }
    car, outcome = _upsert_car(db, rec)
    db.commit()
    db.refresh(car)
    return {
        "saved": True,
        "outcome": outcome,
        "car_id": car.id,
        "make": car.make,
        "model": car.model,
        "year": car.year,
        "price_aud": car.price_aud,
        "p_plate_compliant": car.p_plate_compliant.value,
        "p_plate_reason": car.p_plate_reason,
        "parsed": rec,
    }


def fetch_listings(
    db: Session,
    *,
    provider: str | None = None,
    query: str | None = None,
    limit: int = 25,
) -> dict:
    settings = get_settings()
    provider = (provider or settings.listing_provider or "auto").lower()
    client = ExternalClient(
        db,
        rate_limit_seconds=settings.listing_rate_limit_seconds,
        cache_ttl_seconds=settings.listing_cache_ttl_seconds,
    )

    message: str | None = None
    if provider == "auto":
        if settings.listing_feed_url:
            provider = "feed"
        elif Path(settings.listings_csv_path).exists():
            provider = "csv"
        else:
            provider = "mock"

    if provider == "mock":
        records = _mock_provider(query, limit)
    elif provider == "csv":
        records = _csv_provider(settings.listings_csv_path, limit)
        if not records:
            message = f"No rows found in {settings.listings_csv_path}; nothing imported."
    elif provider == "carsales":
        records, message = _carsales_provider(client, query, limit)
    elif provider == "feed":
        if not settings.listing_feed_url:
            records, message = [], "Set LISTING_FEED_URL to use the feed provider."
        else:
            records, message = _feed_provider(
                client, settings.listing_feed_url, settings.listing_feed_format, limit
            )
    elif provider == "ebay":
        records, message = _ebay_provider(client, settings, query, limit)
    elif provider in {"autograb", "redbook"}:
        records = []
        message = (
            f"'{provider}' is a licensed/partner API. Set "
            f"{provider.upper()}_API_KEY and wire the vendor endpoint to enable it."
        )
    else:
        records = []
        message = f"Unknown provider {provider!r}."

    inserted = updated = skipped = 0
    tally = {s.value: 0 for s in ComplianceStatus}
    for rec in records:
        if not rec.get("make") or not rec.get("model"):
            skipped += 1
            continue
        _car, outcome = _upsert_car(db, rec)
        if outcome == "inserted":
            inserted += 1
        else:
            updated += 1
    db.commit()

    # Recount compliance across the rows we just touched.
    for rec in records:
        ext = rec.get("external_id")
        if not ext:
            continue
        car = db.scalar(select(Car).where(Car.external_id == ext))
        if car is not None:
            tally[car.p_plate_compliant.value] += 1

    run = FetchRun(
        provider=provider,
        query=query,
        fetched_count=len(records),
        inserted_count=inserted,
        updated_count=updated,
        skipped_count=skipped,
        status="ok" if records or provider not in {"carsales"} else "empty",
        error=message,
    )
    db.add(run)
    db.commit()
    db.refresh(run)

    return {
        "run_id": run.id,
        "provider": provider,
        "query": query,
        "fetched": len(records),
        "inserted": inserted,
        "updated": updated,
        "skipped": skipped,
        "status": run.status,
        "message": message or f"Fetched {len(records)} listing(s) via '{provider}'.",
        "compliance": tally,
    }
