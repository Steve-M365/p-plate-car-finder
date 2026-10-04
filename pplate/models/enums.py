"""Shared enums / constants for the data model."""

from __future__ import annotations

import enum


class ComplianceStatus(str, enum.Enum):
    """Result of the Victorian P-plate compliance check."""

    COMPLIANT = "compliant"
    NON_COMPLIANT = "non_compliant"
    UNKNOWN = "unknown"


class CarSource(str, enum.Enum):
    """Where a car record came from."""

    MANUAL = "manual"
    RECOMMENDATION = "recommendation"
    CARSALES = "carsales"
    MARKETPLACE = "marketplace"
    CSV = "csv"
    MOCK = "mock"
    FEED = "feed"
    EBAY = "ebay"
    CAPTURE = "capture"


# Canonical body types / fuel types / transmissions used for filtering.
BODY_TYPES = [
    "hatch",
    "sedan",
    "wagon",
    "SUV",
    "ute",
    "coupe",
    "convertible",
    "van",
    "people mover",
]

FUEL_TYPES = ["petrol", "diesel", "hybrid", "electric", "LPG"]

TRANSMISSIONS = ["automatic", "manual", "CVT", "dual-clutch"]
