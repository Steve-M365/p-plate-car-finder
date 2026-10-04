"""Return type for the P-plate compliance evaluation."""

from __future__ import annotations

from dataclasses import dataclass

from pplate.models.enums import ComplianceStatus


@dataclass(slots=True)
class ComplianceResult:
    status: ComplianceStatus
    reason: str
    power_to_weight: float | None = None
    listed_high_performance: bool = False
    borderline: bool = False

    @property
    def compliant(self) -> bool:
        return self.status is ComplianceStatus.COMPLIANT

    def as_dict(self) -> dict:
        return {
            "status": self.status.value,
            "compliant": self.compliant,
            "reason": self.reason,
            "power_to_weight": self.power_to_weight,
            "listed_high_performance": self.listed_high_performance,
            "borderline": self.borderline,
        }
