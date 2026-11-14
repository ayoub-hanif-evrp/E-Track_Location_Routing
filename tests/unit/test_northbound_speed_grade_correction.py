"""Regression tests for northbound power/grade/speed scientific correction."""

from __future__ import annotations

import json
import math
from pathlib import Path

import pytest

from morocco_etruck.energy.refrigeration import load_refrigeration
from morocco_etruck.energy.simulator import EdgeInput
from morocco_etruck.energy.terrain import TerrainSample
from morocco_etruck.energy.traction import (
    max_power_feasible_speed_mps,
    wheel_power_at_speed_w,
)
from morocco_etruck.energy.transitions import EnergyState, apply_drive
from morocco_etruck.energy.vehicle import load_vehicle
from morocco_etruck.energy.weather import CorridorWeatherDay, WeatherPointDay
from morocco_etruck.optimization.arc_preprocessing import (
    build_drive_table,
    simulate_drive_from_soc,
)
from morocco_etruck.optimization.drive_table_cache import (
    build_drive_table_fingerprint,
    speed_policy_digest,
)
from shapely.geometry import LineString

ROOT = Path(__file__).resolve().parents[2]
VOLVO = ROOT / "configs/vehicles/volvo_fh_electric_4x2_540kwh.yaml"
EACTROS = ROOT / "configs/vehicles/eactros_600.yaml"
FRIDGE = ROOT / "configs/energy/pass2_tomato_firm_ripe.yaml"


def _flat_weather() -> CorridorWeatherDay:
    pt = WeatherPointDay(
        point_id="mid",
        lat=32.0,
        lon=-8.0,
        date="synthetic",
        T_mean_c=20.0,
        wind_speed_mean_mps=0.0,
        wind_dir_mean_deg=0.0,
        pressure_mean_hpa=1013.25,
    )
    return CorridorWeatherDay(day_id="flat", date="synthetic", points={"mid": pt})


def _edge(length_m: float = 100.0) -> EdgeInput:
    # Rough lon/lat span ~ length (not geodesic-accurate; length_m authoritative)
    return EdgeInput(
        geometry=LineString([(-8.0, 32.0), (-8.0 + length_m / 111000.0, 32.0)]),
        length_m=length_m,
        speed_mps=80.0 / 3.6,
        highway="motorway",
        speed_source="class_default",
    )


def _terrain(length_m: float, dz_m: float) -> TerrainSample:
    return TerrainSample(
        distances_m=[0.0, length_m],
        elevations_m=[0.0, dz_m],
        source="test_dem",
        valid_mask=[True, True],
    )


def test_speed_reduction_respects_peak_power_limit():
    vehicle = load_vehicle(VOLVO)
    L, dz = 50.0, 5.5  # ~11% grade
    mass = 25300.0
    v_hi = 80.0 / 3.6
    p_hi = wheel_power_at_speed_w(
        length_m=L,
        dz_m=dz,
        mass_kg=mass,
        v_mps=v_hi,
        wind_along_travel_mps=0.0,
        rho_kg_m3=1.2,
        vehicle=vehicle,
    )
    assert p_hi > vehicle.peak_power_w
    v_star, p_star = max_power_feasible_speed_mps(
        length_m=L,
        dz_m=dz,
        mass_kg=mass,
        wind_along_travel_mps=0.0,
        rho_kg_m3=1.2,
        vehicle=vehicle,
        power_limit_w=float(vehicle.peak_power_w),
        v_hi_mps=v_hi,
        v_lo_mps=1.0 / 3.6,
    )
    assert v_star is not None
    assert v_star < v_hi
    assert p_star <= vehicle.peak_power_w + 1e-3


def test_dem_grade_changes_energy_and_time():
    vehicle = load_vehicle(VOLVO)
    fridge = load_refrigeration(FRIDGE)
    weather = _flat_weather()
    edge = _edge(200.0)
    flat = _terrain(200.0, 0.0)
    climb = _terrain(200.0, 10.0)
    st = EnergyState(soc=0.9, trailer_soc=None)
    r0 = apply_drive(
        st,
        edge,
        vehicle=vehicle,
        weather=weather,
        fridge_cfg=fridge,
        gcm_kg=25300.0,
        refrigeration_on=True,
        power_source="A",
        terrain=flat,
        s_cursor_m=0.0,
        speed_mps=80 / 3.6,
        adapt_speed_to_peak_power=True,
    )
    r1 = apply_drive(
        st,
        edge,
        vehicle=vehicle,
        weather=weather,
        fridge_cfg=fridge,
        gcm_kg=25300.0,
        refrigeration_on=True,
        power_source="A",
        terrain=climb,
        s_cursor_m=0.0,
        speed_mps=80 / 3.6,
        adapt_speed_to_peak_power=True,
    )
    assert r0.violation_reason is None and r1.violation_reason is None
    assert r1.E_traction_j > r0.E_traction_j
    # Climb adaptation may slow → longer duration
    assert r1.dt_s >= r0.dt_s - 1e-9
    assert r1.speed_adapted or r1.speed_mps_used <= r0.speed_mps_used + 1e-9


def test_peak_not_treated_as_unlimited_continuous_for_eactros():
    vehicle = load_vehicle(EACTROS)
    assert vehicle.peak_power_w > vehicle.continuous_power_w
    L, dz = 80.0, 7.0
    mass = 25300.0
    v_hi = 80 / 3.6
    v_peak, _ = max_power_feasible_speed_mps(
        length_m=L,
        dz_m=dz,
        mass_kg=mass,
        wind_along_travel_mps=0.0,
        rho_kg_m3=1.2,
        vehicle=vehicle,
        power_limit_w=float(vehicle.peak_power_w),
        v_hi_mps=v_hi,
    )
    v_cont, _ = max_power_feasible_speed_mps(
        length_m=L,
        dz_m=dz,
        mass_kg=mass,
        wind_along_travel_mps=0.0,
        rho_kg_m3=1.2,
        vehicle=vehicle,
        power_limit_w=float(vehicle.continuous_power_w),
        v_hi_mps=v_hi,
    )
    assert v_peak is not None and v_cont is not None
    assert v_cont <= v_peak + 1e-9

    fridge = load_refrigeration(FRIDGE)
    weather = _flat_weather()
    edge = _edge(L)
    terrain = _terrain(L, dz)
    st = EnergyState(soc=0.9, trailer_soc=None)
    r_peak = apply_drive(
        st,
        edge,
        vehicle=vehicle,
        weather=weather,
        fridge_cfg=fridge,
        gcm_kg=25300.0,
        refrigeration_on=False,
        power_source="A",
        terrain=terrain,
        s_cursor_m=0.0,
        speed_mps=v_hi,
        adapt_speed_to_peak_power=True,
        adapt_speed_to_continuous_power=False,
    )
    r_cont = apply_drive(
        st,
        edge,
        vehicle=vehicle,
        weather=weather,
        fridge_cfg=fridge,
        gcm_kg=25300.0,
        refrigeration_on=False,
        power_source="A",
        terrain=terrain,
        s_cursor_m=0.0,
        speed_mps=v_hi,
        adapt_speed_to_peak_power=True,
        adapt_speed_to_continuous_power=True,
    )
    assert r_peak.speed_mps_used is not None and r_cont.speed_mps_used is not None
    assert r_cont.speed_mps_used <= r_peak.speed_mps_used + 1e-9
    # Continuous-adapted segment must satisfy continuous rating
    p = wheel_power_at_speed_w(
        length_m=L,
        dz_m=dz,
        mass_kg=mass,
        v_mps=r_cont.speed_mps_used,
        wind_along_travel_mps=0.0,
        rho_kg_m3=1.2,
        vehicle=vehicle,
    )
    assert p <= vehicle.continuous_power_w + 1.0


def test_speed_policy_digest_invalidates_drive_cache_fingerprint():
    base = {"class_defaults_kmh": {"motorway": 80}, "use_osm_maxspeed": False}
    a = dict(base)
    b = dict(base)
    b["adapt_speed_to_peak_power"] = True
    assert speed_policy_digest(a) != speed_policy_digest(b)
    fp_a = build_drive_table_fingerprint(
        vehicle_yaml=VOLVO,
        fridge_yaml=FRIDGE,
        weather_points={},
        terrain_mode="dem",
        terrain_source="copdem",
        terrain_hash="abc",
        macro_u="O",
        macro_v="D",
        edge_pairs=[(1, 2)],
        length_m=1000.0,
        gcm_kg=25300.0,
        refrigeration_on=True,
        power_source="A",
        energy_quantum_kwh=10,
        time_step_min=5,
        E_truck_min=50,
        E_truck_cap=470,
        E_trailer_min=None,
        E_trailer_cap=None,
        speed_schedule=[80 / 3.6],
        speed_policy=a,
    )
    fp_b = build_drive_table_fingerprint(
        vehicle_yaml=VOLVO,
        fridge_yaml=FRIDGE,
        weather_points={},
        terrain_mode="dem",
        terrain_source="copdem",
        terrain_hash="abc",
        macro_u="O",
        macro_v="D",
        edge_pairs=[(1, 2)],
        length_m=1000.0,
        gcm_kg=25300.0,
        refrigeration_on=True,
        power_source="A",
        energy_quantum_kwh=10,
        time_step_min=5,
        E_truck_min=50,
        E_truck_cap=470,
        E_trailer_min=None,
        E_trailer_cap=None,
        speed_schedule=[80 / 3.6],
        speed_policy=b,
    )
    assert fp_a != fp_b


def test_pass2b_change_fields_separate_coverage_from_sites():
    path = ROOT / "results/pass2_refinement_change_fields.json"
    if not path.exists():
        pytest.skip("change-fields artifact not generated yet")
    rows = json.loads(path.read_text(encoding="utf-8"))
    sb = next(r for r in rows if "southbound" in r["scenario"])
    def _as_bool(x) -> bool:
        if isinstance(x, str):
            return x.strip().lower() in {"1", "true", "yes"}
        return bool(x)

    assert _as_bool(sb["coverage_changed"])
    assert not _as_bool(sb["minimum_site_count_changed"])
    assert not _as_bool(sb["optimal_site_set_changed"])
    assert str(sb["sites_q10"]).upper() in {"NONE", ""}
    assert str(sb["sites_q5"]).upper() in {"NONE", ""}


def test_revalidation_bb_enum_agree_when_placement_completed():
    path = ROOT / "results/northbound_revalidated_placement.csv"
    if not path.exists():
        pytest.skip("revalidation CSV missing")
    import pandas as pd

    df = pd.read_csv(path)
    if "place_Ball_bb_enum_agree" not in df.columns:
        pytest.skip("no placement columns")
    sub = df[df["place_Ball_bb_enum_agree"].notna()]
    assert len(sub) >= 1
    assert sub["place_Ball_bb_enum_agree"].astype(str).str.lower().isin(
        {"true", "1"}
    ).all()


def test_served_rows_have_consistent_replay_flags():
    path = ROOT / "results/northbound_revalidated_placement.csv"
    if not path.exists():
        pytest.skip("revalidation CSV missing")
    import pandas as pd

    df = pd.read_csv(path)
    served = df[df["served"] == True]  # noqa: E712
    if served.empty:
        pytest.skip("no served rows in this artifact")
    assert served["discrete_replay_ok"].astype(bool).all()
    assert served["continuous_replay_ok"].astype(bool).all()
    assert (served["mission_status"].astype(str) == "OPTIMAL").all()


def test_simulate_drive_adapt_clears_steep_peak_reject():
    vehicle = load_vehicle(VOLVO)
    fridge = load_refrigeration(FRIDGE)
    weather = _flat_weather()
    L, dz = 40.0, 4.5
    edge = _edge(L)
    terrain = _terrain(L, dz)
    ok0, *_ = simulate_drive_from_soc(
        [edge],
        terrain,
        soc0=0.9,
        trailer_soc0=None,
        vehicle=vehicle,
        weather=weather,
        fridge_cfg=fridge,
        gcm_kg=25300.0,
        refrigeration_on=False,
        power_source="A",
        adapt_speed_to_peak_power=False,
    )
    ok1, *rest = simulate_drive_from_soc(
        [edge],
        terrain,
        soc0=0.9,
        trailer_soc0=None,
        vehicle=vehicle,
        weather=weather,
        fridge_cfg=fridge,
        gcm_kg=25300.0,
        refrigeration_on=False,
        power_source="A",
        adapt_speed_to_peak_power=True,
    )
    # Fixed may fail peak; adapt must succeed on this synthetic climb
    assert ok1 is True
    if not ok0:
        assert rest[3] is None or rest[3] != "peak_motor_power_exceeded" or ok1
