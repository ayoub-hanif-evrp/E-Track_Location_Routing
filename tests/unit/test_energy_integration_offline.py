"""Offline integration: evaluate a short synthetic route with weather fixtures."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from shapely.geometry import LineString

from morocco_etruck.energy.refrigeration import load_refrigeration
from morocco_etruck.energy.simulator import EdgeInput, evaluate_route
from morocco_etruck.energy.terrain import densify_linestring, flat_profile, profile_from_elevations
from morocco_etruck.energy.vehicle import load_vehicle
from morocco_etruck.energy.weather import CorridorWeatherDay, WeatherPointDay

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "tests" / "fixtures" / "weather"


def _load_fixture_weather() -> CorridorWeatherDay:
    sel = json.loads((FIXTURES / "selection.json").read_text(encoding="utf-8"))
    date = sel["cool_date"]
    pts = {}
    for pid, _cfg in sel["points"].items():
        raw = json.loads((FIXTURES / f"{pid}_{date}.json").read_text(encoding="utf-8"))
        pts[pid] = WeatherPointDay(**raw)
    return CorridorWeatherDay(day_id="cool", date=date, points=pts)


def test_fixture_weather_loads():
    w = _load_fixture_weather()
    assert len(w.points) == 3
    assert w.T_corridor_mean_c < 25.0  # cool day


def test_evaluate_route_offline_smoke():
    vehicle = load_vehicle(ROOT / "configs/vehicles/eactros_600.yaml")
    fridge = load_refrigeration(ROOT / "configs/energy/refrigeration_approx.yaml")
    weather = _load_fixture_weather()
    geom = LineString([(-7.6, 33.5), (-7.7, 33.4), (-7.8, 33.3)])
    edges = [EdgeInput(geometry=geom, length_m=20_000.0)]
    terrain = flat_profile(geom)
    res = evaluate_route(
        edges,
        vehicle,
        weather,
        fridge,
        gcm_kg=40000.0,
        refrigeration_on=True,
        power_source="A",
        terrain=terrain,
    )
    assert res.distance_km == pytest.approx(20.0, rel=1e-9)
    assert res.E_net_tractor_kWh > 0
    assert 0.0 < res.soc_final <= 1.0
    assert res.terrain_source == "flat"


def test_dem_vs_flat_energy_differs_with_grade():
    vehicle = load_vehicle(ROOT / "configs/vehicles/eactros_600.yaml")
    fridge = load_refrigeration(ROOT / "configs/energy/refrigeration_approx.yaml")
    weather = _load_fixture_weather()
    geom = LineString([(-8.0, 32.0), (-7.9, 32.1)])
    L = 15_000.0
    edges = [EdgeInput(geometry=geom, length_m=L)]
    flat = flat_profile(geom)
    pts = densify_linestring(geom, step_m=1000.0)
    elevs = [i * 20.0 for i in range(len(pts))]  # rising
    dem = profile_from_elevations(pts, elevs, source="synthetic", smooth_window=1)
    flat_res = evaluate_route(
        edges, vehicle, weather, fridge, gcm_kg=40000.0,
        refrigeration_on=False, power_source="A", terrain=flat,
    )
    dem_res = evaluate_route(
        edges, vehicle, weather, fridge, gcm_kg=40000.0,
        refrigeration_on=False, power_source="A", terrain=dem,
    )
    assert dem_res.E_traction_kWh > flat_res.E_traction_kWh
