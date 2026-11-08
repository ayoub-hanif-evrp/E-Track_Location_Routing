"""
Proved coverage / secondary bounds for charger-placement B&B (Task 04B).

Assumption (feasibility monotonicity)
-------------------------------------
Under the current model (independent missions, optional charging, no shared
charger capacity / queues, nonnegative site costs, fixed directed paths):
adding an operational compatible site cannot make a previously feasible mission
infeasible, and cannot increase that mission's optimal discrete operating cost.

Invalidated by: shared capacity, queues, coupled schedules, negative costs,
or mandatory detours that add energy.

Coverage upper bound
--------------------
For node N, evaluate active stations = direction-filter(installed ∪ undecided).
This relaxes the budget (undecided treated as free). By monotonicity, any
descendant's served weight is ≤ this value when the evaluation is certified.
If ub_cov < cov* prune. If MRLS LIMIT_REACHED or replay fails, the bound is
uncertified → do not prune on coverage.

Secondary-cost lower bound (coverage tie)
-----------------------------------------
When ub_cov = cov* and the UB evaluation is certified:

  LB = CRF · CAPEX(installed) + Σ_{m served in UB} w_m · C_var_m(UB)

- CAPEX(descendant) ≥ CAPEX(installed) (nonnegative site costs).
- For each mission still served at coverage cov*, fewer sites ⇒ C_var ≥ C_var(UB).
- Missions counted in UB that a descendant drops would reduce coverage below
  ub_cov, so among coverage-tying descendants the served set is at least as
  costly in aggregate under this LB.

Prune only if LB > sec* + ε (strict). Do not use stronger operating-cost LBs
without a written proof.

Budget pruning
--------------
committed_capex > B ⇒ prune (nonnegative CAPEX). Cannot remove a feasible optimum.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from morocco_etruck.optimization.placement_evaluation import SubsetEvaluation
from morocco_etruck.optimization.placement_problem import annualized_infra_cost, subset_capex


EPS_SECONDARY = 1e-9


@dataclass
class BoundResult:
    ub_coverage: float
    ub_certified: bool
    secondary_lb: float | None
    ub_evaluation: SubsetEvaluation | None
    reason: str


def committed_capex(installed: set[str], capex: dict[str, float]) -> float:
    return subset_capex(installed, capex)


def budget_infeasible(installed: set[str], capex: dict[str, float], max_capex: float | None) -> bool:
    """True ⇒ prune: committed CAPEX already exceeds budget."""
    if max_capex is None:
        return False
    return committed_capex(installed, capex) > float(max_capex) + 1e-9


def coverage_upper_bound(
    *,
    installed: set[str],
    undecided: set[str],
    evaluate_fn: Callable[[set[str]], SubsetEvaluation],
) -> BoundResult:
    """
    Certified coverage UB over the budget-relaxed superset installed ∪ undecided.
    """
    relaxed = set(installed) | set(undecided)
    ev = evaluate_fn(relaxed)
    return BoundResult(
        ub_coverage=float(ev.coverage_serviceable),
        ub_certified=bool(ev.certified),
        secondary_lb=None,
        ub_evaluation=ev,
        reason="coverage_ub",
    )


def secondary_lower_bound(
    *,
    installed: set[str],
    capex: dict[str, float],
    crf: float,
    ub_evaluation: SubsetEvaluation,
) -> float:
    """
    Secondary LB when coverage UB ties the incumbent and UB eval is certified.

    Uses CAPEX(installed) (not the relaxed superset) plus variable cost from the
    UB evaluation's served non-structural missions.
    """
    infra_lb = annualized_infra_cost(installed, capex, crf)
    # variable_cost on SubsetEvaluation already weights served missions
    return float(infra_lb + ub_evaluation.variable_cost)


def can_prune_coverage(*, ub: BoundResult, incumbent_coverage: float | None) -> bool:
    if incumbent_coverage is None:
        return False
    if not ub.ub_certified:
        return False
    return ub.ub_coverage < float(incumbent_coverage) - 1e-12


def can_prune_secondary(
    *,
    ub: BoundResult,
    installed: set[str],
    capex: dict[str, float],
    crf: float,
    incumbent_coverage: float,
    incumbent_secondary: float,
    eps: float = EPS_SECONDARY,
) -> tuple[bool, float | None]:
    if not ub.ub_certified or ub.ub_evaluation is None:
        return False, None
    if abs(ub.ub_coverage - float(incumbent_coverage)) > 1e-12:
        return False, None
    lb = secondary_lower_bound(
        installed=installed,
        capex=capex,
        crf=crf,
        ub_evaluation=ub.ub_evaluation,
    )
    return lb > float(incumbent_secondary) + eps, lb


def bound_stats_dict(ub: BoundResult, secondary_lb: float | None = None) -> dict[str, Any]:
    return {
        "ub_coverage": ub.ub_coverage,
        "ub_certified": ub.ub_certified,
        "secondary_lb": secondary_lb,
        "reason": ub.reason,
    }
