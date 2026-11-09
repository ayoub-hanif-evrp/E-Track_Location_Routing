"""Task 05B adversarial tests for path-union physics multiroute MRLS."""

from __future__ import annotations

import json
from pathlib import Path

import networkx as nx
import pandas as pd
import pytest

from morocco_etruck.energy.refrigeration import load_refrigeration
from morocco_etruck.energy.terrain import flat_profile
from morocco_etruck.energy.vehicle import load_vehicle
from morocco_etruck.energy.weather import CorridorWeatherDay, WeatherPointDay
from morocco_etruck.optimization.arc_preprocessing import MacroArcSpec, build_macro_arc
from morocco_etruck.optimization.label_setting import SolverStatus, solve_mrls
from morocco_etruck.optimization.multiroute_charging import (
    ArtificialMidpointRejected,
    GroundedCharger,
    reject_artificial_midpoint_keys,
    split_arcs_at_charger_nodes,
)
from morocco_etruck.optimization.multiroute_physics import (
    MultirouteMissionContext,
    build_path_union_routing_instance,
    induce_od_decision_arcs,
)
from morocco_etruck.optimization.multiroute_replay import continuous_replay_multiroute
from morocco_etruck.optimization.problem import ArcData, DriveTableEntry, RoutingInstance, StationData
from morocco_etruck.optimization.reference_solver import solve_reference
from morocco_etruck.optimization.replay import replay_solution
from morocco_etruck.optimization.route_choice_graph import (
    DecisionArc,
    canonicalize_terminals,
    make_arc_id,
)
from shapely.geometry import LineString

ROOT = Path(__file__).resolve().parents[2]


def _toy_weather() -> CorridorWeatherDay:
    return CorridorWeatherDay(
        day_id="t",
        date="t",
        points={
            "m": WeatherPointDay(
                point_id="m",
                lat=32.0,
                lon=-8.0,
                date="t",
                T_mean_c=20.0,
                wind_speed_mean_mps=1.0,
                wind_dir_mean_deg=0.0,
                pressure_mean_hpa=1013.0,
            )
        },
    )


def _toy_graph() -> nx.DiGraph:
    G = nx.DiGraph()
    # O --a--> J --b--> D  (short steep)
    # O --c--> M --d--> D  (long flat)
    coords = {
        1: (-8.0, 32.0),
        2: (-7.9, 32.05),
        3: (-7.8, 32.1),
        4: (-7.85, 32.02),
        5: (-7.8, 32.1),
    }
    for nid, (lon, lat) in coords.items():
        G.add_node(nid, lon=lon, lat=lat)
    def edge(u, v, L, highway="primary"):
        G.add_edge(
            u,
            v,
            length_m=L,
            highway=highway,
            hgv_access="unknown",
            geometry_wkt=LineString([(G.nodes[u]["lon"], G.nodes[u]["lat"]), (G.nodes[v]["lon"], G.nodes[v]["lat"])]).wkt,
        )
    edge(1, 2, 5000)
    edge(2, 3, 5000)
    edge(1, 4, 8000)
    edge(4, 3, 8000)
    # one-way only forward on short branch already
    return G


def test_reject_artificial_midpoint_charger():
    with pytest.raises(ArtificialMidpointRejected):
        reject_artificial_midpoint_keys(["R0_casa_agadir"])


def test_canonicalize_aliases_one_osm_id():
    terminals = {
        "casablanca": 100,
        "casa_agadir__o": 100,
        "agadir_casa__d": 100,
        "agadir": 200,
    }
    nodes, rev, alias = canonicalize_terminals(terminals)
    assert nodes["casablanca"] == 100
    assert "casa_agadir__o" not in nodes
    assert alias["casa_agadir__o"] == "casablanca"
    assert rev[100] == "casablanca"


def test_parallel_macro_arc_ids_differ():
    a = make_arc_id([(1, 2), (2, 3)])
    b = make_arc_id([(1, 4), (4, 3)])
    assert a != b
    assert a == make_arc_id([(1, 2), (2, 3)])


def test_branching_junction_route_choice_and_reference():
    """Two alternatives; longer cheaper road_cost forces non-shortest when both feasible."""
    arcs = [
        ArcData("O", "J", 1, 10, 0, road_cost=20, arc_id="short"),
        ArcData("J", "D", 1, 10, 0, road_cost=20, arc_id="short2"),
        ArcData("O", "M", 1, 5, 0, road_cost=5, arc_id="long1"),
        ArcData("M", "D", 1, 5, 0, road_cost=5, arc_id="long2"),
    ]
    # Parallel same endpoints with different costs
    arcs.append(ArcData("O", "D", 1, 50, 0, road_cost=100, arc_id="direct_expensive"))
    inst = RoutingInstance(
        name="branch",
        nodes=["O", "J", "M", "D"],
        arcs=arcs,
        origin="O",
        destination="D",
        deadline_steps=20,
        E_truck_cap=100,
        E_truck_min=0,
        E_truck_init=100,
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
    r = solve_mrls(inst, max_seconds=10.0)
    assert r.status == SolverStatus.OPTIMAL
    assert r.path_nodes == ["O", "M", "D"]
    ref = solve_reference(inst)
    assert ref.objective == r.objective
    assert ref.path_nodes == r.path_nodes


def test_oneway_forbidden_continuation():
    arcs = [ArcData("O", "D", 1, 5, 0, road_cost=1, arc_id="fwd")]
    inst = RoutingInstance(
        name="ow",
        nodes=["O", "D"],
        arcs=arcs,
        origin="D",
        destination="O",
        deadline_steps=10,
        E_truck_cap=50,
        E_truck_min=0,
        E_truck_init=50,
        E_trailer_cap=None,
        E_trailer_min=None,
        E_trailer_init=None,
        stations={},
        active_stations=set(),
        power_source="A",
        refrigeration_on=False,
        wait_max_steps=0,
    )
    assert solve_mrls(inst, max_seconds=5.0).status == SolverStatus.INFEASIBLE


def test_parallel_same_endpoints_distinguished_by_arc_id():
    table_ok = {(50, None): DriveTableEntry(True, 1, 40, None)}
    table_bad = {(50, None): DriveTableEntry(False, reason="peak_motor")}
    arcs = [
        ArcData("O", "D", 1, 0, 0, 1, drive_table=table_bad, arc_id="uphill"),
        ArcData("O", "D", 1, 0, 0, 2, drive_table=table_ok, arc_id="alt"),
    ]
    inst = RoutingInstance(
        name="par",
        nodes=["O", "D"],
        arcs=arcs,
        origin="O",
        destination="D",
        deadline_steps=5,
        E_truck_cap=50,
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
        wait_max_steps=0,
    )
    r = solve_mrls(inst, max_seconds=10.0)
    assert r.status == SolverStatus.OPTIMAL
    assert r.actions[0].get("arc_id") == "alt"


def test_charger_changes_route():
    arcs = [
        ArcData("O", "S", 1, 40, 0, 1, arc_id="a"),
        ArcData("S", "D", 1, 40, 0, 1, arc_id="b"),
        ArcData("O", "M", 1, 20, 0, 5, arc_id="c"),
        ArcData("M", "D", 1, 20, 0, 5, arc_id="d"),
    ]
    stations = {
        "S": StationData("S", 350, 0.95, 0, True, hypothetical_access=True),
    }
    base = dict(
        nodes=["O", "S", "M", "D"],
        arcs=arcs,
        origin="O",
        destination="D",
        deadline_steps=30,
        E_truck_cap=60,
        E_truck_min=0,
        E_truck_init=50,
        E_trailer_cap=None,
        E_trailer_min=None,
        E_trailer_init=None,
        power_source="A",
        refrigeration_on=False,
        energy_quantum_kwh=1,
        time_step_min=5,
        wait_max_steps=0,
    )
    with_s = RoutingInstance(name="w", stations=stations, active_stations={"S"}, **base)
    without = RoutingInstance(name="wo", stations=stations, active_stations=set(), **base)
    r1 = solve_mrls(with_s, max_seconds=10.0)
    r0 = solve_mrls(without, max_seconds=10.0)
    assert r1.status == SolverStatus.OPTIMAL
    assert r0.status == SolverStatus.OPTIMAL
    assert "S" in r1.path_nodes
    assert "S" not in r0.path_nodes


def test_intermediate_soc_floor_blocks_short_path():
    arcs = [
        ArcData("O", "D", 1, 80, 0, 1, arc_id="short"),
        ArcData("O", "M", 1, 30, 0, 5, arc_id="l1"),
        ArcData("M", "D", 1, 30, 0, 5, arc_id="l2"),
    ]
    inst = RoutingInstance(
        name="soc",
        nodes=["O", "M", "D"],
        arcs=arcs,
        origin="O",
        destination="D",
        deadline_steps=20,
        E_truck_cap=100,
        E_truck_min=10,
        E_truck_init=70,
        E_trailer_cap=None,
        E_trailer_min=None,
        E_trailer_init=None,
        stations={},
        active_stations=set(),
        power_source="A",
        refrigeration_on=False,
        wait_max_steps=0,
    )
    r = solve_mrls(inst, max_seconds=10.0)
    assert r.status == SolverStatus.OPTIMAL
    assert r.path_nodes == ["O", "M", "D"]


def test_failed_continuous_replay_not_ok():
    # Macro missing → continuous replay fails
    ctx = MultirouteMissionContext(
        od_id="t",
        macros_by_arc_id={},
        vehicle=load_vehicle(ROOT / "configs/vehicles/eactros_600.yaml"),
        fridge=load_refrigeration(ROOT / "configs/energy/refrigeration_approx.yaml"),
        weather=_toy_weather(),
        gcm_kg=25000.0,
        refrigeration_on=False,
        power_source="A",
        time_step_min=5,
        terrain_mode="flat",
    )
    inst = RoutingInstance(
        name="x",
        nodes=["O", "D"],
        arcs=[ArcData("O", "D", 1, 1, 0, 1, arc_id="missing")],
        origin="O",
        destination="D",
        deadline_steps=5,
        E_truck_cap=100,
        E_truck_min=0,
        E_truck_init=100,
        E_trailer_cap=None,
        E_trailer_min=None,
        E_trailer_init=None,
        stations={},
        active_stations=set(),
        power_source="A",
        refrigeration_on=False,
    )
    crep, _ = continuous_replay_multiroute(
        ctx, inst, [{"type": "DRIVE", "u": "O", "v": "D", "arc_id": "missing"}]
    )
    assert crep.ok is False


def test_split_arcs_inserts_charger_node():
    arc = DecisionArc(
        u="O",
        v="D",
        path_nodes=[1, 2, 3],
        osm_edge_pairs=[(1, 2), (2, 3)],
        length_m=1000.0,
        arc_id=make_arc_id([(1, 2), (2, 3)]),
    )
    chargers = [
        GroundedCharger(
            key="settat",
            node="settat",
            osm_node_id=2,
            official_name="SETTAT",
            osm_id="1",
            lat=0,
            lon=0,
            snap_distance_m=0,
            hgv_status="unknown",
            travel_direction="",
        )
    ]
    new_arcs, nodes, _ = split_arcs_at_charger_nodes(
        [arc], chargers=chargers, decision_nodes={"O": 1, "D": 3}
    )
    assert any(a.u == "O" and a.v == "settat" for a in new_arcs)
    assert any(a.u == "settat" and a.v == "D" for a in new_arcs)
    assert nodes["settat"] == 2


def test_induce_od_from_regenerated_decision_graph():
    path = ROOT / "data/processed/multiroute/decision_graph.json"
    paths = ROOT / "data/processed/multiroute/path_alternatives.csv"
    if not path.exists():
        pytest.skip("multiroute artifacts missing")
    dec = json.loads(path.read_text(encoding="utf-8"))
    rows = pd.read_csv(paths).to_dict(orient="records")
    arcs, origin, dest, nodes = induce_od_decision_arcs(dec, rows, "casa_marrakech")
    assert origin == "casablanca"
    assert dest == "marrakech"
    assert len(arcs) >= 2
    assert all(a.arc_id for a in arcs)
    assert len({a.arc_id for a in arcs}) == len(arcs)


def test_contract_od_path_union_compact():
    from morocco_etruck.optimization.multiroute_physics import contract_od_path_union
    from morocco_etruck.road_network import load_graph_from_csv

    nodes = ROOT / "data/processed/multiroute/nodes.csv"
    edges = ROOT / "data/processed/multiroute/edges.csv"
    paths = ROOT / "data/processed/multiroute/path_alternatives.csv"
    if not nodes.exists():
        pytest.skip("multiroute artifacts missing")
    G = load_graph_from_csv(nodes, edges)
    rows = pd.read_csv(paths).to_dict(orient="records")
    od_rows = [r for r in rows if r["od_id"] == "casa_marrakech"]
    short = [r for r in od_rows if r["method"] == "shortest_distance"]
    rest = sorted(
        [r for r in od_rows if r["method"] != "shortest_distance"],
        key=lambda r: -float(r["jaccard_distance_vs_shortest"]),
    )
    use = (short[:1] + rest)[:2]
    arcs, origin, dest, nodes_map = contract_od_path_union(G, use, "casa_marrakech")
    assert origin == "O" and dest == "D"
    assert 2 <= len(arcs) <= 40
    assert len({a.arc_id for a in arcs}) == len(arcs)


def test_offline_reproducible_arc_id():
    assert make_arc_id([(10, 20)]) == make_arc_id([(10, 20)])
