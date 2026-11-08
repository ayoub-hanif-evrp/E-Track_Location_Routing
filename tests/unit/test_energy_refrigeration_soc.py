"""Refrigeration approx, SOC bounds, and A vs B no double-counting."""

from __future__ import annotations

from pathlib import Path

import pytest
from shapely.geometry import LineString

from morocco_etruck.energy.refrigeration import (
    cop_at_ambient,
    heat_gain_w,
    load_refrigeration,
    tru_electrical_power_w,
)
from morocco_etruck.energy.simulator import EdgeInput, evaluate_route
from morocco_etruck.energy.terrain import flat_profile
from morocco_etruck.energy.vehicle import load_vehicle
from morocco_etruck.energy.weather import CorridorWeatherDay, WeatherPointDay

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def vehicle():
    return load_vehicle(ROOT / "configs/vehicles/eactros_600.yaml")


@pytest.fixture(scope="module")
def fridge():
    return load_refrigeration(ROOT / "configs/energy/refrigeration_approx.yaml")


def _weather(T: float) -> CorridorWeatherDay:
    pts = {
        "p": WeatherPointDay(
            point_id="p",
            lat=32.0,
            lon=-8.0,
            date="2025-01-01",
            T_mean_c=T,
            wind_speed_mean_mps=0.0,
            wind_dir_mean_deg=0.0,
            pressure_mean_hpa=1013.25,
        )
    }
    return CorridorWeatherDay(day_id="test", date="2025-01-01", points=pts)


def _short_edges() -> list[EdgeInput]:
    # ~10 km eastbound segment near Casablanca lat
    geom = LineString([(-8.0, 32.0), (-7.9, 32.0)])
    # haversine ~ 9.4 km
    return [EdgeInput(geometry=geom, length_m=9400.0)]


def test_heat_gain_zero_below_setpoint(fridge):
    assert heat_gain_w(fridge.setpoint_c - 5.0, fridge) == 0.0


def test_hot_vs_cool_refrigeration(fridge):
    p_hot = tru_electrical_power_w(35.0, fridge)
    p_cool = tru_electrical_power_w(12.0, fridge)
    assert p_hot > p_cool > 0
    assert cop_at_ambient(35.0, fridge) < cop_at_ambient(12.0, fridge)


def test_config_b_tractor_unaffected_by_tru(vehicle, fridge):
    edges = _short_edges()
    terrain = flat_profile(edges[0].geometry)
    weather = _weather(35.0)
    off = evaluate_route(
        edges, vehicle, weather, fridge,
        gcm_kg=25000.0, refrigeration_on=False, power_source="B", terrain=terrain,
    )
    on = evaluate_route(
        edges, vehicle, weather, fridge,
        gcm_kg=25000.0, refrigeration_on=True, power_source="B", terrain=terrain,
    )
    assert on.E_refrig_kWh > 0
    assert on.E_net_tractor_kWh == pytest.approx(off.E_net_tractor_kWh, rel=1e-9)
    assert on.soc_final == pytest.approx(off.soc_final, rel=1e-9)
    assert on.E_trailer_refrig_j > 0
    assert on.trailer_soc_final is not None
    assert on.trailer_soc_final < fridge.trailer_soc_initial


def test_config_a_tru_hits_tractor(vehicle, fridge):
    edges = _short_edges()
    terrain = flat_profile(edges[0].geometry)
    weather = _weather(35.0)
    off = evaluate_route(
        edges, vehicle, weather, fridge,
        gcm_kg=25000.0, refrigeration_on=False, power_source="A", terrain=terrain,
    )
    on = evaluate_route(
        edges, vehicle, weather, fridge,
        gcm_kg=25000.0, refrigeration_on=True, power_source="A", terrain=terrain,
    )
    assert on.E_net_tractor_kWh > off.E_net_tractor_kWh
    assert on.soc_final < off.soc_final
    assert on.E_trailer_refrig_j == 0.0


def test_no_double_counting_a_vs_b(vehicle, fridge):
    edges = _short_edges()
    terrain = flat_profile(edges[0].geometry)
    weather = _weather(30.0)
    a = evaluate_route(
        edges, vehicle, weather, fridge,
        gcm_kg=25000.0, refrigeration_on=True, power_source="A", terrain=terrain,
    )
    b = evaluate_route(
        edges, vehicle, weather, fridge,
        gcm_kg=25000.0, refrigeration_on=True, power_source="B", terrain=terrain,
    )
    # Same TRU energy total; A puts it on tractor, B on trailer
    assert a.E_refrig_kWh == pytest.approx(b.E_refrig_kWh)
    assert a.E_net_tractor_kWh - a.E_refrig_kWh == pytest.approx(b.E_net_tractor_kWh, rel=1e-9)
    assert b.E_trailer_refrig_j == pytest.approx(a.E_refrig_j)


def test_soc_bounds(vehicle, fridge):
    # Very long / heavy to drain battery near floor
    geom = LineString([(-9.0, 30.0), (-7.0, 34.0)])
    edges = [EdgeInput(geometry=geom, length_m=500_000.0)]
    terrain = flat_profile(geom)
    weather = _weather(20.0)
    res = evaluate_route(
        edges, vehicle, weather, fridge,
        gcm_kg=44000.0, refrigeration_on=True, power_source="A", terrain=terrain,
    )
    assert 0.0 <= res.soc_final <= vehicle.soc_max
