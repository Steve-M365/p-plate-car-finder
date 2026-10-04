"""JSON API for car CRUD, search, filtering and statistics."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from pplate.db import get_db
from pplate.schemas import CarCreate, CarFilter, CarOut, CarUpdate, StatsOut
from pplate.services import car_service

router = APIRouter(prefix="/api/cars", tags=["cars"])


@router.get("", response_model=list[CarOut])
def list_cars(filters: CarFilter = Depends(), db: Session = Depends(get_db)):
    """Search/filter cars.

    Query params: ``q, min_price, max_price, body_type, fuel_type, transmission,
    min_safety, compliance (compliant|non_compliant|unknown), recommended, source,
    sort, limit, offset``.
    """
    return car_service.get_cars(db, filters)


@router.post("", response_model=CarOut, status_code=status.HTTP_201_CREATED)
def create_car(payload: CarCreate, db: Session = Depends(get_db)):
    return car_service.create_car(db, payload)


@router.get("/stats", response_model=StatsOut)
def car_stats(db: Session = Depends(get_db)):
    return car_service.stats(db)


@router.get("/{car_id}", response_model=CarOut)
def get_car(car_id: int, db: Session = Depends(get_db)):
    car = car_service.get_car(db, car_id)
    if car is None:
        raise HTTPException(status_code=404, detail="Car not found")
    return car


@router.put("/{car_id}", response_model=CarOut)
def update_car(car_id: int, payload: CarUpdate, db: Session = Depends(get_db)):
    car = car_service.get_car(db, car_id)
    if car is None:
        raise HTTPException(status_code=404, detail="Car not found")
    return car_service.update_car(db, car, payload)


@router.patch("/{car_id}", response_model=CarOut)
def patch_car(car_id: int, payload: CarUpdate, db: Session = Depends(get_db)):
    car = car_service.get_car(db, car_id)
    if car is None:
        raise HTTPException(status_code=404, detail="Car not found")
    return car_service.update_car(db, car, payload)


@router.delete("/{car_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_car(car_id: int, db: Session = Depends(get_db)):
    car = car_service.get_car(db, car_id)
    if car is None:
        raise HTTPException(status_code=404, detail="Car not found")
    car_service.delete_car(db, car)
    return None


@router.post("/{car_id}/recheck", response_model=CarOut)
def recheck_car(car_id: int, db: Session = Depends(get_db)):
    """Recalculate the Victorian P-plate compliance fields for one car."""
    car = car_service.get_car(db, car_id)
    if car is None:
        raise HTTPException(status_code=404, detail="Car not found")
    car_service.apply_compliance(car)
    db.add(car)
    db.commit()
    db.refresh(car)
    return car
