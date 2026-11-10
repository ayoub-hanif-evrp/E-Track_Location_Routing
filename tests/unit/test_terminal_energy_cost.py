"""Task 06B — energy replenishment objective and MRLS termination."""

from __future__ import annotations

from morocco_etruck.optimization.label_setting import SolverStatus, solve_mrls
from morocco_etruck.optimization.problem import (
    ArcData,
    RoutingInstance,
    StationData,
    terminal_replenishment_cents,
    total_objective_cents,
)
from morocco_etruck.optimization.reference_solver import solve_reference
from morocco_etruck.optimization.replay import replay_solution


def _inst(
    arcs: list[ArcData],
    *,
    mode: str = "enroute_incremental_cost",
    stations: dict[str, StationData] | None = None,
    active: set[str] | None = None,
    E_init: int = 100,
    E_cap: int = 100,
    E_min: int = 10,
    nodes: list[str] | None = None,
    wait_max_steps: int = 0,
    terminal_price: int | None = 2,
    terminal_eta: float | None = 1.0,
) -> RoutingInstance:
    node_set = nodes or sorted({n for a in arcs for n in (a.u, a.v)})
    return RoutingInstance(
        name="terminal_energy",
        nodes=list(node_set),
        arcs=arcs,
        origin="O",
        destination="D",
        deadline_steps=80,
        E_truck_cap=E_cap,
        E_truck_min=E_min,
        E_truck_init=E_init,
        E_trailer_cap=None,
        E_trailer_min=None,
        E_trailer_init=None,
        stations=stations or {},
        active_stations=active or set(),
        power_source="A",
        refrigeration_on=False,
        wait_max_steps=wait_max_steps,
        energy_quantum_kwh=1,
        objective_mode=mode,  # type: ignore[arg-type]
        terminal_target_truck_kwh=E_cap,
        terminal_price_cents_per_grid_kwh=terminal_price,
        terminal_eta=terminal_eta,
    )


def test_legacy_equal_road_cost_ignores_battery_drain():
    """Equal road costs → legacy objective ties on cost; MRLS picks first by heap (lower dE wins dominance)."""
    arcs = [
        ArcData("O", "D", 1, 10, 0, road_cost=20, arc_id="thirsty"),
        ArcData("O", "D", 1, 40, 0, road_cost=20, arc_id="hungrier"),
    ]
    legacy = _inst(arcs, mode="enroute_incremental_cost")
    r = solve_mrls(legacy)
    assert r.status == SolverStatus.OPTIMAL
    assert r.objective == 20
    # Dominance prefers higher remaining energy at same cost → thirsty arc.
    assert r.final_label is not None
    assert r.final_label.E_truck == 90


def test_replenishment_prefers_lower_total_electricity():
    arcs = [
        ArcData("O", "D", 1, 10, 0, road_cost=20, arc_id="efficient"),
        ArcData("O", "D", 1, 40, 0, road_cost=20, arc_id="wasteful"),
    ]
    inst = _inst(arcs, mode="energy_replenishment_cost", terminal_price=2, terminal_eta=1.0)
    # efficient: E_final=90 → shortfall 10 → term=20 → total=40
    # wasteful: E_final=60 → shortfall 40 → term=80 → total=100
    r = solve_mrls(inst)
    assert r.status == SolverStatus.OPTIMAL
    assert r.objective == 40
    assert any(a.get("arc_id") == "efficient" for a in r.actions)
    ref = solve_reference(inst)
    assert ref.status == SolverStatus.OPTIMAL
    assert ref.objective == r.objective
    rep = replay_solution(inst, r.actions, expected_cost=r.objective)
    assert rep.ok


def test_first_destination_not_global_under_replenishment():
    """
    Cheap thirsty direct arc arrives first in en-route order, but a slightly
    dearer efficient path has lower total with terminal valuation.
    """
    arcs = [
        ArcData("O", "D", 1, 50, 0, road_cost=10, arc_id="cheap_thirsty"),
        ArcData("O", "M", 1, 5, 0, road_cost=8, arc_id="om"),
        ArcData("M", "D", 1, 5, 0, road_cost=8, arc_id="md"),
    ]
    inst = _inst(
        arcs,
        mode="energy_replenishment_cost",
        nodes=["O", "M", "D"],
        terminal_price=2,
        terminal_eta=1.0,
        E_init=100,
        E_cap=100,
    )
    # cheap_thirsty: enroute=10, E=50, term=2*50=100, total=110
    # O-M-D: enroute=16, E=90, term=2*10=20, total=36
    r = solve_mrls(inst)
    assert r.status == SolverStatus.OPTIMAL
    assert r.objective == 36
    assert r.path_nodes == ["O", "M", "D"]
    ref = solve_reference(inst)
    assert ref.objective == 36
    assert ref.path_nodes == ["O", "M", "D"]


def test_no_double_count_enroute_charge_and_terminal():
    st = StationData("S", power_kw=60, eta=1.0, price_cents_per_grid_kwh=2, compatible=True)
    arcs = [
        ArcData("O", "S", 1, 40, 0, road_cost=5, arc_id="os"),
        ArcData("S", "D", 1, 40, 0, road_cost=5, arc_id="sd"),
    ]
    inst = _inst(
        arcs,
        mode="energy_replenishment_cost",
        stations={"S": st},
        active={"S"},
        nodes=["O", "S", "D"],
        E_init=50,
        E_cap=100,
        E_min=10,
        terminal_price=2,
        terminal_eta=1.0,
    )
    r = solve_mrls(inst)
    assert r.status == SolverStatus.OPTIMAL
    assert r.final_label is not None
    # Terminal prices only remaining shortfall after en-route purchases.
    term = terminal_replenishment_cents(inst, r.final_label.E_truck, None)
    assert r.objective == total_objective_cents(
        inst, r.final_label.cost, r.final_label.E_truck, None
    )
    assert r.objective == r.final_label.cost + term
    # En-route charge cost is inside label.cost; terminal does not re-add charged kWh.
    charged = sum(int(a["delta_e_kwh"]) for a in r.actions if a.get("type") == "CHARGE")
    assert charged >= 0
    assert term == 2 * max(0, 100 - r.final_label.E_truck)
    ref = solve_reference(inst)
    assert ref.objective == r.objective


def test_legacy_still_first_pop_optimal_matches_reference():
    arcs = [
        ArcData("O", "D", 1, 5, 0, road_cost=10, arc_id="a"),
        ArcData("O", "M", 1, 5, 0, road_cost=6, arc_id="om"),
        ArcData("M", "D", 1, 5, 0, road_cost=6, arc_id="md"),
    ]
    inst = _inst(arcs, mode="enroute_incremental_cost", nodes=["O", "M", "D"])
    r = solve_mrls(inst)
    ref = solve_reference(inst)
    assert r.status == SolverStatus.OPTIMAL
    assert ref.objective == r.objective == 10
