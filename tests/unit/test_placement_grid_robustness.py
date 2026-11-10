"""Task 06B — objective mode / quantum plumbing for placement prep."""

from __future__ import annotations

from morocco_etruck.optimization.label_setting import SolverStatus, solve_mrls
from morocco_etruck.optimization.problem import ArcData, RoutingInstance, StationData
from morocco_etruck.optimization.multiroute_adapter import clone_physics_instance_for_subset


def _toy(mode: str) -> RoutingInstance:
    st = StationData("S", power_kw=60, eta=1.0, price_cents_per_grid_kwh=2, compatible=True)
    return RoutingInstance(
        name="toy",
        nodes=["O", "S", "D"],
        arcs=[
            ArcData("O", "S", 1, 40, 0, road_cost=5, arc_id="os"),
            ArcData("S", "D", 1, 40, 0, road_cost=5, arc_id="sd"),
        ],
        origin="O",
        destination="D",
        deadline_steps=40,
        E_truck_cap=100,
        E_truck_min=10,
        E_truck_init=50,
        E_trailer_cap=None,
        E_trailer_min=None,
        E_trailer_init=None,
        stations={"S": st},
        active_stations=set(),
        power_source="A",
        refrigeration_on=False,
        wait_max_steps=0,
        energy_quantum_kwh=10,
        objective_mode=mode,  # type: ignore[arg-type]
        terminal_target_truck_kwh=100,
        terminal_price_cents_per_grid_kwh=2,
        terminal_eta=1.0,
    )


def test_clone_preserves_objective_mode():
    tmpl = _toy("energy_replenishment_cost")
    inst = clone_physics_instance_for_subset(tmpl, active_stations={"S"}, name="x")
    assert inst.objective_mode == "energy_replenishment_cost"
    assert inst.terminal_price_cents_per_grid_kwh == 2


def test_replenishment_objective_exceeds_enroute_when_shortfall():
    legacy = _toy("enroute_incremental_cost")
    repl = _toy("energy_replenishment_cost")
    for inst in (legacy, repl):
        inst.active_stations = {"S"}
    r0 = solve_mrls(legacy)
    r1 = solve_mrls(repl)
    assert r0.status == SolverStatus.OPTIMAL
    assert r1.status == SolverStatus.OPTIMAL
    assert r0.final_label is not None and r1.final_label is not None
    # Same en-route decisions possible; replenishment total >= enroute-only objective.
    assert r1.objective is not None and r0.objective is not None
    assert r1.objective >= r0.objective


def test_stats_dict_exposes_labels_expanded():
    inst = _toy("enroute_incremental_cost")
    inst.active_stations = {"S"}
    r = solve_mrls(inst)
    assert isinstance(r.stats, dict)
    assert r.stats.get("labels_expanded", 0) >= 1
