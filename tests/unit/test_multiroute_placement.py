"""Task 05C — synthetic multi-route placement: enum certifies B&B; install changes route."""

from __future__ import annotations

from pathlib import Path

from morocco_etruck.optimization.branch_and_bound import run_branch_and_bound_core
from morocco_etruck.optimization.label_setting import SolverStatus, solve_mrls
from morocco_etruck.optimization.multiroute_adapter import clone_physics_instance_for_subset
from morocco_etruck.optimization.multiroute_placement import load_multiroute_placement_config
from morocco_etruck.optimization.placement_certification import OptimalityStatus
from morocco_etruck.optimization.placement_evaluation import SubsetEvaluation
from morocco_etruck.optimization.placement_problem import (
    PlacementSite,
    annualized_infra_cost,
    budget_ok,
    subset_capex,
)
from morocco_etruck.optimization.problem import ArcData, RoutingInstance, StationData
from morocco_etruck.optimization.site_enumeration import all_subsets

ROOT = Path(__file__).resolve().parents[2]


def _synth_template() -> RoutingInstance:
    """
    Two road alternatives:
      O -> chg_a -> D  (short, high energy) — needs charger to be feasible at low SOC
      O -> B -> D  (long, low energy) — always feasible without chargers
    Installing chg_a enables the short route (lower road_cost).
    """
    arcs = [
        # Short via charger: needs mid-route charge (40+40 from init 35)
        ArcData("O", "chg_a", 1, 30, 0, road_cost=1, arc_id="oa"),
        ArcData("chg_a", "D", 1, 30, 0, road_cost=1, arc_id="ad"),
        # Long alternative: still energy-infeasible from init 35 without charge
        ArcData("O", "B", 1, 25, 0, road_cost=5, arc_id="ob"),
        ArcData("B", "D", 1, 25, 0, road_cost=5, arc_id="bd"),
    ]
    stations = {
        "chg_a": StationData("chg_a", 350.0, 1.0, 0, True, official_name="A", osm_id="1"),
        "chg_dummy": StationData(
            "chg_dummy", 350.0, 1.0, 0, True, official_name="X", osm_id="2"
        ),
    }
    return RoutingInstance(
        name="synth_mr",
        nodes=["O", "chg_a", "B", "D", "chg_dummy"],
        arcs=arcs,
        origin="O",
        destination="D",
        deadline_steps=30,
        E_truck_cap=60,
        E_truck_min=0,
        E_truck_init=35,
        E_trailer_cap=None,
        E_trailer_min=None,
        E_trailer_init=None,
        stations=stations,
        active_stations=set(),
        power_source="A",
        refrigeration_on=False,
        energy_quantum_kwh=1,
        time_step_min=5,
        wait_max_steps=0,
    )


def test_install_changes_optimal_route():
    tmpl = _synth_template()
    without = clone_physics_instance_for_subset(tmpl, active_stations=set())
    with_a = clone_physics_instance_for_subset(tmpl, active_stations={"chg_a"})
    r0 = solve_mrls(without, max_seconds=10.0)
    r1 = solve_mrls(with_a, max_seconds=10.0)
    assert r0.status == SolverStatus.INFEASIBLE
    assert r1.status == SolverStatus.OPTIMAL
    assert "chg_a" in r1.path_nodes
    assert any(a.get("type") == "CHARGE" for a in r1.actions)


def test_bb_matches_enumeration_on_synthetic():
    tmpl = _synth_template()
    sites = [
        PlacementSite("y_a", "synth", "chg_a", "A"),
        PlacementSite("y_dummy", "synth", "chg_dummy", "Dummy"),
    ]
    capex = {"y_a": 100.0, "y_dummy": 100.0}
    crf = 0.1
    cents = 0.01
    max_capex = 200.0

    def evaluate_fn(installed: set[str]) -> SubsetEvaluation:
        active = {
            s.station_key
            for s in sites
            if s.id in installed and s.station_key in tmpl.stations
        }
        inst = clone_physics_instance_for_subset(tmpl, active_stations=active)
        r = solve_mrls(inst, max_seconds=10.0)
        served = r.status == SolverStatus.OPTIMAL
        obj = float(r.objective or 0) * cents if served else 0.0
        infra = subset_capex(installed, capex)
        infra_ann = annualized_infra_cost(installed, capex, crf)
        return SubsetEvaluation(
            site_ids=frozenset(installed),
            budget_ok=budget_ok(installed, capex, max_capex),
            certified=True,
            coverage_total=1.0 if served else 0.0,
            coverage_serviceable=1.0 if served else 0.0,
            weight_total=1.0,
            weight_serviceable=1.0,
            infra_capex=infra,
            infra_annual=infra_ann,
            variable_cost=obj,
            secondary_cost=infra_ann + obj,
            missions=[],
        )

    # Exhaustive
    best = None
    for subset in all_subsets([s.id for s in sites]):
        if not budget_ok(set(subset), capex, max_capex):
            continue
        ev = evaluate_fn(set(subset))
        if best is None:
            best = ev
        else:
            if ev.coverage_serviceable > best.coverage_serviceable + 1e-12 or (
                abs(ev.coverage_serviceable - best.coverage_serviceable) <= 1e-12
                and ev.secondary_cost + 1e-12 < best.secondary_cost
            ):
                best = ev

    bb = run_branch_and_bound_core(
        site_ids=[s.id for s in sites],
        capex=capex,
        max_capex=max_capex,
        crf=crf,
        evaluate_fn=evaluate_fn,
    )
    assert bb.optimality_status == OptimalityStatus.CERTIFIED_OPTIMAL
    assert best is not None and bb.incumbent is not None
    assert abs(best.coverage_serviceable - bb.incumbent.coverage_serviceable) <= 1e-9
    assert abs(best.secondary_cost - bb.incumbent.secondary_cost) <= 1e-6
    # Optimum installs the enabling charger (may or may not include dummy)
    assert "y_a" in bb.incumbent.site_ids


def test_load_multiroute_placement_config():
    path = ROOT / "configs/optimization/multiroute_placement_pilot.yaml"
    cfg = load_multiroute_placement_config(path, root=ROOT)
    assert len(cfg.sites) == 3
    assert "default" in cfg.demand_scenarios
    assert {s.station_key for s in cfg.sites} == {
        "settat_ca",
        "benguerir_ca",
        "amskroud_ca",
    }
