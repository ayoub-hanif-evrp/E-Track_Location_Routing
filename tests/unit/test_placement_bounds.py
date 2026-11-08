"""Hand cases for proved placement bounds (Task 04B)."""

from __future__ import annotations

from morocco_etruck.optimization.placement_bounds import (
    budget_infeasible,
    can_prune_coverage,
    can_prune_secondary,
    coverage_upper_bound,
    secondary_lower_bound,
)
from morocco_etruck.optimization.placement_evaluation import SubsetEvaluation


def _ev(
    sites: set[str],
    *,
    cov: float,
    secondary: float,
    certified: bool = True,
    var: float = 0.0,
    capex: float = 0.0,
    annual: float = 0.0,
) -> SubsetEvaluation:
    return SubsetEvaluation(
        site_ids=frozenset(sites),
        budget_ok=True,
        certified=certified,
        coverage_total=cov,
        coverage_serviceable=cov,
        weight_total=10.0,
        weight_serviceable=10.0,
        infra_capex=capex,
        infra_annual=annual,
        variable_cost=var,
        secondary_cost=secondary,
        missions=[],
    )


def test_budget_prune():
    capex = {"A": 100.0, "B": 100.0}
    assert budget_infeasible({"A", "B"}, capex, 150.0)
    assert not budget_infeasible({"A"}, capex, 150.0)
    assert not budget_infeasible({"A", "B"}, capex, None)


def test_coverage_ub_and_prune():
    table = {
        frozenset({"A", "B"}): _ev({"A", "B"}, cov=5.0, secondary=20.0),
        frozenset({"A"}): _ev({"A"}, cov=3.0, secondary=12.0),
    }

    def evaluate_fn(installed: set[str]) -> SubsetEvaluation:
        return table[frozenset(installed)]

    ub = coverage_upper_bound(installed={"A"}, undecided={"B"}, evaluate_fn=evaluate_fn)
    assert ub.ub_certified
    assert ub.ub_coverage == 5.0
    assert can_prune_coverage(ub=ub, incumbent_coverage=6.0)
    assert not can_prune_coverage(ub=ub, incumbent_coverage=5.0)
    assert not can_prune_coverage(ub=ub, incumbent_coverage=4.0)


def test_uncertified_coverage_cannot_prune():
    def evaluate_fn(installed: set[str]) -> SubsetEvaluation:
        return _ev(installed, cov=0.0, secondary=0.0, certified=False)

    ub = coverage_upper_bound(installed=set(), undecided={"A"}, evaluate_fn=evaluate_fn)
    assert not ub.ub_certified
    assert not can_prune_coverage(ub=ub, incumbent_coverage=10.0)


def test_secondary_lb_prune():
    # UB eval at full relaxed set: cov=5, var=10; installed already CAPEX 200 → annual high
    crf = 0.1
    capex = {"A": 200.0, "B": 50.0}
    ub_ev = _ev({"A", "B"}, cov=5.0, secondary=30.0, var=10.0, capex=250.0, annual=25.0)
    ub = coverage_upper_bound(
        installed={"A"},
        undecided={"B"},
        evaluate_fn=lambda _s: ub_ev,
    )
    lb = secondary_lower_bound(installed={"A"}, capex=capex, crf=crf, ub_evaluation=ub_ev)
    # LB = 0.1*200 + 10 = 30
    assert abs(lb - 30.0) < 1e-9
    prune, lb2 = can_prune_secondary(
        ub=ub,
        installed={"A"},
        capex=capex,
        crf=crf,
        incumbent_coverage=5.0,
        incumbent_secondary=20.0,  # better incumbent secondary
    )
    assert prune
    assert lb2 is not None and lb2 > 20.0
