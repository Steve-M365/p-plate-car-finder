"""Car CRUD, filtering, statistics and compliance application."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from pplate.models import Car
from pplate.models.enums import ComplianceStatus
from pplate.schemas import CarCreate, CarFilter, CarUpdate
from pplate.services.p_plate_compliance import evaluate


def apply_compliance(car: Car) -> Car:
    """Recalculate and persist the P-plate fields for a car."""
    result = evaluate(car)
    car.power_to_weight = result.power_to_weight
    car.p_plate_compliant = result.status
    car.p_plate_reason = result.reason
    car.listed_high_performance = result.listed_high_performance
    return car


def create_car(db: Session, data: CarCreate) -> Car:
    car = Car(**data.model_dump())
    apply_compliance(car)
    db.add(car)
    db.commit()
    db.refresh(car)
    return car


def update_car(db: Session, car: Car, data: CarUpdate) -> Car:
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(car, field, value)
    apply_compliance(car)
    db.add(car)
    db.commit()
    db.refresh(car)
    return car


def delete_car(db: Session, car: Car) -> None:
    db.delete(car)
    db.commit()


def get_car(db: Session, car_id: int) -> Car | None:
    return db.get(Car, car_id)


_SORT_MAP = {
    "price_asc": (Car.price_aud.asc().nulls_last(), Car.id.asc()),
    "price_desc": (Car.price_aud.desc().nulls_last(), Car.id.asc()),
    "year_desc": (Car.year.desc().nulls_last(), Car.id.asc()),
    "year_asc": (Car.year.asc().nulls_last(), Car.id.asc()),
    "safety_desc": (Car.safety_rating_stars.desc().nulls_last(), Car.id.asc()),
    "power_asc": (Car.power_kw.asc().nulls_last(), Car.id.asc()),
    "make_asc": (Car.make.asc(), Car.model.asc()),
    "created_desc": (Car.created_at.desc(),),
}


def get_cars(db: Session, filters: CarFilter) -> list[Car]:
    stmt = select(Car)

    if filters.q:
        like = f"%{filters.q.strip()}%"
        stmt = stmt.where(
            (Car.make.ilike(like))
            | (Car.model.ilike(like))
            | (Car.variant.ilike(like))
            | (Car.notes.ilike(like))
        )
    if filters.min_price is not None:
        stmt = stmt.where(Car.price_aud >= filters.min_price)
    if filters.max_price is not None:
        stmt = stmt.where(Car.price_aud <= filters.max_price)
    if filters.body_type:
        stmt = stmt.where(Car.body_type == filters.body_type)
    if filters.fuel_type:
        stmt = stmt.where(Car.fuel_type == filters.fuel_type)
    if filters.transmission:
        stmt = stmt.where(Car.transmission == filters.transmission)
    if filters.min_safety is not None:
        stmt = stmt.where(Car.safety_rating_stars >= filters.min_safety)
    if filters.compliance is not None:
        stmt = stmt.where(Car.p_plate_compliant == filters.compliance)
    if filters.recommended is not None:
        stmt = stmt.where(Car.recommended == filters.recommended)
    if filters.source:
        stmt = stmt.where(Car.source == filters.source)

    order = _SORT_MAP.get(filters.sort, _SORT_MAP["price_asc"])
    stmt = stmt.order_by(*order).limit(filters.limit).offset(filters.offset)
    return list(db.scalars(stmt).all())


def stats(db: Session) -> dict:
    total = db.scalar(select(func.count(Car.id))) or 0
    compliant = (
        db.scalar(
            select(func.count(Car.id)).where(Car.p_plate_compliant == ComplianceStatus.COMPLIANT)
        )
        or 0
    )
    non_compliant = (
        db.scalar(
            select(func.count(Car.id)).where(Car.p_plate_compliant == ComplianceStatus.NON_COMPLIANT)
        )
        or 0
    )
    unknown = total - compliant - non_compliant
    recommended = db.scalar(select(func.count(Car.id)).where(Car.recommended.is_(True))) or 0
    return {
        "total": total,
        "compliant": compliant,
        "non_compliant": non_compliant,
        "unknown": unknown,
        "recommended": recommended,
    }
