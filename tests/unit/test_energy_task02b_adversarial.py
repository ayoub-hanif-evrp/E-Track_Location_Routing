"""Adversarial Task 02B tests: DEM artifacts, power caps, SOC path feasibility."""

from __future__ import annotations

import math
from pathlib import Path

import pytest
from shapely.geometry import LineString

from morocco_etruck.energy.refrigeration import load_refrigeration
from morocco_etruck.energy.simulator import EdgeInput, evaluate_route, route_geodesic_length_m
from morocco_etruck.energy.terrain import (
    TerrainQuality,
    TerrainSample,
    assess_terrain_quality,
    cumulative_geodesic_m,
    densify_linestring,
    flat_profile,
    profile_distance_agrees,
    profile_from_elevations,
)
from morocco_etruck.energy.traction import map_wheel_to_battery_power, segment_traction_energy
from morocco_etruck.energy.vehicle import load_vehicle, validate_gcm
from morocco_etruck.energy.weather import (
    CorridorWeatherDay,
    WeatherPointDay,
    circular_mean_deg,
    vector_mean_wind,
)

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def vehicle():
    return load_vehicle(ROOT / "configs/vehicles/eactros_600.yaml")


@pytest.fixture(scope="module")
def fridge():
    return load_refrigeration(ROOT / "configs/energy/refrigeration_approx.yaml")


def _weather(T: float = 20.0, wind: float = 0.0) -> CorridorWeatherDay:
    p = WeatherPointDay(
        point_id="p",
        lat=32.0,
        lon=-8.0,
        date="2025-01-01",
        T_mean_c=T,
        wind_speed_mean_mps=wind,
        wind_dir_mean_deg=0.0,
        pressure_mean_hpa=1013.25,
    )
    return CorridorWeatherDay(day_id="t", date="2025-01-01", points={"p": p})


def _force_valid_quality(n: int = 2) -> TerrainQuality:
    return TerrainQuality(
        status="valid",
        max_abs_grade=0.0,
        n_samples=n,
        n_missing=0,
        missing_frac=0.0,
        n_grade_violations=0,
        first_grade_violation_km=None,
        notes=["test override"],
    )


def test_synthetic_150pct_grade_flagged():
    prof = TerrainSample(
        distances_m=[0.0, 158.0],
        elevations_m=[0.0, 249.0],
        source="synthetic",
        meta={},
        valid_mask=[True, True],
    )
    q = assess_terrain_quality(prof, max_abs_grade=0.15, min_segment_m=50.0)
    assert q.status == "invalid"
    assert q.max_abs_grade > 1.0
    assert q.n_grade_violations >= 1


def test_missing_raster_pixels_not_credible_zero():
    pts = [(-8.0 + i * 0.01, 32.0) for i in range(5)]
    elevs = [float("nan"), float("nan"), 400.0, 401.0, 402.0]
    mask = [False, False, True, True, True]
    prof = profile_from_elevations(pts, elevs, source="synthetic", smooth_window=1, valid_mask=mask)
    q = assess_terrain_quality(prof, max_missing_frac=0.02)
    assert q.status in {"invalid", "missing_data"}
    assert q.n_missing >= 2
    assert not math.isfinite(prof.elevations_m[0])


def test_peak_power_exceedance_flagged_not_silently_clipped(vehicle):
    seg = segment_traction_energy(
        length_m=500.0,
        dz_m=200.0,
        mass_kg=40000.0,
        v_mps=vehicle.cruise_mps,
        wind_along_travel_mps=0.0,
        rho_kg_m3=1.225,
        vehicle=vehicle,
        soc=1.0,
    )
    assert seg.P_wheel_w > vehicle.peak_power_w
    assert seg.power_feasible_peak is False
    assert seg.P_batt_trac_w == pytest.approx(seg.P_batt_required_w)
    assert seg.P_batt_required_w == pytest.approx(seg.P_wheel_w / vehicle.eta_prop)
    assert seg.E_batt_trac_j > vehicle.peak_power_w * seg.dt_s


def test_infeasible_energy_not_hidden_by_power_clip(vehicle, fridge):
    geom = LineString([(-8.0, 32.0), (-7.9, 32.1)])
    edges = [EdgeInput(geometry=geom, length_m=50_000.0)]
    terrain = TerrainSample(
        distances_m=[0.0, 50_000.0],
        elevations_m=[0.0, 5000.0],
        source="synthetic",
        meta={},
        valid_mask=[True, True],
    )
    res = evaluate_route(
        edges,
        vehicle,
        _weather(),
        fridge,
        gcm_kg=40000.0,
        refrigeration_on=False,
        power_source="A",
        terrain=terrain,
        terrain_quality=_force_valid_quality(),
    )
    assert res.power_feasible is False
    assert res.mission_feasible is False
    assert res.E_traction_kWh > 0


def test_mid_trip_soc_floor_not_rescued_by_regen(vehicle, fridge):
    e1 = EdgeInput(geometry=LineString([(-8.0, 32.0), (-7.5, 32.0)]), length_m=450_000.0)
    e2 = EdgeInput(geometry=LineString([(-7.5, 32.0), (-7.4, 32.0)]), length_m=50_000.0)
    terrain = TerrainSample(
        distances_m=[0.0, 450_000.0, 500_000.0],
        elevations_m=[0.0, 0.0, -3000.0],
        source="synthetic",
        meta={},
        valid_mask=[True, True, True],
    )
    res = evaluate_route(
        [e1, e2],
        vehicle,
        _weather(),
        fridge,
        gcm_kg=40000.0,
        refrigeration_on=False,
        power_source="A",
        terrain=terrain,
        terrain_quality=_force_valid_quality(3),
        speed_mps=22.222,
    )
    assert res.soc_feasible is False
    assert res.first_violation_reason == "tractor_soc_floor"
    assert res.first_violation_distance_km is not None
    assert res.first_violation_distance_km <= 450.0 + 1e-6
    assert res.mission_feasible is False
    assert res.minimum_soc < vehicle.soc_min


def test_regen_at_full_soc_does_not_increase_energy(vehicle):
    _req, used, *_rest = map_wheel_to_battery_power(-200_000.0, vehicle, soc=1.0)
    assert used == 0.0


def test_trailer_and_tractor_soc_checked_separately(vehicle, fridge):
    geom = LineString([(-8.0, 32.0), (-7.5, 32.0)])
    edges = [EdgeInput(geometry=geom, length_m=400_000.0)]
    terrain = flat_profile(geom)
    res_b = evaluate_route(
        edges,
        vehicle,
        _weather(T=40.0),
        fridge,
        gcm_kg=25000.0,
        refrigeration_on=True,
        power_source="B",
        terrain=terrain,
    )
    assert res_b.trailer_soc_final is not None
    if res_b.minimum_trailer_soc is not None and res_b.minimum_trailer_soc < fridge.trailer_soc_min:
        assert res_b.trailer_soc_feasible is False
        assert res_b.mission_feasible is False


def test_route_and_profile_distance_consistency():
    geom = LineString([(-8.0, 32.0), (-7.5, 32.0), (-7.0, 31.5)])
    route_m = route_geodesic_length_m(geom)
    pts = densify_linestring(geom, step_m=2000.0)
    dists = cumulative_geodesic_m(pts)
    prof = profile_from_elevations(pts, [0.0] * len(pts), source="flat", smooth_window=1)
    assert profile_distance_agrees(prof, route_m, rel_tol=0.002, abs_tol_m=500.0)
    assert abs(dists[-1] - route_m) <= max(500.0, 0.002 * route_m)


def test_gcm_labels_and_bounds(vehicle):
    validate_gcm(25000.0, vehicle)
    validate_gcm(40000.0, vehicle)
    with pytest.raises(ValueError):
        validate_gcm(5000.0, vehicle)
    with pytest.raises(ValueError):
        validate_gcm(50000.0, vehicle)


def test_circular_wind_mean_handles_wrap():
    mean = circular_mean_deg([350.0, 10.0])
    assert mean < 20.0 or mean > 340.0
    spd, direction = vector_mean_wind([10.0, 10.0], [350.0, 10.0])
    assert spd > 0
    assert direction < 20.0 or direction > 340.0


def test_invalid_terrain_yields_indeterminate_mission(vehicle, fridge):
    geom = LineString([(-8.0, 32.0), (-7.9, 32.0)])
    edges = [EdgeInput(geometry=geom, length_m=10_000.0)]
    terrain = TerrainSample(
        distances_m=[0.0, 158.0, 316.0],
        elevations_m=[0.0, 249.0, 498.0],
        source="copdem_glo30",
        meta={},
        valid_mask=[True, True, True],
    )
    q = assess_terrain_quality(terrain)
    assert q.status == "invalid"
    res = evaluate_route(
        edges,
        vehicle,
        _weather(),
        fridge,
        gcm_kg=25000.0,
        refrigeration_on=False,
        power_source="A",
        terrain=terrain,
        terrain_quality=q,
    )
    assert res.mission_feasible is None
    assert res.terrain_quality_status == "invalid"
