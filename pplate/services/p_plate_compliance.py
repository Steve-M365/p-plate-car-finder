"""Victorian P-plate (probationary) vehicle compliance logic.

THE RULES THIS IMPLEMENTS (verified from Transport Victoria / VicRoads, re-checked October 2026)
===============================================================================
Victoria restricts which cars a probationary (P1 or P2) driver may drive.
A car is a "probationary prohibited vehicle" (PPV) if ANY of the following:

1. It has a **"banned" rating** in the Victorian *probationary vehicle
   database* (administered via vicroadssafevehicles.carsalesnetwork.com.au).
2. Its **power-to-mass ratio exceeds 130 kW per tonne** of *tare* mass
   (tare mass is the unladen mass without fuel/load and is slightly LIGHTER
   than the kerb weight most listings quote, which means the official ratio is
   slightly HIGHER than one calculated from kerb weight).
3. Its **engine has been modified to increase performance**, unless the
   modification was performed by the manufacturer when the vehicle was built.

Notes and common misconceptions
-------------------------------
* The old absolute power cap (~125/149 kW) and the blanket turbo / V8 / rotary
  bans are **obsolete** in Victoria. Since 29 October 2019 Victoria uses the
  power-to-mass test plus the banned-vehicle database.
* The 130 kW/tonne limit applies to **both P1 and P2** and to **all ages** in
  Victoria (unlike QLD/SA where it only applies to under-25s).
* Learner permit holders, full licence holders and overseas licence holders are
  NOT subject to the prohibited-vehicle rule. This tool is aimed at P1/P2.
* Exemptions exist (supervising driver, work-related automatic exemption, and
  undue-hardship approval) - see `RULES_SOURCE_URLS`.

IMPORTANT - this is decision-support, not legal advice. The authoritative check
for a specific make/model/variant is the Victorian probationary vehicle database
or VicRoads. Where data is missing or borderline this module returns "unknown"
rather than a false "compliant".
"""

from __future__ import annotations

import re
from typing import Any

from pplate.config import get_settings
from pplate.models.enums import ComplianceStatus
from pplate.services.compliance_types import ComplianceResult

# ---------------------------------------------------------------------------
# Source references (also surfaced in the UI + README)
# ---------------------------------------------------------------------------
PPV_DATABASE_URL = "https://vicroadssafevehicles.carsalesnetwork.com.au/#/search"

RULES_SOURCE_URLS: list[str] = [
    # Primary government source for the prohibited-vehicle rule.
    "https://transport.vic.gov.au/road-and-active-transport/registration-and-licensing/licences/probationary-licence/vehicles-for-probationary-drivers",
    # VicRoads landing page for P-plate drivers.
    "https://www.vicroads.vic.gov.au/ls-and-ps/driving-on-your-ps",
    # The database used for Approved / Banned / Under review decisions.
    PPV_DATABASE_URL,
    # Official exemptions (supervising driver / work / undue hardship).
    "https://transport.vic.gov.au/road-and-active-transport/registration-and-licensing/licences/probationary-licence/exemptions-to-drive-a-prohibited-vehicle",
    # Road Safety (Drivers) Regulations 2019 (Vic), reg 57 (high-powered mods).
    "https://www4.austlii.edu.au/au/legis/vic/num_reg/rsr2019n100o2019403/s57.html",
    # Reputable industry summaries (carsales, VACC on EVs).
    "https://www.carsales.com.au/editorial/details/p-plate-prohibited-vehicles-update-100374/",
    "https://motortech.com.au/can-i-drive-an-ev-on-my-p-plates-yes-and-no/",
]

RULES_SUMMARY = (
    "In Victoria a probationary (P1/P2) driver may not drive a vehicle that: "
    "(1) is rated 'banned' in the Victorian probationary vehicle database, or "
    "(2) has a power-to-mass ratio greater than 130 kW per tonne of tare mass, or "
    "(3) has a performance-increasing engine modification (unless done by the "
    "manufacturer at build). The 130 kW/tonne limit applies to both P1 and P2 "
    "regardless of age, and applies equally to electric vehicles - many "
    "single-motor EVs are under the limit while dual-motor/performance variants "
    "are not. Learner, full and overseas licence holders are exempt. Exemptions "
    "exist for supervising drivers, work use and undue hardship."
)

# ---------------------------------------------------------------------------
# Conservative high-performance model knowledge base
# ---------------------------------------------------------------------------
# These are widely-documented performance variants that commonly exceed
# 130 kW/t and/or attract attention in the state checkers. Matching is a
# SECONDARY, conservative heuristic layered on top of the maths - the maths is
# the primary test. The authoritative answer is always the official database.
#
# Each entry: (regex applied to "make model variant" lowercased, human note)
_LISTED_HIGH_PERFORMANCE: list[tuple[str, str]] = [
    (r"\bgolf\s+(?:gti|r)(?![\w-])", "Volkswagen Golf GTI/R hot hatch"),
    (r"\bpolo\s+gti\b", "Volkswagen Polo GTI (often borderline)"),
    (r"\b(scirocco\s+r|passat\s+r36)\b", "Volkswagen performance variant"),
    (r"\bgr\s+(yaris|corolla|86|supra)\b", "Toyota GR performance model"),
    (r"\btoyota\s+(supra|gr86)\b", "Toyota sports model"),
    (r"\bsubaru\s+(wrx|sti|brz)\b", "Subaru WRX/STI/BRZ"),
    (r"\bi30\s+n(?![\w-])|\bi20\s+n(?![\w-])|\bveloster\s+n(?![\w-])", "Hyundai N performance model"),
    (r"\bhonda\s+civic\s+type\s*r\b", "Honda Civic Type R"),
    (r"\btesla\s+model\s+(3|s|x|y)\b.*(performance|long\s*range|plaid)", "Tesla performance/long-range variant"),
    (r"\bmg4\s+xpower\b", "MG4 XPower"),
    (r"\b(byd\s+)?seal\s+.*(performance|awd)\b", "BYD Seal performance/AWD variant"),
    (r"\bmustang\b", "Ford Mustang"),
    (r"\bfocus\s+(rs|st)\b", "Ford Focus RS/ST"),
    (r"\bfiesta\s+st\b", "Ford Fiesta ST"),
    (r"\b(falcon|commodore)\s+(xr8|gt|gt-f|ss|ssv|r8|hsv)\b", "Australian V8 performance"),
    (r"\bhsv\b", "HSV performance vehicle"),
    (r"\bcommodore\s+ss\b", "Holden Commodore SS"),
    (r"\bbmw\s+m[0-9]", "BMW M performance model"),
    (r"\b(m2|m3|m4|m5|m135i|m140i|m240i|m340i|z4)\b", "BMW performance model"),
    (r"\baudi\s+(s3|s4|s5|rs3|rs4|rs5|rs6|tt\s+rs)\b", "Audi S/RS performance model"),
    (r"\bamg\b|\ba45\b|\bc63\b|\bcla45\b", "Mercedes-AMG performance model"),
    (r"\b(370z|350z|gt-?r|skyline)\b", "Nissan sports model"),
    (r"\bmazda\s+mx-?5\b", "Mazda MX-5 (often borderline - verify)"),
    (r"\bkia\s+stinger\b", "Kia Stinger"),
    (r"\b(renault\s+)?megane\s+rs\b|\bclio\s+rs\b", "Renault Sport hot hatch"),
    (r"\bpeugeot\s+308\s+gti\b", "Peugeot 308 GTI"),
    (r"\bskoda\s+octavia\s+rs\b", "Skoda Octavia RS"),
    (r"\b(lexus\s+(is\s*f|rc\s*f|gs\s*f)|isf|rcf)\b", "Lexus F performance model"),
    (r"\bvolvo\s+.*polestar\b", "Volvo Polestar performance variant"),
    (r"\bmini\s+(cooper\s+)?(jcw|john\s+cooper\s+works)\b", "MINI JCW"),
    (r"\bchevrolet\s+camaro\b|\bcamaro\b", "Chevrolet Camaro"),
]

_COMPILED_LIST = [(re.compile(pattern, re.IGNORECASE), note) for pattern, note in _LISTED_HIGH_PERFORMANCE]


def compute_power_to_weight(power_kw: float | None, weight_kg: int | None) -> float | None:
    """Return kW per tonne, or None if either input is missing/invalid."""
    if power_kw is None or weight_kg is None:
        return None
    try:
        power = float(power_kw)
        weight = float(weight_kg)
    except (TypeError, ValueError):
        return None
    if power <= 0 or weight <= 0:
        return None
    return round(power / (weight / 1000.0), 1)


def known_high_performance_match(make: str, model: str, variant: str | None) -> str | None:
    """Return a human note if the car matches the conservative performance list."""
    haystack = " ".join(part for part in (make, model, variant) if part).lower()
    for pattern, note in _COMPILED_LIST:
        if pattern.search(haystack):
            return note
    return None


def _get(car: Any, key: str) -> Any:
    """Read a field from either an ORM object or a dict-like mapping."""
    if isinstance(car, dict):
        return car.get(key)
    return getattr(car, key, None)


def evaluate(car: Any) -> ComplianceResult:
    """Evaluate a car (ORM object or mapping) against the Victorian rules.

    Order of checks (most authoritative first):
      1. Performance-increasing engine modification  -> non_compliant
      2. Listed high-performance model (heuristic)    -> non_compliant
      3. Configured absolute power cap (legacy/off)   -> non_compliant if set
      4. Power-to-mass ratio maths                    -> compliant / borderline / non
    """
    settings = get_settings()

    make = (_get(car, "make") or "").strip()
    model = (_get(car, "model") or "").strip()
    variant = (_get(car, "variant") or "").strip() or None
    power_kw = _get(car, "power_kw")
    weight_kg = _get(car, "weight_kg")
    modified = bool(_get(car, "modified"))
    mod_notes = _get(car, "modification_notes")
    listed_flag = bool(_get(car, "listed_high_performance"))

    limit = float(settings.pplate_power_to_mass_limit)
    borderline_lower = float(settings.pplate_borderline_lower)
    absolute_cap = settings.pplate_absolute_power_limit_kw

    ratio = compute_power_to_weight(power_kw, weight_kg)

    # 1. Performance engine modification -----------------------------------
    if modified:
        detail = f" ({mod_notes})" if mod_notes else ""
        return ComplianceResult(
            status=ComplianceStatus.NON_COMPLIANT,
            reason=(
                "Likely non-compliant - engine modified to increase performance"
                f"{detail}. Only factory performance modifications are permitted."
            ),
            power_to_weight=ratio,
        )

    # 2. Known high-performance model (heuristic) --------------------------
    match_note = known_high_performance_match(make, model, variant) if (make or model) else None
    if listed_flag or match_note:
        note = match_note or "listed high-performance model"
        return ComplianceResult(
            status=ComplianceStatus.NON_COMPLIANT,
            reason=(
                f"Likely non-compliant - recognised high-performance model ({note}); "
                "commonly exceeds the power-to-mass limit. Confirm on the official "
                "probationary vehicle database."
            ),
            power_to_weight=ratio,
            listed_high_performance=True,
        )

    # 3. Optional legacy absolute power cap (disabled by default) ----------
    if absolute_cap is not None and power_kw is not None and float(power_kw) > float(absolute_cap):
        return ComplianceResult(
            status=ComplianceStatus.NON_COMPLIANT,
            reason=(
                f"Likely non-compliant - engine power {float(power_kw):.0f} kW exceeds the "
                f"configured {float(absolute_cap):.0f} kW threshold."
            ),
            power_to_weight=ratio,
        )

    # 4. Power-to-mass maths -----------------------------------------------
    if ratio is None:
        missing = []
        if power_kw is None:
            missing.append("power (kW)")
        if weight_kg is None:
            missing.append("weight (kg)")
        return ComplianceResult(
            status=ComplianceStatus.UNKNOWN,
            reason=(
                "Unknown - missing " + " and ".join(missing) + ". Cannot confirm the "
                "power-to-mass ratio; check the official probationary vehicle database."
            ),
            power_to_weight=None,
        )

    # Note: ratio here is computed from the KERB weight we hold. Tare mass is
    # lighter, so the official ratio is slightly HIGHER. We therefore treat the
    # band just under the limit as "borderline / verify".
    if ratio >= limit:
        return ComplianceResult(
            status=ComplianceStatus.NON_COMPLIANT,
            reason=(
                f"Likely non-compliant - power-to-mass ratio ~{ratio:.1f} kW/t "
                f"(kerb-weight estimate) exceeds the {limit:.0f} kW/tonne limit."
            ),
            power_to_weight=ratio,
        )

    if ratio >= borderline_lower:
        return ComplianceResult(
            status=ComplianceStatus.UNKNOWN,
            reason=(
                f"Borderline - power-to-mass ratio ~{ratio:.1f} kW/t using kerb weight "
                f"(limit {limit:.0f} kW/t). The official calculation uses lighter tare "
                "mass, so this may exceed the limit. Verify on the official database."
            ),
            power_to_weight=ratio,
            borderline=True,
        )

    return ComplianceResult(
        status=ComplianceStatus.COMPLIANT,
        reason=(
            f"Likely compliant - power-to-mass ratio ~{ratio:.1f} kW/t (kerb-weight "
            f"estimate), comfortably under the {limit:.0f} kW/tonne limit."
        ),
        power_to_weight=ratio,
    )


def check_p_plate_compliance(car: Any) -> dict:
    """Backwards-friendly wrapper returning a plain dict.

    Returns ``{"compliant": bool, "status": str, "reason": str, ...}``.
    """
    return evaluate(car).as_dict()
