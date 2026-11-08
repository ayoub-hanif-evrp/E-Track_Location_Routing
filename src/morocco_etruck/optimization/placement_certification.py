"""Certification statuses and serviceability taxonomy (Task 04B)."""

from __future__ import annotations

from enum import Enum


class OptimalityStatus(str, Enum):
    CERTIFIED_OPTIMAL = "CERTIFIED_OPTIMAL"
    INCUMBENT_UNPROVED = "INCUMBENT_UNPROVED"
    NO_FEASIBLE = "NO_FEASIBLE"
    LIMIT_REACHED = "LIMIT_REACHED"


class ServiceabilityClass(str, Enum):
    SERVICEABLE = "serviceable"
    PEAK_MOTOR = "peak_motor"
    UNSERVED_ALL_CANDIDATES = "unserved_all_candidates"
    LIMIT_REACHED = "limit_reached"
    REPLAY_INVALID = "replay_invalid"


def is_peak_motor_reason(reason: str | None) -> bool:
    if not reason:
        return False
    r = reason.lower()
    return "peak_motor" in r or "peak_power" in r or "power_exceeded" in r
