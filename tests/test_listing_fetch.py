"""Integration test for the listing fetch + compliance tagging pipeline.

Uses an isolated in-memory SQLite database so it never touches the dev DB.
"""

from __future__ import annotations

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from pplate.db.base import Base
from pplate.models import Car
from pplate.models.enums import ComplianceStatus
from pplate.services.listing_fetch import fetch_listings


def _session():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def test_mock_fetch_inserts_and_tags_compliance():
    db = _session()
    result = fetch_listings(db, provider="mock", limit=8)

    assert result["fetched"] == 8
    assert result["inserted"] == 8
    assert result["status"] == "ok"

    cars = db.scalars(select(Car)).all()
    assert len(cars) == 8
    # Every row must carry a compliance reason and a valid status.
    assert all(c.p_plate_reason for c in cars)
    assert all(c.p_plate_compliant in ComplianceStatus for c in cars)
    # A realistic mock sample should include more than one category.
    statuses = {c.p_plate_compliant for c in cars}
    assert statuses.issubset(set(ComplianceStatus))
    assert ComplianceStatus.COMPLIANT in statuses


def test_mock_fetch_is_idempotent_by_external_id():
    db = _session()
    fetch_listings(db, provider="mock", limit=8)
    second = fetch_listings(db, provider="mock", limit=8)
    assert second["inserted"] == 0
    assert second["updated"] == 8
    assert len(db.scalars(select(Car)).all()) == 8
