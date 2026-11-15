"""Hand cases for certified placement B&B (Task 04B)."""

from __future__ import annotations

from morocco_etruck.optimization.branch_and_bound import run_branch_and_bound_core
from morocco_etruck.optimization.placement_certification import OptimalityStatus
from morocco_etruck.optimization.placement_evaluation import SubsetEvaluation
from morocco_etruck.optimization.placement_problem import capital_recovery_factor


def _ev(
    sites: set[str],
    *,
    cov: float,
    var: float,
    capex_map: dict[str, float],
    crf: float,
    certified: bool = True,
) -> SubsetEvaluation:
    infra = sum(capex_map[s] for s in sites)
    annual = infra * crf
    return SubsetEvaluation(
        site_ids=frozenset(sites),
        budget_ok=True,
        certified=certified,
        coverage_total=cov,
        coverage_serviceable=cov,
        weight_total=10.0,
        weight_serviceable=10.0,
        infra_capex=infra,
        infra_annual=annual,
        variable_cost=var,
        secondary_cost=annual + var,
        missions=[],
    )


def _table_evaluator(table: dict[frozenset[str], SubsetEvaluation]):
    def evaluate_fn(installed: set[str]) -> SubsetEvaluation:
        key = frozenset(installed)
        if key not in table:
            raise KeyError(f"missing subset {key}")
        return table[key]

    return evaluate_fn


def test_single_site_optimum():
    crf = capital_recovery_factor(0.08, 15)
    capex = {"A": 100.0, "B": 100.0}
    # Empty cov 0; A cov 2; B cov 1; AB cov 2 higher cost
    table = {
        frozenset(): _ev(set(), cov=0.0, var=0.0, capex_map=capex, crf=crf),
        frozenset({"A"}): _ev({"A"}, cov=2.0, var=5.0, capex_map=capex, crf=crf),
        frozenset({"B"}): _ev({"B"}, cov=1.0, var=4.0, capex_map=capex, crf=crf),
        frozenset({"A", "B"}): _ev({"A", "B"}, cov=2.0, var=5.0, capex_map=capex, crf=crf),
    }
    res = run_branch_and_bound_core(
        site_ids=["A", "B"],
        capex=capex,
        max_capex=100.0,
        crf=crf,
        evaluate_fn=_table_evaluator(table),
    )
    assert res.optimality_status == OptimalityStatus.CERTIFIED_OPTIMAL
    assert res.incumbent is not None
    assert res.incumbent.site_ids == frozenset({"A"})
    assert res.incumbent.coverage_serviceable == 2.0


def test_two_sites_jointly_required():
    crf = 0.1
    capex = {"A": 50.0, "B": 50.0}
    table = {
        frozenset(): _ev(set(), cov=0.0, var=0.0, capex_map=capex, crf=crf),
        frozenset({"A"}): _ev({"A"}, cov=0.0, var=0.0, capex_map=capex, crf=crf),
        frozenset({"B"}): _ev({"B"}, cov=0.0, var=0.0, capex_map=capex, crf=crf),
        frozenset({"A", "B"}): _ev({"A", "B"}, cov=3.0, var=1.0, capex_map=capex, crf=crf),
    }
    res = run_branch_and_bound_core(
        site_ids=["A", "B"],
        capex=capex,
        max_capex=100.0,
        crf=crf,
        evaluate_fn=_table_evaluator(table),
    )
    assert res.optimality_status == OptimalityStatus.CERTIFIED_OPTIMAL
    assert res.incumbent is not None
    assert res.incumbent.site_ids == frozenset({"A", "B"})


def test_budget_cut_excludes_expensive_pair():
    crf = 0.1
    capex = {"A": 100.0, "B": 100.0}
    table = {
        frozenset(): _ev(set(), cov=0.0, var=0.0, capex_map=capex, crf=crf),
        frozenset({"A"}): _ev({"A"}, cov=1.0, var=2.0, capex_map=capex, crf=crf),
        frozenset({"B"}): _ev({"B"}, cov=1.0, var=3.0, capex_map=capex, crf=crf),
        frozenset({"A", "B"}): _ev({"A", "B"}, cov=5.0, var=1.0, capex_map=capex, crf=crf),
    }
    res = run_branch_and_bound_core(
        site_ids=["A", "B"],
        capex=capex,
        max_capex=100.0,
        crf=crf,
        evaluate_fn=_table_evaluator(table),
    )
    assert res.optimality_status == OptimalityStatus.CERTIFIED_OPTIMAL
    assert res.incumbent is not None
    assert res.incumbent.site_ids == frozenset({"A"})  # cheaper var at equal cov
    assert res.stats.prune_budget >= 1


def test_equal_coverage_prefers_lower_opex():
    crf = 0.1
    capex = {"A": 100.0, "B": 100.0}
    table = {
        frozenset(): _ev(set(), cov=0.0, var=0.0, capex_map=capex, crf=crf),
        frozenset({"A"}): _ev({"A"}, cov=2.0, var=10.0, capex_map=capex, crf=crf),
        frozenset({"B"}): _ev({"B"}, cov=2.0, var=4.0, capex_map=capex, crf=crf),
        frozenset({"A", "B"}): _ev({"A", "B"}, cov=2.0, var=4.0, capex_map=capex, crf=crf),
    }
    res = run_branch_and_bound_core(
        site_ids=["A", "B"],
        capex=capex,
        max_capex=100.0,
        crf=crf,
        evaluate_fn=_table_evaluator(table),
    )
    assert res.incumbent is not None
    assert res.incumbent.site_ids == frozenset({"B"})


def test_coverage_prune_fires():
    crf = 0.1
    # Three sites; only A and B serve; C useless. Budget unlimited.
    capex = {"A": 10.0, "B": 10.0, "C": 10.0}
    table = {}
    for mask in range(8):
        sites = {s for i, s in enumerate(["A", "B", "C"]) if mask & (1 << i)}
        cov = (1.0 if "A" in sites else 0.0) + (1.0 if "B" in sites else 0.0)
        table[frozenset(sites)] = _ev(sites, cov=cov, var=0.0, capex_map=capex, crf=crf)
    res = run_branch_and_bound_core(
        site_ids=["A", "B", "C"],
        capex=capex,
        max_capex=None,
        crf=crf,
        evaluate_fn=_table_evaluator(table),
    )
    assert res.optimality_status == OptimalityStatus.CERTIFIED_OPTIMAL
    assert res.incumbent is not None
    assert res.incumbent.coverage_serviceable == 2.0
    assert "A" in res.incumbent.site_ids and "B" in res.incumbent.site_ids


def test_secondary_prune_with_expensive_committed():
    """
    Hand case forcing a proved secondary-cost prune under exclude-first DFS:

    Sites X (expensive, CAPEX 500) then Y (cheap, CAPEX 100), equal coverage 1.
    Exclude-first explores {Y} first → incumbent secondary = 11.
    Then node installed={X}, undecided={Y}: UB cov=1, LB = 0.1*500+1 = 51 > 11
    ⇒ prune_secondary > 0. Optimum remains {Y}.
    """
    crf = 0.1
    capex = {"X": 500.0, "Y": 100.0}
    table = {
        frozenset(): _ev(set(), cov=0.0, var=0.0, capex_map=capex, crf=crf),
        frozenset({"Y"}): _ev({"Y"}, cov=1.0, var=1.0, capex_map=capex, crf=crf),
        frozenset({"X"}): _ev({"X"}, cov=1.0, var=1.0, capex_map=capex, crf=crf),
        frozenset({"X", "Y"}): _ev({"X", "Y"}, cov=1.0, var=1.0, capex_map=capex, crf=crf),
    }
    res = run_branch_and_bound_core(
        site_ids=["X", "Y"],
        capex=capex,
        max_capex=None,
        crf=crf,
        evaluate_fn=_table_evaluator(table),
        install_first=False,
    )
    assert res.optimality_status == OptimalityStatus.CERTIFIED_OPTIMAL
    assert res.incumbent is not None
    assert res.incumbent.site_ids == frozenset({"Y"})
    assert res.stats.prune_secondary > 0

    from morocco_etruck.optimization.placement_problem import LexScore
    from morocco_etruck.optimization.site_enumeration import all_subsets

    best = None
    for subset in all_subsets(["X", "Y"]):
        ev = table[frozenset(subset)]
        if best is None or LexScore.from_parts(
            ev.coverage_serviceable, ev.secondary_cost
        ) < LexScore.from_parts(best.coverage_serviceable, best.secondary_cost):
            best = ev
    assert best is not None
    assert best.site_ids == res.incumbent.site_ids
    assert abs(best.secondary_cost - res.incumbent.secondary_cost) < 1e-9


def test_limit_reached_cannot_false_prove():
    crf = 0.1
    capex = {"A": 100.0, "B": 100.0}
    table = {
        frozenset(): _ev(set(), cov=0.0, var=0.0, capex_map=capex, crf=crf),
        frozenset({"A"}): _ev({"A"}, cov=1.0, var=1.0, capex_map=capex, crf=crf),
        frozenset({"B"}): _ev({"B"}, cov=1.0, var=1.0, capex_map=capex, crf=crf),
        frozenset({"A", "B"}): _ev({"A", "B"}, cov=2.0, var=1.0, capex_map=capex, crf=crf),
    }
    res = run_branch_and_bound_core(
        site_ids=["A", "B"],
        capex=capex,
        max_capex=None,
        crf=crf,
        evaluate_fn=_table_evaluator(table),
        node_limit=1,  # stop immediately after root visit start
    )
    assert res.optimality_status == OptimalityStatus.LIMIT_REACHED
    assert res.optimality_status != OptimalityStatus.CERTIFIED_OPTIMAL


def test_injected_limit_reached_leaf_uncertified_not_certified_global():
    crf = 0.1
    capex = {"A": 50.0, "B": 50.0}

    def evaluate_fn(installed: set[str]) -> SubsetEvaluation:
        # Full set uncertified (LIMIT_REACHED injection)
        if installed == {"A", "B"}:
            return _ev(installed, cov=0.0, var=0.0, capex_map=capex, crf=crf, certified=False)
        cov = float(len(installed))
        return _ev(installed, cov=cov, var=1.0, capex_map=capex, crf=crf, certified=True)

    res = run_branch_and_bound_core(
        site_ids=["A", "B"],
        capex=capex,
        max_capex=None,
        crf=crf,
        evaluate_fn=evaluate_fn,
    )
    # Uncertified leaf means cannot claim CERTIFIED_OPTIMAL
    assert res.optimality_status == OptimalityStatus.INCUMBENT_UNPROVED
    assert res.incumbent is not None
    assert res.incumbent.site_ids in (frozenset({"A"}), frozenset({"B"}))


def test_mrls_limit_reached_style_uncertified_blocks_certified_optimal():
    """Task 08 contract: MRLS LIMIT_REACHED ⇒ subset certified=False ⇒ not CERTIFIED_OPTIMAL."""
    crf = 0.1
    capex = {"S0": 50.0, "S1": 50.0}

    def evaluate_fn(installed: set[str]) -> SubsetEvaluation:
        # Simulate one mission returning LIMIT_REACHED on every non-empty subset
        # that includes S1 (artificial unresolved evaluation).
        if "S1" in installed:
            return _ev(
                installed,
                cov=0.0,
                var=0.0,
                capex_map=capex,
                crf=crf,
                certified=False,
            )
        cov = 1.0 if installed else 0.0
        return _ev(installed, cov=cov, var=1.0, capex_map=capex, crf=crf, certified=True)

    res = run_branch_and_bound_core(
        site_ids=["S0", "S1"],
        capex=capex,
        max_capex=None,
        crf=crf,
        evaluate_fn=evaluate_fn,
    )
    assert res.optimality_status != OptimalityStatus.CERTIFIED_OPTIMAL
    assert res.optimality_status == OptimalityStatus.INCUMBENT_UNPROVED


def test_budget_relaxed_superset_routing_certified_supports_ub_not_incumbent():
    """
    P0.4: over-budget installed∪undecided may be routing-certified (UB) while
    budget_ok=False, and must never become the incumbent.
    """
    from morocco_etruck.optimization.placement_bounds import coverage_upper_bound

    crf = 0.1
    capex = {"A": 100.0, "B": 100.0}

    def evaluate_fn(installed: set[str]) -> SubsetEvaluation:
        infra = sum(capex[s] for s in installed)
        budget = infra <= 100.0 + 1e-9
        # Both sites together: higher coverage, routing certified, over budget
        if installed == {"A", "B"}:
            return SubsetEvaluation(
                site_ids=frozenset(installed),
                budget_ok=False,
                certified=True,  # routing resolved
                coverage_total=2.0,
                coverage_serviceable=2.0,
                weight_total=2.0,
                weight_serviceable=2.0,
                infra_capex=infra,
                infra_annual=infra * crf,
                variable_cost=1.0,
                secondary_cost=infra * crf + 1.0,
                missions=[],
            )
        cov = 1.0 if installed else 0.0
        return SubsetEvaluation(
            site_ids=frozenset(installed),
            budget_ok=budget,
            certified=True,
            coverage_total=cov,
            coverage_serviceable=cov,
            weight_total=2.0,
            weight_serviceable=2.0,
            infra_capex=infra,
            infra_annual=infra * crf,
            variable_cost=2.0 if installed else 0.0,
            secondary_cost=infra * crf + (2.0 if installed else 0.0),
            missions=[],
        )

    ub = coverage_upper_bound(
        installed=set(),
        undecided={"A", "B"},
        evaluate_fn=evaluate_fn,
    )
    assert ub.ub_certified is True
    assert ub.ub_coverage == 2.0

    res = run_branch_and_bound_core(
        site_ids=["A", "B"],
        capex=capex,
        max_capex=100.0,
        crf=crf,
        evaluate_fn=evaluate_fn,
    )
    assert res.incumbent is not None
    assert res.incumbent.budget_ok is True
    assert res.incumbent.site_ids in (frozenset({"A"}), frozenset({"B"}))
    assert res.incumbent.site_ids != frozenset({"A", "B"})


def test_over_budget_subset_never_incumbent_even_if_routing_certified():
    from morocco_etruck.optimization.branch_and_bound import _lex_better

    crf = 0.1
    capex = {"A": 200.0}
    over = SubsetEvaluation(
        site_ids=frozenset({"A"}),
        budget_ok=False,
        certified=True,
        coverage_total=5.0,
        coverage_serviceable=5.0,
        weight_total=5.0,
        weight_serviceable=5.0,
        infra_capex=200.0,
        infra_annual=20.0,
        variable_cost=0.0,
        secondary_cost=20.0,
        missions=[],
    )
    assert _lex_better(over, None) is False


def test_dedicated_budget_relaxed_ub_fn_used_for_coverage_bound():
    """Coverage UB must call evaluate_coverage_ub_fn, not the budgeted leaf evaluator."""
    crf = 0.1
    capex = {"A": 100.0, "B": 100.0}
    calls = {"leaf": 0, "ub": 0}

    def leaf_fn(installed: set[str]) -> SubsetEvaluation:
        calls["leaf"] += 1
        infra = sum(capex[s] for s in installed)
        return SubsetEvaluation(
            site_ids=frozenset(installed),
            budget_ok=infra <= 100.0 + 1e-9,
            certified=True,
            coverage_total=1.0 if installed else 0.0,
            coverage_serviceable=1.0 if installed else 0.0,
            weight_total=2.0,
            weight_serviceable=2.0,
            infra_capex=infra,
            infra_annual=infra * crf,
            variable_cost=1.0,
            secondary_cost=infra * crf + 1.0,
            missions=[],
        )

    def ub_fn(installed: set[str]) -> SubsetEvaluation:
        calls["ub"] += 1
        infra = sum(capex[s] for s in installed)
        # Superset A∪B: higher coverage, budget relaxed → budget_ok True
        cov = 2.0 if installed == {"A", "B"} else (1.0 if installed else 0.0)
        return SubsetEvaluation(
            site_ids=frozenset(installed),
            budget_ok=True,
            certified=True,
            coverage_total=cov,
            coverage_serviceable=cov,
            weight_total=2.0,
            weight_serviceable=2.0,
            infra_capex=infra,
            infra_annual=infra * crf,
            variable_cost=0.5,
            secondary_cost=infra * crf + 0.5,
            missions=[],
        )

    res = run_branch_and_bound_core(
        site_ids=["A", "B"],
        capex=capex,
        max_capex=100.0,
        crf=crf,
        evaluate_fn=leaf_fn,
        evaluate_coverage_ub_fn=ub_fn,
    )
    assert calls["ub"] > 0
    assert res.incumbent is not None
    assert res.incumbent.budget_ok is True
    assert len(res.incumbent.site_ids) <= 1


def test_bb_matches_exhaustive_across_tight_and_all_sites_budgets():
    """B&B agrees with exhaustive best subset under B=0, tight, and Ball."""
    import itertools

    crf = 0.1
    sites = ["A", "B", "C"]
    capex = {"A": 100.0, "B": 100.0, "C": 100.0}
    # Coverage: A alone 1, B alone 1, C alone 0, A+B 2, A+C 1, B+C 1, A+B+C 2
    # Secondary var: cheaper with fewer sites when coverage ties
    var = {
        frozenset(): 0.0,
        frozenset({"A"}): 5.0,
        frozenset({"B"}): 6.0,
        frozenset({"C"}): 9.0,
        frozenset({"A", "B"}): 3.0,
        frozenset({"A", "C"}): 5.0,
        frozenset({"B", "C"}): 6.0,
        frozenset({"A", "B", "C"}): 2.5,
    }
    cov = {
        frozenset(): 0.0,
        frozenset({"A"}): 1.0,
        frozenset({"B"}): 1.0,
        frozenset({"C"}): 0.0,
        frozenset({"A", "B"}): 2.0,
        frozenset({"A", "C"}): 1.0,
        frozenset({"B", "C"}): 1.0,
        frozenset({"A", "B", "C"}): 2.0,
    }

    def evaluate_fn(installed: set[str]) -> SubsetEvaluation:
        key = frozenset(installed)
        infra = sum(capex[s] for s in installed)
        return SubsetEvaluation(
            site_ids=key,
            budget_ok=True,  # budget checked by B&B / enum filter
            certified=True,
            coverage_total=cov[key],
            coverage_serviceable=cov[key],
            weight_total=2.0,
            weight_serviceable=2.0,
            infra_capex=infra,
            infra_annual=infra * crf,
            variable_cost=var[key],
            secondary_cost=infra * crf + var[key],
            missions=[],
        )

    def exhaustive_best(max_capex: float | None) -> SubsetEvaluation | None:
        best = None
        for r in range(len(sites) + 1):
            for combo in itertools.combinations(sites, r):
                s = set(combo)
                infra = sum(capex[x] for x in s)
                if max_capex is not None and infra > float(max_capex) + 1e-9:
                    continue
                ev = evaluate_fn(s)
                if best is None:
                    best = ev
                    continue
                from morocco_etruck.optimization.placement_problem import LexScore

                if LexScore.from_parts(
                    ev.coverage_serviceable, ev.secondary_cost, True
                ) < LexScore.from_parts(
                    best.coverage_serviceable, best.secondary_cost, True
                ):
                    best = ev
        return best

    for B in (0.0, 100.0, 200.0, None):
        enum = exhaustive_best(B)
        bb = run_branch_and_bound_core(
            site_ids=sites,
            capex=capex,
            max_capex=B,
            crf=crf,
            evaluate_fn=evaluate_fn,
            evaluate_coverage_ub_fn=evaluate_fn,
        )
        if enum is None:
            assert bb.incumbent is None
        else:
            assert bb.incumbent is not None
            assert bb.incumbent.site_ids == enum.site_ids
            assert abs(bb.incumbent.coverage_serviceable - enum.coverage_serviceable) < 1e-12
            assert abs(bb.incumbent.secondary_cost - enum.secondary_cost) < 1e-9
            assert bb.optimality_status == OptimalityStatus.CERTIFIED_OPTIMAL
