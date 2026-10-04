"""Tests for the Victorian P-plate compliance engine."""

from __future__ import annotations

from pplate.models.enums import ComplianceStatus
from pplate.services.p_plate_compliance import compute_power_to_weight, evaluate


def base(**over) -> dict:
    car = {
        "make": "Toyota",
        "model": "Corolla",
        "variant": "Ascent",
        "power_kw": 103,
        "weight_kg": 1280,
    }
    car.update(over)
    return car


def test_power_to_weight_maths():
    assert compute_power_to_weight(100, 1000) == 100.0
    assert compute_power_to_weight(None, 1000) is None
    assert compute_power_to_weight(100, None) is None
    assert compute_power_to_weight(0, 1000) is None


def test_comfortably_compliant():
    result = evaluate(base())
    assert result.status is ComplianceStatus.COMPLIANT
    assert result.compliant


def test_over_power_to_weight_limit_is_non_compliant():
    # 200 kW / 1.0 t = 200 kW/t
    result = evaluate(base(power_kw=200, weight_kg=1000))
    assert result.status is ComplianceStatus.NON_COMPLIANT


def test_borderline_is_unknown_not_compliant():
    # 125 kW / 1.0 t = 125 kW/t -> inside the 120-130 border band
    result = evaluate(base(power_kw=125, weight_kg=1000))
    assert result.status is ComplianceStatus.UNKNOWN
    assert result.borderline


def test_missing_power_is_unknown():
    result = evaluate(base(power_kw=None))
    assert result.status is ComplianceStatus.UNKNOWN


def test_missing_weight_is_unknown():
    result = evaluate(base(weight_kg=None))
    assert result.status is ComplianceStatus.UNKNOWN


def test_performance_modification_is_non_compliant():
    result = evaluate(base(modified=True, modification_notes="turbo kit"))
    assert result.status is ComplianceStatus.NON_COMPLIANT
    assert "modified" in result.reason.lower()


def test_listed_high_performance_model_is_non_compliant():
    result = evaluate(
        {"make": "Volkswagen", "model": "Golf", "variant": "R", "power_kw": 221, "weight_kg": 1435}
    )
    assert result.status is ComplianceStatus.NON_COMPLIANT
    assert result.listed_high_performance


def test_absolute_power_cap_disabled_by_default():
    # A high-power but heavy car under 130 kW/t is compliant while the cap is off.
    # 150 kW / 1.5 t = 100 kW/t
    result = evaluate(base(power_kw=150, weight_kg=1500))
    assert result.status is ComplianceStatus.COMPLIANT


def test_golf_r_line_not_flagged_as_golf_r():
    # "R-Line" is cosmetic, must not match the "Golf R" pattern.
    result = evaluate(
        {"make": "Volkswagen", "model": "Golf", "variant": "R-Line", "power_kw": 110, "weight_kg": 1350}
    )
    assert result.status is ComplianceStatus.COMPLIANT
