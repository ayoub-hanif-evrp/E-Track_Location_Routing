"""Task 08 — positive nesting adversary, shortest-mask connectivity, payload legality."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from morocco_etruck.energy.vehicle import (
    empty_combination_kg,
    gcm_from_payload,
    load_vehicle,
    validate_gcm,
)
from morocco_etruck.optimization.label_setting import SolverStatus, solve_mrls
from morocco_etruck.optimization.multiroute_adapter import (
    build_physics_od_instance,
    clone_physics_instance_for_subset,
    load_multiroute_pilot_config,
    shortest_path_allowed_arc_ids,
    shortest_path_edge_set,
)
from morocco_etruck.optimization.problem import ArcData, RoutingInstance, StationData

ROOT = Path(__file__).resolve().parents[2]
EACTROS = ROOT / "configs/vehicles/eactros_600.yaml"
VOLVO = ROOT / "configs/vehicles/volvo_fh_electric_4x2_540kwh.yaml"


def test_synthetic_adversarial_strict_cost_monotonicity():
    """
    Positive (non-vacuous) nesting: both restricted and expanded OPTIMAL,
    expanded strictly cheaper when a lower-road-cost alternative is unmasked.
    """
    arcs = [
        ArcData("O", "D", 2, 20, 0, road_cost=100, arc_id="short_expensive"),
        ArcData("O", "A", 1, 10, 0, road_cost=5, arc_id="alt_oa"),
        ArcData("A", "D", 1, 10, 0, road_cost=5, arc_id="alt_ad"),
    ]
    tmpl = RoutingInstance(
        name="task08_nest_adversary",
        nodes=["O", "A", "D"],
        arcs=arcs,
        origin="O",
        destination="D",
        deadline_steps=20,
        E_truck_cap=100,
        E_truck_min=0,
        E_truck_init=50,
        E_trailer_cap=None,
        E_trailer_min=None,
        E_trailer_init=None,
        stations={},
        active_stations=set(),
        power_source="A",
        refrigeration_on=False,
        energy_quantum_kwh=1,
        time_step_min=5,
        wait_max_steps=0,
    )
    restricted = clone_physics_instance_for_subset(
        tmpl,
        active_stations=set(),
        allowed_arc_ids=frozenset({"short_expensive"}),
    )
    expanded = clone_physics_instance_for_subset(
        tmpl,
        active_stations=set(),
        allowed_arc_ids=frozenset({"short_expensive", "alt_oa", "alt_ad"}),
    )
    r = solve_mrls(restricted, max_seconds=5.0)
    e = solve_mrls(expanded, max_seconds=5.0)
    assert r.status == SolverStatus.OPTIMAL
    assert e.status == SolverStatus.OPTIMAL
    assert r.objective is not None and e.objective is not None
    assert e.objective < r.objective, (
        f"expected strict mono: expanded={e.objective} < restricted={r.objective}"
    )
    assert e.objective == 10
    assert r.objective == 100


def test_shortest_mask_connects_od_and_covers_osm_edges():
    cfg = load_multiroute_pilot_config(
        ROOT / "configs/optimization/multiroute_pilot.yaml", root=ROOT
    )
    path_rows = pd.read_csv(cfg.path_alternatives_csv).to_dict(orient="records")
    vehicle = load_vehicle(EACTROS)
    gcm = gcm_from_payload(5300.0, vehicle)
    e_init = int(round(0.5 * float(vehicle.usable_kwh)))
    inst, ctx, _notes = build_physics_od_instance(
        cfg=cfg,
        root=ROOT,
        od_id="casa_marrakech",
        path_rows=path_rows,
        E_truck_init=e_init,
        refrigeration_on=True,
        weather_id="cool",
        with_chargers=True,
        energy_quantum_kwh=10,
        terrain_mode="flat",
        objective_mode="enroute_incremental_cost",
        vehicle_yaml=EACTROS,
        road_cost_per_km=100.0,
        gcm_kg=gcm,
        max_alternatives_for_union=2,
        fridge_yaml=ROOT / "configs/energy/task07b_thermal_nominal.yaml",
    )
    short_edges = shortest_path_edge_set(path_rows, "casa_marrakech")
    mask = shortest_path_allowed_arc_ids(ctx, path_rows, "casa_marrakech")
    assert mask
    # Every masked macro's OSM pairs ⊆ shortest path
    for aid in mask:
        macro = ctx.macros_by_arc_id[aid]
        pairs = list(macro.osm_edge_pairs or [])
        assert pairs
        assert all((int(u), int(v)) in short_edges for u, v in pairs)
    # Masked outgoing yields a directed O→D walk
    masked = clone_physics_instance_for_subset(
        inst, active_stations=set(), allowed_arc_ids=mask
    )
    import heapq
    from collections import defaultdict

    g = defaultdict(list)
    for n in masked.nodes:
        for a in masked.outgoing(n):
            g[a.u].append((a.v, a.road_cost, a))
    pq = [(0, masked.origin, [masked.origin])]
    seen = {}
    path = None
    while pq:
        c, u, pth = heapq.heappop(pq)
        if u in seen and seen[u] <= c:
            continue
        seen[u] = c
        if u == masked.destination:
            path = pth
            break
        for v, rc, _a in g[u]:
            heapq.heappush(pq, (c + rc, v, pth + [v]))
    assert path is not None, "shortest mask does not connect O→D"
    # Identity vs full clone
    full = clone_physics_instance_for_subset(
        inst,
        active_stations=set(),
        allowed_arc_ids=frozenset(str(a.arc_id) for a in inst.arcs if a.arc_id),
    )
    assert set(masked.nodes) == set(full.nodes)
    assert {a.arc_id for a in masked.arcs} == {a.arc_id for a in full.arcs}


def test_payload_15000_within_manufacturer_gcw_both_vehicles():
    for path in (EACTROS, VOLVO):
        v = load_vehicle(path)
        gcm = gcm_from_payload(15000.0, v)
        validate_gcm(gcm, v)
        assert gcm == empty_combination_kg(v) + 15000.0
        assert gcm <= float(v.gcm_limit_kg) + 1e-6


def test_empty_combination_helpers_match_yaml():
    ea = load_vehicle(EACTROS)
    vo = load_vehicle(VOLVO)
    assert empty_combination_kg(ea) == 19700.0
    assert empty_combination_kg(vo) == 20000.0
