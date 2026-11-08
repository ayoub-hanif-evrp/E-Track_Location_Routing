"""Offline smoke: flat micro-profile → DRIVE table → MRLS (no live DEM)."""

from __future__ import annotations

from pathlib import Path

import pytest
from shapely.geometry import LineString

from morocco_etruck.energy.refrigeration import load_refrigeration
from morocco_etruck.energy.simulator import EdgeInput
from morocco_etruck.energy.terrain import flat_profile
from morocco_etruck.energy.vehicle import load_vehicle
from morocco_etruck.energy.weather import CorridorWeatherDay, WeatherPointDay
from morocco_etruck.optimization.arc_preprocessing import MacroArcSpec, build_drive_table
from morocco_etruck.optimization.label_setting import SolverStatus, solve_mrls
from morocco_etruck.optimization.problem import ArcData, RoutingInstance, StationData
from morocco_etruck.optimization.replay import replay_solution

ROOT = Path(__file__).resolve().parents[2]


def _toy_weather() -> CorridorWeatherDay:
    wp = WeatherPointDay(
        point_id="mid",
        lat=32.0,
        lon=-8.0,
        date="2025-01-15",
        T_mean_c=15.0,
        wind_speed_mean_mps=2.0,
        wind_dir_mean_deg=180.0,
        pressure_mean_hpa=1013.0,
    )
    return CorridorWeatherDay(day_id="cool", date="2025-01-15", points={"mid": wp})


def test_flat_drive_table_and_mrls():
    vehicle = load_vehicle(ROOT / "configs/vehicles/eactros_600.yaml")
    fridge = load_refrigeration(ROOT / "configs/energy/refrigeration_approx.yaml")
    weather = _toy_weather()

    # ~50 km flat toy corridor split into 2 km edges
    n = 26
    coords = [(-7.5 - i * 0.02, 33.0 - i * 0.01) for i in range(n)]
    geom = LineString(coords)
    micro = []
    for i in range(n - 1):
        sub = LineString([coords[i], coords[i + 1]])
        # approximate length; geodesic would be better but constant ~2 km order
        micro.append(EdgeInput(geometry=sub, length_m=2000.0))
    terrain = flat_profile(geom)
    macro = MacroArcSpec(
        u="O",
        v="D",
        path_nodes=[],
        osm_edge_pairs=[],
        geometry=geom,
        length_m=sum(e.length_m for e in micro),
        micro_edges=micro,
        terrain=terrain,
        terrain_quality_status="flat",
        road_cost=0,
    )
    q = 5
    E_min, E_cap = 60, 600
    table = build_drive_table(
        macro,
        vehicle=vehicle,
        weather=weather,
        fridge_cfg=fridge,
        gcm_kg=25000.0,
        refrigeration_on=False,
        power_source="A",
        E_truck_min=E_min,
        E_truck_cap=E_cap,
        E_trailer_min=None,
        E_trailer_cap=None,
        energy_quantum_kwh=q,
        time_step_min=5,
    )
    assert (E_cap, None) in table
    assert table[(E_cap, None)].feasible
    assert table[(E_cap, None)].E_end_truck <= E_cap
    assert table[(E_cap, None)].dt_steps >= 1

    inst = RoutingInstance(
        name="toy_flat",
        nodes=["O", "D"],
        arcs=[
            ArcData(
                "O",
                "D",
                dt_steps=1,
                dE_truck_kwh=0,
                dE_trailer_kwh=0,
                road_cost=0,
                drive_table=table,
            )
        ],
        origin="O",
        destination="D",
        deadline_steps=120,
        E_truck_cap=E_cap,
        E_truck_min=E_min,
        E_truck_init=E_cap,
        E_trailer_cap=None,
        E_trailer_min=None,
        E_trailer_init=None,
        stations={},
        active_stations=set(),
        power_source="A",
        refrigeration_on=False,
        wait_max_steps=0,
        time_step_min=5,
        energy_quantum_kwh=q,
    )
    r = solve_mrls(inst)
    assert r.status == SolverStatus.OPTIMAL
    rep = replay_solution(inst, r.actions, expected_cost=r.objective)
    assert rep.ok


def test_pilot_yaml_loads():
    from morocco_etruck.optimization.morocco_adapter import load_pilot_config

    cfg = load_pilot_config(ROOT / "configs/optimization/morocco_pilot.yaml")
    assert "scenarios" in cfg
    assert cfg["charger"]["hypothetical_access"] if False else cfg["charger"]["power_kw"] == 350.0
