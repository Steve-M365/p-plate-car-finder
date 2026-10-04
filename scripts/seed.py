"""Seed the database with 20 example cars (compliant, borderline and not).

Run:  python scripts/seed.py
Idempotent: rows are keyed by ``external_id = "seed:<n>"`` and updated in place.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select  # noqa: E402

from pplate.db import SessionLocal, init_db  # noqa: E402
from pplate.models import Car  # noqa: E402
from pplate.models.enums import CarSource  # noqa: E402
from pplate.schemas import CarCreate  # noqa: E402
from pplate.services.car_service import create_car, update_car, apply_compliance  # noqa: E402
from pplate.schemas import CarUpdate  # noqa: E402

SEED_CARS: list[dict] = [
    # --- Compliant (comfortably under 130 kW/t) ---------------------------
    dict(make="Toyota", model="Corolla", variant="Ascent", year=2016, engine_size_cc=1798, power_kw=103, weight_kg=1280, body_type="hatch", fuel_type="petrol", transmission="CVT", price_aud=13500, odometer_km=92000, location="Werribee VIC", safety_rating_stars=5.0, safety_rating_year=2014, recommended=True, notes="Reliable, cheap to service, 5-star ANCAP."),
    dict(make="Mazda", model="Mazda3", variant="Maxx", year=2017, engine_size_cc=1998, power_kw=114, weight_kg=1270, body_type="hatch", fuel_type="petrol", transmission="automatic", price_aud=16900, odometer_km=78000, location="Dandenong VIC", safety_rating_stars=5.0, safety_rating_year=2014, recommended=True, notes="Sharp handling, quality interior."),
    dict(make="Hyundai", model="i30", variant="Active", year=2015, engine_size_cc=1797, power_kw=107, weight_kg=1290, body_type="hatch", fuel_type="petrol", transmission="automatic", price_aud=11900, odometer_km=105000, location="Geelong VIC", safety_rating_stars=5.0, safety_rating_year=2013, recommended=True, notes="Great value, roomy, cheap parts."),
    dict(make="Kia", model="Rio", variant="Si", year=2016, engine_size_cc=1396, power_kw=74, weight_kg=1120, body_type="hatch", fuel_type="petrol", transmission="automatic", price_aud=10500, odometer_km=88000, location="Frankston VIC", safety_rating_stars=4.0, safety_rating_year=2011, recommended=True, notes="Tiny running costs."),
    dict(make="Suzuki", model="Swift", variant="GL", year=2017, engine_size_cc=1242, power_kw=70, weight_kg=990, body_type="hatch", fuel_type="petrol", transmission="automatic", price_aud=11900, odometer_km=64000, location="Bundoora VIC", safety_rating_stars=5.0, safety_rating_year=2011, recommended=True, notes="Light, frugal, fun."),
    dict(make="Honda", model="Jazz", variant="VTi", year=2015, engine_size_cc=1497, power_kw=88, weight_kg=1060, body_type="hatch", fuel_type="petrol", transmission="CVT", price_aud=11500, odometer_km=98000, location="Sunshine VIC", safety_rating_stars=5.0, safety_rating_year=2008, recommended=True, notes="Magic seats, big interior."),
    dict(make="Hyundai", model="Accent", variant="Active", year=2016, engine_size_cc=1591, power_kw=91, weight_kg=1150, body_type="hatch", fuel_type="petrol", transmission="automatic", price_aud=10900, odometer_km=72000, location="Ringwood VIC", safety_rating_stars=5.0, safety_rating_year=2011, recommended=True, notes="Cheap to buy and run."),
    dict(make="Nissan", model="Pulsar", variant="ST", year=2015, engine_size_cc=1798, power_kw=96, weight_kg=1240, body_type="hatch", fuel_type="petrol", transmission="CVT", price_aud=10500, odometer_km=91000, location="Berwick VIC", safety_rating_stars=5.0, safety_rating_year=2014, recommended=True, notes="Roomy, 5-star, cheap."),
    dict(make="Kia", model="Cerato", variant="Si", year=2016, engine_size_cc=1999, power_kw=112, weight_kg=1300, body_type="sedan", fuel_type="petrol", transmission="automatic", price_aud=12900, odometer_km=84000, location="Craigieburn VIC", safety_rating_stars=5.0, safety_rating_year=2013, recommended=True, notes="Spacious, 5-star."),
    dict(make="Toyota", model="Camry", variant="Altise", year=2015, engine_size_cc=2494, power_kw=133, weight_kg=1470, body_type="sedan", fuel_type="petrol", transmission="automatic", price_aud=13900, odometer_km=112000, location="Epping VIC", safety_rating_stars=5.0, safety_rating_year=2011, recommended=True, notes="Comfortable, roomy."),
    dict(make="Mazda", model="Mazda2", variant="Neo", year=2015, engine_size_cc=1496, power_kw=79, weight_kg=1030, body_type="hatch", fuel_type="petrol", transmission="automatic", price_aud=10900, odometer_km=76000, location="Werribee VIC", safety_rating_stars=4.0, safety_rating_year=2014, recommended=True, notes="Nippy, frugal."),
    dict(make="Toyota", model="Yaris", variant="Ascent", year=2015, engine_size_cc=1298, power_kw=63, weight_kg=1000, body_type="hatch", fuel_type="petrol", transmission="automatic", price_aud=9900, odometer_km=81000, location="Dandenong VIC", safety_rating_stars=5.0, safety_rating_year=2011, recommended=True, notes="Toyota reliability, cheap."),
    dict(make="Ford", model="Falcon", variant="XR6", year=2014, engine_size_cc=3984, power_kw=195, weight_kg=1704, body_type="sedan", fuel_type="petrol", transmission="automatic", cylinders=6, price_aud=12900, odometer_km=160000, location="Melbourne VIC", safety_rating_stars=5.0, safety_rating_year=2010, notes="Surprise example: a six-cylinder that is still under 130 kW/t (no cylinder ban in Victoria)."),
    # --- Borderline -> "verify" (120-130 kW/t by kerb weight) --------------
    dict(make="Holden", model="Commodore", variant="SV6", year=2014, engine_size_cc=3564, power_kw=210, weight_kg=1750, body_type="sedan", fuel_type="petrol", transmission="automatic", cylinders=6, price_aud=16900, odometer_km=140000, location="Melbourne VIC", safety_rating_stars=5.0, safety_rating_year=2013, notes="Borderline: verify against official database / tare mass."),
    # --- Non-compliant -----------------------------------------------------
    dict(make="Subaru", model="WRX", variant="Premium", year=2015, engine_size_cc=1998, power_kw=195, weight_kg=1455, body_type="sedan", fuel_type="petrol", transmission="manual", price_aud=26000, odometer_km=88000, location="Melbourne VIC", safety_rating_stars=5.0, safety_rating_year=2014, notes="High-performance turbo; over the limit."),
    dict(make="Honda", model="Civic", variant="Type R", year=2018, engine_size_cc=1996, power_kw=228, weight_kg=1380, body_type="hatch", fuel_type="petrol", transmission="manual", price_aud=42000, odometer_km=56000, location="Melbourne VIC", safety_rating_stars=5.0, safety_rating_year=2017, notes="Hot hatch; well over the limit."),
    dict(make="Volkswagen", model="Golf", variant="R", year=2016, engine_size_cc=1984, power_kw=221, weight_kg=1435, body_type="hatch", fuel_type="petrol", transmission="dual-clutch", price_aud=32000, odometer_km=79000, location="Melbourne VIC", safety_rating_stars=5.0, safety_rating_year=2014, notes="Performance AWD; banned for P-platers."),
    dict(make="Mazda", model="MX-5", variant="Roadster", year=2016, engine_size_cc=1998, power_kw=135, weight_kg=1058, body_type="convertible", fuel_type="petrol", transmission="manual", price_aud=24900, odometer_km=68000, location="Melbourne VIC", safety_rating_stars=4.0, safety_rating_year=2015, notes="Light sports car; verify - often over the limit."),
    dict(make="Honda", model="Civic", variant="Type R (modified)", year=2018, engine_size_cc=1996, power_kw=228, weight_kg=1380, body_type="hatch", fuel_type="petrol", transmission="manual", price_aud=40000, odometer_km=56000, location="Melbourne VIC", safety_rating_stars=5.0, safety_rating_year=2017, modified=True, modification_notes="Aftermarket ECU tune and exhaust", notes="Modified example."),
    dict(make="Toyota", model="Corolla", variant="Ascent (modified)", year=2015, engine_size_cc=1798, power_kw=103, weight_kg=1280, body_type="hatch", fuel_type="petrol", transmission="manual", price_aud=12000, odometer_km=99000, location="Melbourne VIC", safety_rating_stars=5.0, safety_rating_year=2014, modified=True, modification_notes="Aftermarket turbo kit installed", notes="Performance-modification example: non-compliant even though power-to-weight is low."),
]


def main() -> None:
    init_db()
    db = SessionLocal()
    inserted = updated = 0
    try:
        for i, spec in enumerate(SEED_CARS, start=1):
            external_id = f"seed:{i}"
            existing = db.scalar(select(Car).where(Car.external_id == external_id))
            if existing:
                update_car(db, existing, CarUpdate(**spec))
                updated += 1
            else:
                car = Car(**spec, source=CarSource.MANUAL, external_id=external_id)
                apply_compliance(car)
                db.add(car)
                db.commit()
                inserted += 1
        print(f"Seed complete: {inserted} inserted, {updated} updated ({len(SEED_CARS)} total).")
    finally:
        db.close()


if __name__ == "__main__":
    main()
