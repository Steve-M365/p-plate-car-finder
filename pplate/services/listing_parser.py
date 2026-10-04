"""Parse a single car listing page/text into normalised car fields.

Used by the user-initiated capture flow (bookmarklet / extension) and by the
single-URL import. It reads, in priority order:

1. JSON-LD (schema.org ``Car`` / ``Vehicle`` / ``Product`` / ``Offer``).
2. Open Graph / meta tags and the page ``<title>``.
3. Conservative regex heuristics over the visible text.

The result is a best-effort partial record: the user can edit anything the
parser got wrong, and the compliance engine recomputes from whatever specs are
present. This module never fetches anything itself.
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Iterable

from bs4 import BeautifulSoup

KNOWN_MAKES = [
    "Toyota", "Mazda", "Hyundai", "Kia", "Ford", "Holden", "Nissan", "Honda",
    "Mitsubishi", "Subaru", "Volkswagen", "VW", "Suzuki", "Mazda", "Mitsubishi",
    "Isuzu", "BMW", "Mercedes-Benz", "Mercedes", "Audi", "Lexus", "Volvo",
    "Renault", "Peugeot", "Skoda", "MG", "BYD", "Tesla", "Jeep", "Land Rover",
    "Chery", "GWM", "Haval", "LDV", "Cupra", "Polestar", "Mini", "Alfa Romeo",
    "Citroen", "Fiat", "Genesis", "Ram", "Chevrolet", "Daihatsu", "Infiniti",
]

_BODY_KEYWORDS = {
    "hatch": "hatch", "hatchback": "hatch", "sedan": "sedan", "saloon": "sedan",
    "wagon": "wagon", "estate": "wagon", "suv": "SUV", "4x4": "SUV",
    "ute": "ute", "utility": "ute", "pickup": "ute", "coupe": "coupe",
    "convertible": "convertible", "cabriolet": "convertible", "van": "van",
    "people mover": "people mover",
}

_YEAR_RE = re.compile(r"\b(19[89][0-9]|20[0-3][0-9])\b")
_PRICE_RE = re.compile(r"\$\s?([0-9]{1,3}(?:,[0-9]{3})+|[0-9]{3,7})")
_ODO_RE = re.compile(r"\b([0-9]{1,3}(?:,[0-9]{3})|[0-9]{3,6})\s?(?:km|kms|kilometres)\b", re.IGNORECASE)
_ENGINE_L_RE = re.compile(r"\b([0-9]\.[0-9])\s?(?:l\b|litre|liter)", re.IGNORECASE)
_ENGINE_CC_RE = re.compile(r"\b([0-9]{3,4})\s?cc\b", re.IGNORECASE)
_POWER_RE = re.compile(r"\b([0-9]{2,4})\s?kW\b", re.IGNORECASE)


def _to_int(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return int(value)
    m = re.search(r"[0-9][0-9,]*", str(value))
    if not m:
        return None
    try:
        return int(m.group().replace(",", ""))
    except ValueError:
        return None


def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    m = re.search(r"[0-9]+(?:\.[0-9]+)?", str(value))
    return float(m.group()) if m else None


def _clean(value: Any) -> str | None:
    if value is None:
        return None
    s = str(value).strip()
    return s or None


def _walk(obj: Any) -> Iterable[Any]:
    yield obj
    if isinstance(obj, dict):
        for v in obj.values():
            yield from _walk(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _walk(v)


def _from_jsonld_node(node: dict) -> dict:
    out: dict[str, Any] = {}
    name = _clean(node.get("name"))
    if name:
        out["_name"] = name
    brand = node.get("brand")
    if isinstance(brand, dict):
        brand = brand.get("name")
    if brand:
        out["make"] = _clean(brand)
    model = node.get("model") or node.get("vehicleModel") or node.get("modelDate")
    if model:
        out["model"] = _clean(model)
    year = _to_int(node.get("vehicleModelDate") or node.get("modelDate") or node.get("productionDate"))
    if year:
        out["year"] = year

    mileage = node.get("mileageFromOdometer")
    if isinstance(mileage, dict):
        mileage = mileage.get("value")
    odo = _to_int(mileage)
    if odo:
        out["odometer_km"] = odo

    offers = node.get("offers")
    price = None
    if isinstance(offers, dict):
        price = offers.get("price") or offers.get("lowPrice")
    elif isinstance(offers, list) and offers and isinstance(offers[0], dict):
        price = offers[0].get("price")
    price_int = _to_int(price)
    if price_int and price_int > 500:
        out["price_aud"] = price_int

    engine = node.get("vehicleEngine")
    if isinstance(engine, dict):
        disp = engine.get("engineDisplacement")
        if isinstance(disp, dict):
            disp = disp.get("value")
        cc = _to_int(disp)
        if cc:
            out["engine_size_cc"] = cc if cc > 100 else cc * 1000
        power = _to_float(engine.get("enginePower"))
        if power:
            out["power_kw"] = power

    if node.get("image"):
        pass  # images are not stored
    return out


def _jsonld_fields(soup: BeautifulSoup) -> dict:
    merged: dict[str, Any] = {}
    for tag in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(tag.string or tag.get_text() or "{}")
        except (json.JSONDecodeError, TypeError):
            continue
        for node in _walk(data):
            if not isinstance(node, dict):
                continue
            t = node.get("@type")
            types = t if isinstance(t, list) else [t]
            if any(x in {"Car", "Vehicle", "Product", "Offer", "VehicleListing"} for x in types):
                merged.update({k: v for k, v in _from_jsonld_node(node).items() if v})
    return merged


def _meta_fields(soup: BeautifulSoup) -> dict:
    out: dict[str, Any] = {}
    title = None
    og_title = soup.find("meta", property="og:title")
    if og_title and og_title.get("content"):
        title = og_title["content"]
    elif soup.title and soup.title.string:
        title = soup.title.string
    if title:
        out["_name"] = title.strip()

    price_meta = soup.find("meta", property="product:price:amount") or soup.find(
        "meta", attrs={"name": "product:price:amount"}
    )
    if price_meta and price_meta.get("content"):
        out["price_aud"] = _to_int(price_meta["content"])

    desc = soup.find("meta", attrs={"name": "description"}) or soup.find("meta", property="og:description")
    if desc and desc.get("content"):
        out["_description"] = desc["content"]
    return out


def _heuristics(text: str) -> dict:
    out: dict[str, Any] = {}
    if not text:
        return out

    m = _YEAR_RE.search(text)
    if m:
        out["year"] = int(m.group(1))

    m = _PRICE_RE.search(text)
    if m:
        out["price_aud"] = _to_int(m.group(1))

    m = _ODO_RE.search(text)
    if m:
        out["odometer_km"] = _to_int(m.group(1))

    m = _ENGINE_CC_RE.search(text)
    if m:
        out["engine_size_cc"] = int(m.group(1))
    elif (m := _ENGINE_L_RE.search(text)):
        out["engine_size_cc"] = int(float(m.group(1)) * 1000)

    m = _POWER_RE.search(text)
    if m:
        out["power_kw"] = float(m.group(1))

    low = text.lower()
    if "dual-clutch" in low or "dsg" in low:
        out["transmission"] = "dual-clutch"
    elif re.search(r"\bcvt\b", low):
        out["transmission"] = "CVT"
    elif "manual" in low:
        out["transmission"] = "manual"
    elif "automatic" in low or re.search(r"\bauto\b", low):
        out["transmission"] = "automatic"

    if "diesel" in low:
        out["fuel_type"] = "diesel"
    elif "hybrid" in low:
        out["fuel_type"] = "hybrid"
    elif "electric" in low or re.search(r"\bev\b", low):
        out["fuel_type"] = "electric"
    elif "lpg" in low:
        out["fuel_type"] = "LPG"
    elif "petrol" in low or "unleaded" in low:
        out["fuel_type"] = "petrol"

    for kw, body in _BODY_KEYWORDS.items():
        if kw in low:
            out["body_type"] = body
            break

    for make in KNOWN_MAKES:
        if re.search(rf"\b{re.escape(make.lower())}\b", low):
            out["make"] = "Volkswagen" if make == "VW" else make
            break

    return out


def _title_make_model(title: str | None, make: str | None) -> tuple[str | None, str | None]:
    """Best-effort make/model from a title when JSON-LD did not supply them."""
    if not title:
        return make, None
    cleaned = re.sub(r"\b(19[89][0-9]|20[0-3][0-9])\b", " ", title)
    cleaned = re.sub(r"[|–—-].*$", " ", cleaned)  # drop trailing site/marketing
    tokens = [t for t in re.split(r"\s+", cleaned) if t]
    if not tokens:
        return make, None
    if make is None:
        for t in tokens:
            for known in KNOWN_MAKES:
                if t.lower() == known.lower():
                    make = "Volkswagen" if known == "VW" else known
                    break
            if make:
                break
    model = None
    if make:
        for i, t in enumerate(tokens):
            if t.lower() == make.lower() and i + 1 < len(tokens):
                model = tokens[i + 1]
                break
    if model is None and len(tokens) >= 2:
        model = tokens[1]
    return make, model


def make_external_id(url: str | None, title: str | None, source: str) -> str:
    basis = url or title or "unknown"
    digest = hashlib.sha1(basis.encode("utf-8", "ignore")).hexdigest()[:16]
    return f"{source}:{digest}"


def parse_listing(
    *,
    url: str | None = None,
    title: str | None = None,
    html: str | None = None,
    text: str | None = None,
    source: str = "capture",
    overrides: dict | None = None,
) -> dict:
    """Return a normalised, partial car record (only fields we are confident about)."""
    fields: dict[str, Any] = {}

    soup = None
    if html:
        soup = BeautifulSoup(html, "html.parser")
        fields.update(_jsonld_fields(soup))
        fields.update({k: v for k, v in _meta_fields(soup).items() if v})
        if text is None:
            text = soup.get_text(" ", strip=True)

    # Explicit title beats parsed title.
    if title:
        fields["_name"] = title

    # Heuristics over combined text (page text + description + name).
    combined = " ".join(filter(None, [text, fields.get("_description"), fields.get("_name")]))
    for key, value in _heuristics(combined).items():
        fields.setdefault(key, value)

    # Make/model fallback from the title.
    make, model = _title_make_model(fields.get("_name"), fields.get("make"))
    if make and not fields.get("make"):
        fields["make"] = make
    if model and not fields.get("model"):
        fields["model"] = model

    if overrides:
        for key, value in overrides.items():
            if value not in (None, "", []):
                fields[key] = value

    record = {
        "make": fields.get("make"),
        "model": fields.get("model"),
        "variant": fields.get("variant"),
        "year": fields.get("year"),
        "engine_size_cc": fields.get("engine_size_cc"),
        "power_kw": fields.get("power_kw"),
        "weight_kg": fields.get("weight_kg"),
        "body_type": fields.get("body_type"),
        "fuel_type": fields.get("fuel_type"),
        "transmission": fields.get("transmission"),
        "cylinders": fields.get("cylinders"),
        "price_aud": fields.get("price_aud"),
        "odometer_km": fields.get("odometer_km"),
        "location": fields.get("location"),
        "safety_rating_stars": fields.get("safety_rating_stars"),
        "safety_rating_year": fields.get("safety_rating_year"),
        "listing_url": url,
        "source": source,
        "external_id": make_external_id(url, fields.get("_name"), source),
    }
    return record
