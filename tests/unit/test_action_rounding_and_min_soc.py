"""Stage A — action-exact rounding audit and microsegment minimum SOC."""

from __future__ import annotations

from pathlib import Path

from shapely.geometry import LineString

from morocco_etruck.energy.refrigeration import load_refrigeration
from morocco_etruck.energy.simulator import EdgeInput
from morocco_etruck.energy.terrain import TerrainSample
from morocco_etruck.energy.vehicle import load_vehicle
from morocco_etruck.energy.weather import CorridorWeatherDay, WeatherPointDay
from morocco_etruck.optimization.arc_preprocessing import MacroArcSpec, simulate_drive_from_soc
from morocco_etruck.optimization.multiroute_physics import MultirouteMissionContext
from morocco_etruck.optimization.multiroute_replay import continuous_replay_multiroute
from morocco_etruck.optimization.problem import ArcData, DriveTableEntry, RoutingInstance
from morocco_etruck.optimization.quantization_audit import (
    audit_solved_actions_exact,
    drive_path_floor_loss,
)
from morocco_etruck.optimization.resource_transitions import _floor_to_quantum

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


def _macro_grade(aid: str = "a1") -> MacroArcSpec:
    e1 = EdgeInput(
        geometry=LineString([(-8.0, 32.0), (-7.98, 32.0)]),
        length_m=2500.0,
        speed_mps=80 / 3.6,
        highway="motorway",
        speed_source="class_default",
    )
    e2 = EdgeInput(
        geometry=LineString([(-7.98, 32.0), (-7.96, 32.0)]),
        length_m=2500.0,
        speed_mps=80 / 3.6,
        highway="motorway",
        speed_source="class_default",
    )
    terrain = TerrainSample(
        distances_m=[0.0, 2500.0, 5000.0],
        elevations_m=[0.0, 100.0, 0.0],
        source="synthetic",
        valid_mask=[True, True, True],
    )
    return MacroArcSpec(
        u="O",
        v="D",
        path_nodes=[1, 2, 3],
        osm_edge_pairs=[(1, 2), (2, 3)],
        geometry=LineString([(-8.0, 32.0), (-7.96, 32.0)]),
        length_m=5000.0,
        micro_edges=[e1, e2],
        terrain=terrain,
        terrain_quality_status="valid",
        road_cost=100,
        meta={"arc_id": aid, "terrain_mode": "dem", "dem_ok": True},
    )


def test_drive_path_floor_loss_is_superseded():
    out = drive_path_floor_loss(
        path_nodes=["O", "D"],
        arcs=[],
        E_truck_init=300,
        energy_quantum_kwh=10,
        simulate_drive_fn=simulate_drive_from_soc,
        prep_ctx=None,
    )
    assert out["superseded"] is True
    assert out["total_rounding_loss_kwh"] is None


def test_soc_min_along_captures_mid_macro_dip_before_regen():
    vehicle = load_vehicle(ROOT / "configs/vehicles/eactros_600.yaml")
    fridge = load_refrigeration(ROOT / "configs/energy/pass2_tomato_firm_ripe.yaml")
    macro = _macro_grade()
    ok, _dt, soc_end, _, reason, ecomp = simulate_drive_from_soc(
        macro.micro_edges,
        macro.terrain,
        soc0=0.5,
        trailer_soc0=None,
        vehicle=vehicle,
        weather=_weather(),
        fridge_cfg=fridge,
        gcm_kg=25000.0,
        refrigeration_on=False,
        power_source="A",
        adapt_speed_to_peak_power=True,
    )
    assert ok, reason
    assert ecomp["soc_min_along"] <= soc_end + 1e-9
    assert ecomp["soc_min_along"] < 0.5


def test_audit_requires_exact_arc_id_and_accounts_all_actions():
    vehicle = load_vehicle(ROOT / "configs/vehicles/eactros_600.yaml")
    fridge = load_refrigeration(ROOT / "configs/energy/pass2_tomato_firm_ripe.yaml")
    weather = _weather()
    macro = _macro_grade("a1")
    E0 = 300
    ok, _dt, soc_end, _, _, _ = simulate_drive_from_soc(
        macro.micro_edges,
        macro.terrain,
        soc0=E0 / vehicle.usable_kwh,
        trailer_soc0=None,
        vehicle=vehicle,
        weather=weather,
        fridge_cfg=fridge,
        gcm_kg=25000.0,
        refrigeration_on=False,
        power_source="A",
        adapt_speed_to_peak_power=True,
    )
    assert ok
    E_end = _floor_to_quantum(soc_end * vehicle.usable_kwh, 10)
    arc = ArcData(
        u="O",
        v="D",
        dt_steps=1,
        dE_truck_kwh=0,
        dE_trailer_kwh=0,
        road_cost=100,
        drive_table={(E0, None): DriveTableEntry(True, 1, E_end, None, None)},
        arc_id="a1",
    )
    inst = RoutingInstance(
        name="toy",
        nodes=["O", "D"],
        arcs=[arc],
        origin="O",
        destination="D",
        deadline_steps=1000,
        E_truck_cap=600,
        E_truck_min=50,
        E_truck_init=E0,
        E_trailer_cap=None,
        E_trailer_min=None,
        E_trailer_init=None,
        stations={},
        active_stations=set(),
        power_source="A",
        refrigeration_on=False,
        aux_w=2000.0,
        tru_mean_w=0.0,
        wait_max_steps=2,
        time_step_min=5,
        energy_quantum_kwh=10,
    )

    class Ctx:
        pass

    ctx = Ctx()
    ctx.vehicle = vehicle
    ctx.weather = weather
    ctx.fridge = fridge
    ctx.gcm_kg = 25000.0
    ctx.refrigeration_on = False
    ctx.power_source = "A"
    ctx.adapt_speed_to_peak_power = True
    ctx.adapt_speed_to_continuous_power = False
    ctx.min_adapt_speed_mps = 1.0 / 3.6
    ctx.macros_by_arc_id = {"a1": macro}

    actions = [{"type": "DRIVE", "u": "O", "v": "D", "arc_id": "a1"}]
    res = audit_solved_actions_exact(
        inst,
        actions,
        prep_ctx=ctx,
        simulate_drive_fn=simulate_drive_from_soc,
        expected_final_E_disc=E_end,
    )
    assert res.ok, res.failure_reason
    assert res.n_drive == 1
    assert res.n_actions_audited == 1

    bad = audit_solved_actions_exact(
        inst,
        [{"type": "DRIVE", "u": "O", "v": "D", "arc_id": "missing"}],
        prep_ctx=ctx,
        simulate_drive_fn=simulate_drive_from_soc,
    )
    assert bad.ok is False
    assert "missing_exact_arc_id" in (bad.failure_reason or "")


def test_replay_min_soc_uses_microsegment_when_emit_trace():
    vehicle = load_vehicle(ROOT / "configs/vehicles/eactros_600.yaml")
    fridge = load_refrigeration(ROOT / "configs/energy/pass2_tomato_firm_ripe.yaml")
    macro = _macro_grade("a1")
    ctx = MultirouteMissionContext(
        od_id="toy",
        macros_by_arc_id={"a1": macro},
        vehicle=vehicle,
        fridge=fridge,
        weather=_weather(),
        gcm_kg=25000.0,
        refrigeration_on=False,
        power_source="A",
        time_step_min=5,
        terrain_mode="dem",
        dem_complete=True,
        weather_assumed=False,
        adapt_speed_to_peak_power=True,
    )
    inst = RoutingInstance(
        name="toy_min",
        nodes=["O", "D"],
        arcs=[],
        origin="O",
        destination="D",
        deadline_steps=100000,
        E_truck_cap=600,
        E_truck_min=50,
        E_truck_init=200,
        E_trailer_cap=None,
        E_trailer_min=None,
        E_trailer_init=None,
        stations={},
        active_stations=set(),
        power_source="A",
        refrigeration_on=False,
        aux_w=2000.0,
        tru_mean_w=0.0,
        wait_max_steps=1,
        time_step_min=5,
        energy_quantum_kwh=5,
    )
    actions = [{"type": "DRIVE", "u": "O", "v": "D", "arc_id": "a1"}]
    rep, ex = continuous_replay_multiroute(ctx, inst, actions, emit_trace=True)
    assert rep.ok, rep.reason
    assert ex.trace_complete
    micros = [m for m in ex.micro_trace if m.get("action_type") == "DRIVE_MICRO"]
    assert micros
    micro_min = min(min(float(m["soc_before"]), float(m["soc_after"])) for m in micros)
    assert abs(ex.min_soc - micro_min) < 1e-9
    assert ex.min_soc_action is not None
    assert ex.min_soc <= float(ex.arrival_soc) + 1e-9
