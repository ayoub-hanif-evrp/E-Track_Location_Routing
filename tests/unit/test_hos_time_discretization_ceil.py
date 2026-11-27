"""Regression: HOS continuous-driving ceil inflation vs physical duration."""
from __future__ import annotations

import math

# Volvo Marrakech→Agadir energy-optimal DRIVE arcs (P0), minutes
VOLVO_MA_ARC_PHYS_MIN = [1.26048, 12.551617, 50.681036, 195.688628, 5.434017]


def discrete_drive_minutes_per_arc(arc_phys_minutes: list[float], timestep_min: float) -> float:
    """Sum of per-arc ceil(dt/ts)*ts — the HOS-in-search accumulation mechanism."""
    total = 0.0
    for dt in arc_phys_minutes:
        total += float(math.ceil(dt / timestep_min) * timestep_min)
    return total


def test_volvo_ma_physical_under_limit_ceil_over_at_5min():
    phys = sum(VOLVO_MA_ARC_PHYS_MIN)
    limit = 270.0
    assert abs(phys - 265.615779) < 1e-5
    assert phys < limit
    disc5 = discrete_drive_minutes_per_arc(VOLVO_MA_ARC_PHYS_MIN, 5.0)
    assert disc5 == 285.0
    assert disc5 > limit


def test_finer_timesteps_restore_under_or_at_limit():
    limit = 270.0
    assert discrete_drive_minutes_per_arc(VOLVO_MA_ARC_PHYS_MIN, 2.0) <= limit
    assert discrete_drive_minutes_per_arc(VOLVO_MA_ARC_PHYS_MIN, 1.0) <= limit


def test_casa_tangier_ceil_inflation_magnitude():
    phys = 266.15
    per_arc_campaign_disc = 300.0
    whole_trip_ceil_5 = float(math.ceil(phys / 5.0) * 5.0)
    assert whole_trip_ceil_5 == 270.0
    assert per_arc_campaign_disc > phys
    assert per_arc_campaign_disc > 270.0
