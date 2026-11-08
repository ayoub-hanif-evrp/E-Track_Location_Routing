"""Tiny independent placement enumeration checks (Task 04A)."""

from __future__ import annotations

from morocco_etruck.optimization.placement_problem import (
    LexScore,
    budget_ok,
    capital_recovery_factor,
    subset_capex,
)
from morocco_etruck.optimization.site_enumeration import all_subsets


def test_all_subsets_count_five_sites():
    ids = ["a", "b", "c", "d", "e"]
    subs = list(all_subsets(ids))
    assert len(subs) == 32
    assert frozenset() in subs
    assert frozenset(ids) in subs


def test_lex_prefers_coverage_then_cost():
    a = LexScore.from_parts(coverage=3.0, secondary_cost=100.0)
    b = LexScore.from_parts(coverage=2.0, secondary_cost=10.0)
    c = LexScore.from_parts(coverage=3.0, secondary_cost=50.0)
    assert min([a, b, c]) == c  # same coverage as a, lower cost; beats b on coverage


def test_budget_and_capex():
    capex = {"s1": 100.0, "s2": 100.0}
    assert subset_capex({"s1"}, capex) == 100.0
    assert budget_ok({"s1", "s2"}, capex, 200.0)
    assert not budget_ok({"s1", "s2"}, capex, 150.0)
    assert budget_ok({"s1", "s2"}, capex, None)


def test_crf_positive():
    crf = capital_recovery_factor(0.08, 15)
    assert 0.1 < crf < 0.15


def test_hand_two_site_selection_logic():
    """
    Hand case: two sites, two missions.
    M1 weight 1 feasible with empty; M2 weight 2 needs site A.
    Budget 100, capex A=B=100 → best is {A} coverage 3, not {B} if B doesn't serve M2.
    """
    # Pure logic over precomputed coverage table
    table = {
        frozenset(): (1.0, 0.0),  # coverage, secondary
        frozenset({"A"}): (3.0, 12.0),
        frozenset({"B"}): (1.0, 11.0),
        frozenset({"A", "B"}): (3.0, 22.0),
    }
    budget = 100.0
    capex = {"A": 100.0, "B": 100.0}
    feasible = [
        (s, cov, cost)
        for s, (cov, cost) in table.items()
        if subset_capex(set(s), capex) <= budget + 1e-9
    ]
    best = min(feasible, key=lambda t: LexScore.from_parts(t[1], t[2]))
    assert best[0] == frozenset({"A"})
    assert best[1] == 3.0
