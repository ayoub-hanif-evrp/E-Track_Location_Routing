"""P0.1 — authoritative DRIVE/CHARGE/WAIT trace integrity."""

from __future__ import annotations

from morocco_etruck.energy.refrigeration import load_refrigeration
from morocco_etruck.energy.simulator import EdgeInput
from morocco_etruck.energy.terrain import TerrainSample
from morocco_etruck.energy.vehicle import load_vehicle
from morocco_etruck.energy.weather import CorridorWeatherDay, WeatherPointDay
from morocco_etruck.optimization.arc_preprocessing import MacroArcSpec, simulate_drive_from_soc
from morocco_etruck.optimization.multiroute_physics import MultirouteMissionContext
from morocco_etruck.optimization.multiroute_replay import (
    continuous_replay_multiroute,
    summarize_complete_trace,
)
from morocco_etruck.optimization.problem import RoutingInstance, StationData
from shapely.geometry import LineString
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _weather() -> CorridorWeatherDay:
    pt = WeatherPointDay(
        point_id="mid",
        lat=32.0,
        lon=-8.0,
        date="hist",
        T_mean_c=20.0,
        wind_speed_mean_mps=0.0,
        wind_dir_mean_deg=0.0,
        pressure_mean_hpa=1013.25,
    )
    return CorridorWeatherDay(day_id="cool", date="2020-01-01", points={"mid": pt})


def _flat_macro(
    aid: str,
    u: str,
    v: str,
    length_m: float = 5000.0,
    *,
    path_nodes: list[int] | None = None,
) -> MacroArcSpec:
    edge = EdgeInput(
        geometry=LineString([(-8.0, 32.0), (-8.0 + length_m / 111000.0, 32.0)]),
        length_m=length_m,
        speed_mps=80 / 3.6,
        highway="motorway",
        speed_source="class_default",
    )
    terrain = TerrainSample(
        distances_m=[0.0, length_m],
        elevations_m=[0.0, 0.0],
        source="flat",
        valid_mask=[True, True],
    )
    pn = path_nodes or [1, 2]
    return MacroArcSpec(
        u=u,
        v=v,
        path_nodes=pn,
        osm_edge_pairs=[(pn[0], pn[-1])],
        geometry=edge.geometry,
        length_m=length_m,
        micro_edges=[edge],
        terrain=terrain,
        terrain_quality_status="flat",
        road_cost=100,
        meta={"arc_id": aid, "terrain_mode": "flat", "dem_ok": True},
    )


def _ctx_and_inst(*, with_station: bool = True, low_init: bool = False):
    vehicle = load_vehicle(ROOT / "configs/vehicles/eactros_600.yaml")
    fridge = load_refrigeration(ROOT / "configs/energy/pass2_tomato_firm_ripe.yaml")
    m1 = _flat_macro(
        "a1",
        "O",
        "S" if with_station else "D",
        8000.0,
        path_nodes=[10, 20],
    )
    macros = {"a1": m1}
    nodes = ["O", "D"]
    stations = {}
    active = set()
    if with_station:
        m2 = _flat_macro("a2", "S", "D", 8000.0, path_nodes=[20, 30])
        macros["a2"] = m2
        nodes = ["O", "S", "D"]
        stations = {
            "S": StationData(
                node="S",
                power_kw=350.0,
                eta=0.95,
                price_cents_per_grid_kwh=20,
                compatible=True,
            )
        }
        active = {"S"}
    ctx = MultirouteMissionContext(
        od_id="toy",
        macros_by_arc_id=macros,
        vehicle=vehicle,
        fridge=fridge,
        weather=_weather(),
        gcm_kg=25000.0,
        refrigeration_on=True,
        power_source="A",
        time_step_min=5,
        terrain_mode="flat",
        dem_complete=True,
        weather_assumed=False,
    )
    E_init = 80 if low_init else 400
    inst = RoutingInstance(
        name="toy_trace",
        nodes=nodes,
        arcs=[],
        origin="O",
        destination="D",
        deadline_steps=500,
        E_truck_cap=600,
        E_truck_min=50,
        E_truck_init=E_init,
        E_trailer_cap=None,
        E_trailer_min=None,
        E_trailer_init=None,
        stations=stations,
        active_stations=active,
        power_source="A",
        refrigeration_on=True,
        aux_w=2000.0,
        tru_mean_w=1000.0,
        wait_max_steps=2,
        time_step_min=5,
        energy_quantum_kwh=10,
    )
    return ctx, inst


def test_drive_charge_drive_trace_updates_soc_and_completes():
    ctx, inst = _ctx_and_inst(with_station=True, low_init=True)
    actions = [
        {"type": "DRIVE", "u": "O", "v": "S", "arc_id": "a1"},
        {"type": "CHARGE", "node": "S", "delta_e_kwh": 200, "steps": 8},
        {"type": "DRIVE", "u": "S", "v": "D", "arc_id": "a2"},
    ]
    # Without charge, second drive from depleted SOC would fail on a longer corridor;
    # here both segments are mild — still verify charge raises SOC mid-mission.
    rep, ex = continuous_replay_multiroute(ctx, inst, actions, emit_trace=True)
    assert rep.ok
    assert ex.trace_complete
    types = [a["action_type"] for a in ex.action_trace]
    assert types == ["DRIVE", "CHARGE", "DRIVE"]
    charge = ex.action_trace[1]
    assert charge["soc_after"] > charge["soc_before"]
    summary = summarize_complete_trace(ex)
    assert summary["usable_for_complete_trip_stats"] is True
    assert abs(summary["length_m"] - ex.length_m) < 1e-6
    assert summary["arrival_soc"] == ex.arrival_soc


def test_drive_wait_drive_trace_records_wait():
    ctx, inst = _ctx_and_inst(with_station=True, low_init=False)
    actions = [
        {"type": "DRIVE", "u": "O", "v": "S", "arc_id": "a1"},
        {"type": "WAIT", "steps": 1},
        {"type": "DRIVE", "u": "S", "v": "D", "arc_id": "a2"},
    ]
    rep, ex = continuous_replay_multiroute(ctx, inst, actions, emit_trace=True)
    assert rep.ok and ex.trace_complete
    assert any(a["action_type"] == "WAIT" for a in ex.action_trace)
    assert ex.wait_duration_s > 0


def test_incomplete_trace_excluded_from_complete_stats():
    ctx, inst = _ctx_and_inst(with_station=True, low_init=False)
    actions = [{"type": "DRIVE", "u": "O", "v": "S", "arc_id": "a1"}]  # not at D
    rep, ex = continuous_replay_multiroute(ctx, inst, actions, emit_trace=True)
    assert not rep.ok
    assert not ex.trace_complete
    summary = summarize_complete_trace(ex)
    assert summary["trace_status"] == "INCOMPLETE"
    assert summary["usable_for_complete_trip_stats"] is False


def test_precharge_low_soc_false_failure_avoided_by_charge_state_update():
    """Stale SOC (skipping CHARGE) would understate energy for the second DRIVE."""
    ctx, inst = _ctx_and_inst(with_station=True, low_init=True)
    actions = [
        {"type": "DRIVE", "u": "O", "v": "S", "arc_id": "a1"},
        {"type": "CHARGE", "node": "S", "delta_e_kwh": 250, "steps": 10},
        {"type": "DRIVE", "u": "S", "v": "D", "arc_id": "a2"},
    ]
    rep, ex = continuous_replay_multiroute(ctx, inst, actions, emit_trace=True)
    assert rep.ok
    # Reconstruct: SOC after first drive, before charge
    d0 = ex.action_trace[0]
    c0 = ex.action_trace[1]
    assert c0["soc_before"] == d0["soc_after"]
    assert c0["soc_after"] > d0["soc_after"] + 0.05
