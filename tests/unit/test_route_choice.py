"""Synthetic route-choice validation (Task 05A Stage 4)."""

from __future__ import annotations

from pathlib import Path

from morocco_etruck.optimization.instances import load_synthetic_instances
from morocco_etruck.optimization.label_setting import SolverStatus, solve_mrls
from morocco_etruck.optimization.reference_solver import solve_reference
from morocco_etruck.optimization.replay import replay_solution
from morocco_etruck.optimization.route_choice_graph import (
    diverse_paths,
    jaccard_distance,
    path_edge_set,
)
import networkx as nx

ROOT = Path(__file__).resolve().parents[2]
SYN = ROOT / "configs/optimization/synthetic_route_choice.yaml"


def _by_name():
    return {i.name: i for i in load_synthetic_instances(SYN)}


def test_short_infeasible_long_ok_and_not_shortest_distance():
    inst = _by_name()["R1_short_infeasible_long_ok"]
    r = solve_mrls(inst)
    assert r.status == SolverStatus.OPTIMAL
    assert r.path_nodes == ["O", "M", "D"]
    # Shortest-distance path O->D is not chosen
    assert r.path_nodes != ["O", "D"]
    ref = solve_reference(inst)
    assert ref.status == SolverStatus.OPTIMAL
    assert ref.objective == r.objective
    assert ref.path_nodes == r.path_nodes
    rep = replay_solution(inst, r.actions, expected_cost=r.objective)
    assert rep.ok


def test_lower_energy_route_preferred():
    inst = _by_name()["R2_short_ok_but_long_cheaper_energy"]
    r = solve_mrls(inst)
    assert r.status == SolverStatus.OPTIMAL
    assert r.path_nodes == ["O", "B", "D"]
    ref = solve_reference(inst)
    assert ref.objective == r.objective


def test_charger_install_changes_route():
    with_s = _by_name()["R3_charger_enables_short"]
    without = _by_name()["R3b_no_charger_forces_long"]
    r1 = solve_mrls(with_s)
    r0 = solve_mrls(without)
    assert r1.status == SolverStatus.OPTIMAL
    assert r0.status == SolverStatus.OPTIMAL
    assert r1.path_nodes == ["O", "S", "D"]
    assert r0.path_nodes == ["O", "M", "D"]
    assert r1.path_nodes != r0.path_nodes


def test_oneway_and_reverse_infeasible():
    fwd = _by_name()["R4_oneway_respected"]
    rev = _by_name()["R4b_reverse_origin_infeasible"]
    assert solve_mrls(fwd).status == SolverStatus.OPTIMAL
    assert solve_mrls(rev).status == SolverStatus.INFEASIBLE
    assert solve_reference(rev).status == SolverStatus.INFEASIBLE


def test_refrigeration_changes_feasibility():
    off = _by_name()["R5_refrig_off_ok"]
    on = _by_name()["R5b_refrig_on_infeasible"]
    assert solve_mrls(off).status == SolverStatus.OPTIMAL
    assert solve_mrls(on).status == SolverStatus.INFEASIBLE


def test_diverse_paths_finds_alternative_on_toy_graph():
    G = nx.DiGraph()
    G.add_node(1, lon=0, lat=0)
    G.add_node(2, lon=1, lat=0)
    G.add_node(3, lon=0.5, lat=0.5)
    G.add_node(4, lon=2, lat=0)
    G.add_edge(1, 2, length_m=1000)
    G.add_edge(2, 4, length_m=1000)
    G.add_edge(1, 3, length_m=800)
    G.add_edge(3, 4, length_m=1500)
    recs = diverse_paths(G, 1, 4, od_id="toy", max_alternatives=3, min_jaccard_distance=0.2)
    assert len(recs) >= 2
    assert recs[0].method == "shortest_distance"
    jd = jaccard_distance(path_edge_set(recs[0].node_path), path_edge_set(recs[1].node_path))
    assert jd > 0
