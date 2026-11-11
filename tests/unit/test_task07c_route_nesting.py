"""Task 07C — route-set nesting on one physical path-union graph."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from morocco_etruck.energy.vehicle import gcm_from_payload, load_vehicle, validate_gcm
from morocco_etruck.optimization.label_setting import SolverStatus, solve_mrls
from morocco_etruck.optimization.multiroute_adapter import (
    build_physics_od_instance,
    clone_physics_instance_for_subset,
    load_multiroute_pilot_config,
    shortest_path_allowed_arc_ids,
)
from morocco_etruck.optimization.multiroute_replay import continuous_replay_multiroute
from morocco_etruck.optimization.replay import replay_solution

ROOT = Path(__file__).resolve().parents[2]
EACTROS = ROOT / "configs/vehicles/eactros_600.yaml"
PAYLOAD = 5300.0
ROAD_CENTS = 100.0


def _full_union_template(*, od_id: str, terrain_mode: str = "flat", with_chargers: bool = True):
    cfg = load_multiroute_pilot_config(
        ROOT / "configs/optimization/multiroute_pilot.yaml", root=ROOT
    )
    path_rows = pd.read_csv(cfg.path_alternatives_csv).to_dict(orient="records")
    vehicle = load_vehicle(EACTROS)
    gcm = gcm_from_payload(PAYLOAD, vehicle)
    validate_gcm(gcm, vehicle)
    e_init = int(round(0.5 * float(vehicle.usable_kwh)))
    # Scientific pilot union (max_alts=2): one physical graph for nested masks.
    inst, ctx, notes = build_physics_od_instance(
        cfg=cfg,
        root=ROOT,
        od_id=od_id,
        path_rows=path_rows,
        E_truck_init=e_init,
        refrigeration_on=True,
        weather_id="cool",
        with_chargers=with_chargers,
        energy_quantum_kwh=10,
        terrain_mode=terrain_mode,
        objective_mode="enroute_incremental_cost",
        vehicle_yaml=EACTROS,
        road_cost_per_km=ROAD_CENTS,
        gcm_kg=gcm,
        max_alternatives_for_union=2,
        fridge_yaml=ROOT / "configs/energy/task07b_thermal_nominal.yaml",
    )
    return cfg, path_rows, inst, ctx, notes, vehicle


def _graph_identity(a, b) -> None:
    assert set(a.nodes) == set(b.nodes)
    assert {x.arc_id for x in a.arcs} == {x.arc_id for x in b.arcs}
    assert set(a.stations) == set(b.stations)
    # Shared DRIVE table object identity per arc_id (same physical tables)
    by_a = {str(x.arc_id): x for x in a.arcs if x.arc_id}
    by_b = {str(x.arc_id): x for x in b.arcs if x.arc_id}
    for aid, arc in by_a.items():
        assert by_b[aid].drive_table is arc.drive_table


@pytest.mark.parametrize(
    "od_id,active,label",
    [
        ("casa_marrakech", frozenset(), "cm_none"),
        ("casa_agadir", frozenset({"settat_ca", "benguerir_ca"}), "ca_settat_benguerir"),
    ],
)
def test_nesting_same_graph_feasibility_and_cost(od_id: str, active: frozenset, label: str):
    """Adversarial Moroccan cells from the Task 07B nesting review."""
    _cfg, path_rows, template, ctx, _notes, _veh = _full_union_template(
        od_id=od_id, terrain_mode="flat", with_chargers=True
    )
    if ctx.terrain_mode == "dem" and not ctx.dem_complete:
        pytest.skip("dem_incomplete")
    short_mask = shortest_path_allowed_arc_ids(ctx, path_rows, od_id)
    assert short_mask, f"empty shortest mask for {od_id}"
    assert short_mask < frozenset(
        str(a.arc_id) for a in template.arcs if a.arc_id
    ) or short_mask == frozenset(str(a.arc_id) for a in template.arcs if a.arc_id)

    restricted = clone_physics_instance_for_subset(
        template,
        active_stations=set(active),
        allowed_arc_ids=short_mask,
        name=f"{label}_restricted",
    )
    expanded = clone_physics_instance_for_subset(
        template,
        active_stations=set(active),
        allowed_arc_ids=None,  # keep template None = all
        name=f"{label}_expanded",
    )
    # Force expanded to all arcs explicitly
    expanded = clone_physics_instance_for_subset(
        template,
        active_stations=set(active),
        allowed_arc_ids=frozenset(str(a.arc_id) for a in template.arcs if a.arc_id),
        name=f"{label}_expanded",
    )
    _graph_identity(restricted, expanded)
    assert restricted.allowed_arc_ids == short_mask
    assert expanded.allowed_arc_ids is not None
    assert short_mask <= expanded.allowed_arc_ids

    r_res = solve_mrls(restricted, max_seconds=90.0, max_expansions=800_000)
    e_res = solve_mrls(expanded, max_seconds=90.0, max_expansions=800_000)

    # Graph identity already checked; now nesting
    if r_res.status == SolverStatus.OPTIMAL:
        assert e_res.status == SolverStatus.OPTIMAL, (
            f"{label}: restricted OPTIMAL but expanded {e_res.status.value}"
        )
        assert e_res.objective is not None and r_res.objective is not None
        assert e_res.objective <= r_res.objective + 1e-9, (
            f"{label}: cost monotonicity violated "
            f"expanded={e_res.objective} > restricted={r_res.objective}"
        )
        for tag, inst, res in (
            ("restricted", restricted, r_res),
            ("expanded", expanded, e_res),
        ):
            disc = replay_solution(inst, res.actions, expected_cost=res.objective)
            assert disc.ok, f"{label}/{tag} discrete replay failed: {disc.reason}"
            crep, _ex = continuous_replay_multiroute(
                ctx,
                inst,
                res.actions,
                discrete_cost=res.objective,
                discrete_t=res.final_label.t,
                discrete_E_truck=res.final_label.E_truck,
            )
            assert crep.ok, f"{label}/{tag} continuous replay failed: {crep.reason}"


def test_shortest_mask_is_proper_subset_on_casa_agadir():
    _cfg, path_rows, template, ctx, _notes, _veh = _full_union_template(
        od_id="casa_agadir", terrain_mode="flat"
    )
    short_mask = shortest_path_allowed_arc_ids(ctx, path_rows, "casa_agadir")
    all_ids = frozenset(str(a.arc_id) for a in template.arcs if a.arc_id)
    assert short_mask
    assert short_mask <= all_ids
    # With alternatives present, shortest should not exhaust the union
    assert len(short_mask) < len(all_ids)


def test_outgoing_respects_allowed_arc_ids():
    _cfg, path_rows, template, ctx, _notes, _veh = _full_union_template(
        od_id="casa_marrakech", terrain_mode="flat"
    )
    short_mask = shortest_path_allowed_arc_ids(ctx, path_rows, "casa_marrakech")
    masked = clone_physics_instance_for_subset(
        template, active_stations=set(), allowed_arc_ids=short_mask
    )
    for node in masked.nodes:
        for arc in masked.outgoing(node):
            if arc.arc_id:
                assert str(arc.arc_id) in short_mask
