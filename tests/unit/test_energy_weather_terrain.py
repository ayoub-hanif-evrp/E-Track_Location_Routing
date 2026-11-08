"""Weather projection and terrain helper unit tests (offline)."""

from __future__ import annotations

import math

from shapely.geometry import LineString

from morocco_etruck.energy.terrain import (
    densify_linestring,
    flat_profile,
    moving_average,
    profile_from_elevations,
)
from morocco_etruck.energy.weather import heading_deg, select_hot_cool_dates, wind_along_travel_mps


def test_tailwind_positive_along_travel():
    import pytest

    # Travel east (90°); wind from west (270°) → blows toward east → tailwind
    assert wind_along_travel_mps(10.0, 270.0, 90.0) == pytest.approx(10.0, abs=1e-9)


def test_headwind_negative():
    # Travel east; wind from east (90°) → headwind
    import pytest

    assert wind_along_travel_mps(10.0, 90.0, 90.0) == pytest.approx(-10.0, abs=1e-9)


def test_heading_north():
    h = heading_deg(0.0, 0.0, 0.0, 1.0)
    assert abs(h - 0.0) < 1.0


def test_select_hot_cool():
    hot, cool = select_hot_cool_dates([("2025-01-15", 10.0), ("2025-07-15", 35.0), ("2025-04-15", 20.0)])
    assert hot == "2025-07-15"
    assert cool == "2025-01-15"


def test_flat_profile_zero_elev():
    geom = LineString([(-8.0, 32.0), (-7.5, 32.0)])
    prof = flat_profile(geom, step_m=5000.0)
    assert prof.source == "flat"
    assert all(z == 0.0 for z in prof.elevations_m)
    assert prof.distances_m[-1] > 0


def test_moving_average_smooths():
    assert moving_average([0, 10, 0], window=3)[1] == 10 / 3


def test_densify_and_synthetic_grade():
    geom = LineString([(-8.0, 32.0), (-7.9, 32.0)])
    pts = densify_linestring(geom, step_m=2000.0)
    elevs = [float(i) * 10.0 for i in range(len(pts))]
    prof = profile_from_elevations(pts, elevs, source="synthetic", smooth_window=1)
    assert prof.elevations_m[-1] > prof.elevations_m[0]
    assert math.isfinite(prof.distances_m[-1])
