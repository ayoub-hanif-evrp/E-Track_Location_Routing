"""Certification statuses and serviceability taxonomy (Task 04B)."""

from __future__ import annotations

from enum import Enum


class OptimalityStatus(str, Enum):
    CERTIFIED_OPTIMAL = "CERTIFIED_OPTIMAL"
    INCUMBENT_UNPROVED = "INCUMBENT_UNPROVED"
    NO_FEASIBLE = "NO_FEASIBLE"
    LIMIT_REACHED = "LIMIT_REACHED"
    # Task 06C: full portfolio cannot be certified when a demand mission is unresolved.
    UNRESOLVED_SERVICEABILITY = "UNRESOLVED_SERVICEABILITY"
    # Discrete optimum only over an explicitly restricted mission subset.
    CONDITIONAL_RESTRICTED_PORTFOLIO = "CONDITIONAL_RESTRICTED_PORTFOLIO"


class ServiceabilityClass(str, Enum):
    SERVICEABLE = "serviceable"
    PEAK_MOTOR = "peak_motor"
    UNSERVED_ALL_CANDIDATES = "unserved_all_candidates"
    LIMIT_REACHED = "limit_reached"
    REPLAY_INVALID = "replay_invalid"


# Statuses for which serviceability has not been proved at the all-sites probe.
UNRESOLVED_SERVICEABILITY_VALUES = frozenset(
    {
        ServiceabilityClass.LIMIT_REACHED.value,
        "limit_reached",
        ServiceabilityClass.REPLAY_INVALID.value,
        "replay_invalid",
        "prep_failed",
        "graph_failed",
        "physics_input_failed",
        "unresolved",
    }
)


def is_unresolved_serviceability(status: str | None) -> bool:
    if status is None:
        return False
    return str(status).lower() in UNRESOLVED_SERVICEABILITY_VALUES


def portfolio_optimality_status(
    *,
    core_status: OptimalityStatus,
    serviceability: dict[str, str],
) -> OptimalityStatus:
    """
    Downgrade full-portfolio CERTIFIED_OPTIMAL when any mission is unresolved
    at the all-sites serviceability probe (LIMIT_REACHED, replay_invalid, prep failure).
    """
    unresolved = {
        mid for mid, v in serviceability.items() if is_unresolved_serviceability(v)
    }
    if not unresolved:
        return core_status
    if core_status == OptimalityStatus.CERTIFIED_OPTIMAL:
        return OptimalityStatus.CONDITIONAL_RESTRICTED_PORTFOLIO
    if core_status in {OptimalityStatus.INCUMBENT_UNPROVED, OptimalityStatus.LIMIT_REACHED}:
        return OptimalityStatus.UNRESOLVED_SERVICEABILITY
    return core_status


def is_peak_motor_reason(reason: str | None) -> bool:
    if not reason:
        return False
    r = reason.lower()
    return "peak_motor" in r or "peak_power" in r or "power_exceeded" in r
