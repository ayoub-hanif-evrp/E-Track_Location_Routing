"""Task 06B — exact arc_id replay and destination terminal checks."""

from __future__ import annotations

from morocco_etruck.optimization.label_setting import SolverStatus, solve_mrls
from morocco_etruck.optimization.problem import ArcData, RoutingInstance
from morocco_etruck.optimization.replay import replay_solution, resolve_drive_arc


def _base_inst(*, arcs: list[ArcData], nodes: list[str] | None = None) -> RoutingInstance:
    node_set = nodes or sorted({n for a in arcs for n in (a.u, a.v)} | {"O", "D"})
    return RoutingInstance(
        name="exact_arc_replay",
        nodes=list(node_set),
        arcs=arcs,
        origin="O",
        destination="D",
        deadline_steps=50,
        E_truck_cap=100,
        E_truck_min=10,
        E_truck_init=100,
        E_trailer_cap=None,
        E_trailer_min=None,
        E_trailer_init=None,
        stations={},
        active_stations=set(),
        power_source="A",
        refrigeration_on=False,
        wait_max_steps=0,
        energy_quantum_kwh=1,
    )


def test_resolve_prefers_unique_arc_id():
    arcs = [
        ArcData("O", "D", 1, 5, 0, road_cost=10, arc_id="cheap"),
        ArcData("O", "D", 1, 20, 0, road_cost=10, arc_id="thirsty"),
    ]
    inst = _base_inst(arcs=arcs)
    arc, err = resolve_drive_arc(inst, u="O", v="D", arc_id="thirsty")
    assert err is None and arc is not None
    assert arc.arc_id == "thirsty"
    assert arc.dE_truck_kwh == 20


def test_resolve_rejects_ambiguous_parallel_without_arc_id():
    arcs = [
        ArcData("O", "D", 1, 5, 0, road_cost=10, arc_id="a"),
        ArcData("O", "D", 1, 5, 0, road_cost=10, arc_id="b"),
    ]
    inst = _base_inst(arcs=arcs)
    arc, err = resolve_drive_arc(inst, u="O", v="D", arc_id=None)
    assert arc is None
    assert err == "ambiguous_parallel_arc"


def test_replay_rejects_wrong_parallel_arc_id():
    arcs = [
        ArcData("O", "D", 1, 5, 0, road_cost=10, arc_id="a"),
        ArcData("O", "D", 1, 5, 0, road_cost=10, arc_id="b"),
    ]
    inst = _base_inst(arcs=arcs)
    # Claim arc_id=a but endpoints imply we could have picked either; wrong id fails lookup
    bad = [{"type": "DRIVE", "u": "O", "v": "D", "arc_id": "missing", "road_cost": 10}]
    rep = replay_solution(inst, bad)
    assert not rep.ok
    assert rep.reason and "arc_id" in rep.reason


def test_replay_rejects_stopping_at_intermediate_node():
    arcs = [
        ArcData("O", "M", 1, 5, 0, road_cost=5, arc_id="om"),
        ArcData("M", "D", 1, 5, 0, road_cost=5, arc_id="md"),
    ]
    inst = _base_inst(arcs=arcs, nodes=["O", "M", "D"])
    actions = [{"type": "DRIVE", "u": "O", "v": "M", "arc_id": "om", "road_cost": 5}]
    rep = replay_solution(inst, actions, expected_cost=5)
    assert not rep.ok
    assert rep.reason and "not_at_destination" in rep.reason


def test_replay_ok_with_correct_arc_id_through_destination():
    arcs = [
        ArcData("O", "D", 1, 5, 0, road_cost=10, arc_id="a"),
        ArcData("O", "D", 1, 40, 0, road_cost=10, arc_id="b"),
    ]
    inst = _base_inst(arcs=arcs)
    r = solve_mrls(inst)
    assert r.status == SolverStatus.OPTIMAL
    assert any(a.get("arc_id") == "a" for a in r.actions)
    rep = replay_solution(inst, r.actions, expected_cost=r.objective)
    assert rep.ok
    assert rep.path_nodes[-1] == "D"


def test_replay_unique_uv_without_arc_id_still_works():
    arcs = [ArcData("O", "D", 1, 5, 0, road_cost=7)]
    inst = _base_inst(arcs=arcs)
    actions = [{"type": "DRIVE", "u": "O", "v": "D", "road_cost": 7}]
    rep = replay_solution(inst, actions, expected_cost=7)
    assert rep.ok
