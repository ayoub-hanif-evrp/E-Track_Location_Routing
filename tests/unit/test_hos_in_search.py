"""Stage B: continuous-driving resource inside MRLS (HOS-in-search)."""

from __future__ import annotations

from morocco_etruck.optimization.dominance import dominates
from morocco_etruck.optimization.label_setting import SolverStatus, solve_mrls
from morocco_etruck.optimization.problem import ArcData, RoutingInstance, StationData
from morocco_etruck.optimization.resource_transitions import Label, apply_drive, apply_wait


def _long_corridor(*, hos: bool, wait_max: int = 3) -> RoutingInstance:
    """O -8steps-> S -8steps-> D with time_step=30 min => 4h arcs.

    Max continuous = round(270/30)=9 steps. Two drives without break = 16 > 9.
    A 2-step WAIT (60 min) at S resets the clock under hos_in_search.
    """
    stations = {"S": StationData("S", power_kw=60.0, eta=1.0, price_cents_per_grid_kwh=0)}
    return RoutingInstance(
        name="hos_toy",
        nodes=["O", "S", "D"],
        arcs=[
            ArcData("O", "S", dt_steps=8, dE_truck_kwh=10, dE_trailer_kwh=0, road_cost=1, power_ok=True),
            ArcData("S", "D", dt_steps=8, dE_truck_kwh=10, dE_trailer_kwh=0, road_cost=1, power_ok=True),
        ],
        origin="O",
        destination="D",
        deadline_steps=40,
        E_truck_cap=200,
        E_truck_min=10,
        E_truck_init=100,
        E_trailer_cap=None,
        E_trailer_min=None,
        E_trailer_init=None,
        stations=stations,
        # No charging at S (avoids charge-lattice explosion); WAIT still allowed via hos_rest_nodes.
        active_stations=set(),
        power_source="A",
        refrigeration_on=False,
        aux_w=0.0,
        tru_mean_w=0.0,
        aux_kwh_per_step=0,
        tru_kwh_per_step=0,
        wait_max_steps=wait_max,
        time_step_min=30,
        energy_quantum_kwh=5,
        hos_in_search=hos,
        hos_rest_nodes=frozenset({"S"}),
    )


def test_hos_blocks_second_leg_without_break():
    inst = _long_corridor(hos=True, wait_max=0)
    lab = Label("O", 0, 100, None, 0, None, {"type": "START"}, 0, can_charge=True)
    r1 = apply_drive(inst, lab, inst.arcs[0], 1)
    assert r1.ok and r1.label is not None
    assert r1.label.drive_since_break_steps == 8
    r2 = apply_drive(inst, r1.label, inst.arcs[1], 2)
    assert not r2.ok
    assert r2.reason == "hos_continuous_driving_exceeded"


def test_hos_wait_reset_allows_second_leg():
    inst = _long_corridor(hos=True, wait_max=3)
    lab = Label("O", 0, 100, None, 0, None, {"type": "START"}, 0, can_charge=True)
    r1 = apply_drive(inst, lab, inst.arcs[0], 1)
    assert r1.ok and r1.label is not None
    w = apply_wait(inst, r1.label, 2, 2)  # 60 min >= 45
    assert w.ok and w.label is not None
    assert w.label.drive_since_break_steps == 0
    r2 = apply_drive(inst, w.label, inst.arcs[1], 3)
    assert r2.ok and r2.label is not None
    assert r2.label.node == "D"


def test_mrls_hos_inserts_wait_when_needed():
    inst = _long_corridor(hos=True, wait_max=2)
    res = solve_mrls(inst, max_seconds=5.0, max_expansions=20_000)
    assert res.status == SolverStatus.OPTIMAL, (res.status, res.stats)
    types = [a.get("type") for a in res.actions]
    assert "WAIT" in types
    assert types.count("DRIVE") >= 2


def test_mrls_without_hos_skips_wait():
    # wait_max=0 so the energy-only search cannot pad; path is still feasible.
    inst = _long_corridor(hos=False, wait_max=0)
    res = solve_mrls(inst, max_seconds=5.0, max_expansions=20_000)
    assert res.status == SolverStatus.OPTIMAL, (res.status, res.stats)
    types = [a.get("type") for a in res.actions]
    assert "WAIT" not in types
    assert types.count("DRIVE") >= 2


def test_dominance_prefers_lower_drive_clock():
    a = Label("S", 5, 80, None, 10, None, {}, 1, can_charge=True, drive_since_break_steps=2)
    b = Label("S", 5, 80, None, 10, None, {}, 2, can_charge=True, drive_since_break_steps=5)
    assert dominates(a, b)
    assert not dominates(b, a)
