"""Independent hand-calculated transition oracle (does not import resource_transitions)."""

from __future__ import annotations

from pathlib import Path

import pytest

from morocco_etruck.optimization.instances import load_synthetic_instances
from morocco_etruck.optimization.label_setting import SolverStatus, solve_mrls
from morocco_etruck.optimization.problem import (
    ArcData,
    InstanceValidationError,
    RoutingInstance,
    StationData,
    validate_routing_instance,
)
from morocco_etruck.optimization.replay import replay_solution

ROOT = Path(__file__).resolve().parents[2]


def _oracle_drive(
    E_truck: int,
    E_trailer: int | None,
    *,
    dE_truck: int,
    dE_trailer: int,
    dt: int,
    t: int,
    cost: int,
    road_cost: int,
    cap: int,
    emin: int,
    deadline: int,
    power_ok: bool,
) -> tuple[bool, int, int, int | None, int, str | None]:
    """Pure integer DRIVE oracle — duplicated arithmetic for independence."""
    if not power_ok:
        return False, t, E_truck, E_trailer, cost, "peak"
    t2 = t + dt
    if t2 > deadline:
        return False, t, E_truck, E_trailer, cost, "deadline"
    Et = E_truck - dE_truck
    if Et > cap:
        Et = cap
    El = None if E_trailer is None else E_trailer - dE_trailer
    if Et < emin:
        return False, t, E_truck, E_trailer, cost, "floor"
    return True, t2, Et, El, cost + road_cost, None


def _oracle_charge(
    E_truck: int,
    *,
    delta: int,
    cap: int,
    emin: int,
    power_kw: float,
    eta: float,
    price: int,
    t: int,
    cost: int,
    deadline: int,
    time_step_min: int = 5,
    aux: int = 0,
) -> tuple[bool, int, int, int, str | None]:
    if delta <= 0 or E_truck + delta > cap and delta > cap - E_truck:
        head = cap - E_truck
        if delta > head:
            return False, t, E_truck, cost, "headroom"
    per = power_kw * eta * (time_step_min / 60.0)
    import math

    steps = max(1, int(math.ceil(delta / per)))
    t2 = t + steps
    if t2 > deadline:
        return False, t, E_truck, cost, "deadline"
    Et = E_truck + delta - aux * steps
    if Et < emin:
        return False, t, E_truck, cost, "floor"
    grid = int(math.ceil(delta / eta))
    return True, t2, min(cap, Et), cost + price * grid, None


def test_oracle_drive_matches_hand_numbers():
    ok, t2, Et, El, c2, reason = _oracle_drive(
        100,
        None,
        dE_truck=5,
        dE_trailer=0,
        dt=2,
        t=0,
        cost=0,
        road_cost=10,
        cap=100,
        emin=10,
        deadline=20,
        power_ok=True,
    )
    assert ok and reason is None
    assert (t2, Et, c2) == (2, 95, 10)


def test_oracle_charge_matches_hand_numbers():
    ok, t2, Et, c2, reason = _oracle_charge(
        10,
        delta=40,
        cap=100,
        emin=10,
        power_kw=60,
        eta=1.0,
        price=2,
        t=2,
        cost=5,
        deadline=30,
    )
    assert ok and reason is None
    assert t2 == 2 + 8  # 40 kWh / 5 kWh/step = 8
    assert Et == 50
    assert c2 == 5 + 80


def test_mrls_case_a_matches_oracle_objective():
    # Case A: single drive 5 kWh, cost 10 from E=100
    ok, t2, Et, _El, c2, _r = _oracle_drive(
        100, None, dE_truck=5, dE_trailer=0, dt=2, t=0, cost=0, road_cost=10,
        cap=100, emin=10, deadline=20, power_ok=True,
    )
    assert ok and c2 == 10 and Et == 95
    insts = load_synthetic_instances(ROOT / "configs/optimization/synthetic_instances.yaml")
    a = next(i for i in insts if i.name == "A_no_charge")
    r = solve_mrls(a)
    assert r.status == SolverStatus.OPTIMAL
    assert r.objective == c2


def test_validate_rejects_negative_cost():
    bad = RoutingInstance(
        name="bad",
        nodes=["O", "D"],
        arcs=[ArcData("O", "D", 1, 1, 0, road_cost=-1)],
        origin="O",
        destination="D",
        deadline_steps=10,
        E_truck_cap=10,
        E_truck_min=0,
        E_truck_init=10,
        E_trailer_cap=None,
        E_trailer_min=None,
        E_trailer_init=None,
        stations={},
        active_stations=set(),
        power_source="A",
        refrigeration_on=False,
        wait_max_steps=0,
    )
    with pytest.raises(InstanceValidationError):
        validate_routing_instance(bad)


def test_validate_rejects_bad_eta():
    bad = RoutingInstance(
        name="bad",
        nodes=["O", "S"],
        arcs=[],
        origin="O",
        destination="S",
        deadline_steps=10,
        E_truck_cap=10,
        E_truck_min=0,
        E_truck_init=10,
        E_trailer_cap=None,
        E_trailer_min=None,
        E_trailer_init=None,
        stations={"S": StationData("S", 60, 0.0, 1)},
        active_stations={"S"},
        power_source="A",
        refrigeration_on=False,
        wait_max_steps=0,
    )
    with pytest.raises(InstanceValidationError):
        validate_routing_instance(bad)


def test_replay_all_optimal_synthetics():
    insts = load_synthetic_instances(ROOT / "configs/optimization/synthetic_instances.yaml")
    for inst in insts:
        r = solve_mrls(inst)
        if r.status != SolverStatus.OPTIMAL:
            continue
        rep = replay_solution(inst, r.actions, expected_cost=r.objective)
        assert rep.ok, f"{inst.name}: {rep.reason}"


def test_k_dominance_stress_prunes():
    insts = load_synthetic_instances(ROOT / "configs/optimization/synthetic_instances.yaml")
    k = next(i for i in insts if i.name == "K_dominance_stress")
    on = solve_mrls(k, use_dominance=True)
    off = solve_mrls(k, use_dominance=False)
    assert on.status == off.status == SolverStatus.OPTIMAL
    assert on.objective == off.objective == 21
    assert on.stats["labels_dominated"] >= 1
    assert on.stats["labels_expanded"] <= off.stats["labels_expanded"]
