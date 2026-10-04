"""Tests for the listing parser and the user-initiated capture flow."""

from __future__ import annotations

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from pplate.db.base import Base
from pplate.models import Car
from pplate.models.enums import CarSource, ComplianceStatus
from pplate.services.listing_fetch import save_captured_listing
from pplate.services.listing_parser import parse_listing

JSONLD_PAGE = """<html><head>
<title>2016 Toyota Corolla Ascent | carsales</title>
<script type="application/ld+json">
{"@type":"Car","brand":{"name":"Toyota"},"model":"Corolla","vehicleModelDate":"2016",
 "mileageFromOdometer":{"value":92000,"unitCode":"KMT"},
 "offers":{"@type":"Offer","price":"13990"}}
</script></head>
<body>2016 Toyota Corolla Ascent 1.8L petrol automatic 92,000 km Werribee VIC</body></html>"""


def _session():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def test_parse_jsonld_page():
    rec = parse_listing(url="https://example.com/x", html=JSONLD_PAGE, source="capture")
    assert rec["make"] == "Toyota"
    assert rec["model"] == "Corolla"
    assert rec["year"] == 2016
    assert rec["price_aud"] == 13990
    assert rec["odometer_km"] == 92000
    assert rec["engine_size_cc"] == 1800
    assert rec["fuel_type"] == "petrol"
    assert rec["transmission"] == "automatic"
    assert rec["source"] == "capture"


def test_parse_from_title_text_only():
    rec = parse_listing(
        title="2014 Mazda 3 Maxx 2.0L auto $15,500 88,000kms",
        text="2014 Mazda 3 Maxx 2.0L auto $15,500 88,000kms",
        source="capture",
    )
    assert rec["make"] == "Mazda"
    assert rec["year"] == 2014
    assert rec["price_aud"] == 15500
    assert rec["odometer_km"] == 88000


def test_explicit_overrides_win():
    rec = parse_listing(
        title="2014 Mazda 3",
        text="2014 Mazda 3",
        overrides={"price_aud": 9999, "power_kw": 120.0, "weight_kg": 1300},
        source="capture",
    )
    assert rec["price_aud"] == 9999
    assert rec["power_kw"] == 120.0


def test_external_id_is_stable_and_source_scoped():
    a = parse_listing(url="https://e.com/1", source="capture")
    b = parse_listing(url="https://e.com/1", source="capture")
    c = parse_listing(url="https://e.com/1", source="feed")
    assert a["external_id"] == b["external_id"]
    assert a["external_id"] != c["external_id"]


def test_save_captured_listing_upserts_and_tags():
    db = _session()
    # The page has no power/weight, so compliance is conservatively "unknown".
    result = save_captured_listing(db, url="https://example.com/x", html=JSONLD_PAGE)
    assert result["saved"] is True
    assert result["p_plate_compliant"] == ComplianceStatus.UNKNOWN.value

    cars = db.scalars(select(Car)).all()
    assert len(cars) == 1
    assert cars[0].source == CarSource.CAPTURE

    # Re-saving the same URL with specs supplied updates (not duplicates) and is compliant.
    again = save_captured_listing(
        db,
        url="https://example.com/x",
        html=JSONLD_PAGE,
        overrides={"power_kw": 103, "weight_kg": 1280},
    )
    assert again["outcome"] == "updated"
    assert again["p_plate_compliant"] == ComplianceStatus.COMPLIANT.value
    assert len(db.scalars(select(Car)).all()) == 1
    assert db.scalars(select(Car)).one().power_to_weight == 80.5


def test_save_captured_listing_needs_make_model():
    db = _session()
    result = save_captured_listing(db, url="https://e.com/x", text="just some words")
    assert result["saved"] is False
