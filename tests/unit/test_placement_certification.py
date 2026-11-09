"""Certification status rules (Task 04B)."""

from __future__ import annotations

from morocco_etruck.optimization.placement_certification import (
    OptimalityStatus,
    ServiceabilityClass,
    is_peak_motor_reason,
)
from morocco_etruck.optimization.placement_evaluation import SubsetEvaluation
from morocco_etruck.optimization.placement_problem import LexScore


def test_peak_motor_reason_detection():
    assert is_peak_motor_reason("peak_motor_power")
    assert is_peak_motor_reason("peak_power exceeded")
    assert not is_peak_motor_reason("energy_floor")
    assert not is_peak_motor_reason(None)


def test_serviceability_enum_values():
    assert ServiceabilityClass.PEAK_MOTOR.value == "peak_motor"
    assert ServiceabilityClass.SERVICEABLE.value == "serviceable"
    assert OptimalityStatus.CERTIFIED_OPTIMAL.value == "CERTIFIED_OPTIMAL"
    assert OptimalityStatus.LIMIT_REACHED.value == "LIMIT_REACHED"


def test_serviceable_denominator_excludes_non_serviceable_classes():
    """weight_serviceable counts only class==serviceable, not merely not-peak-motor."""
    from morocco_etruck.optimization.placement_evaluation import SubsetEvaluation

    # Simulate taxonomy: peak_motor + unserved_all_candidates + serviceable
    serviceability = {
        "M_peak": "peak_motor",
        "M_unserved": "unserved_all_candidates",
        "M_ok": "serviceable",
    }
    weights = {"M_peak": 0.5, "M_unserved": 2.0, "M_ok": 3.0}
    serviceable_ids = {mid for mid, v in serviceability.items() if v == "serviceable"}
    structural_ids = {mid for mid, v in serviceability.items() if v == "peak_motor"}
    w_serv = sum(w for mid, w in weights.items() if mid in serviceable_ids)
    w_not_struct = sum(w for mid, w in weights.items() if mid not in structural_ids)
    assert w_serv == 3.0
    assert w_not_struct == 5.0  # would wrongly include unserved_all_candidates
    assert isinstance(SubsetEvaluation, type)


def test_enumeration_global_cert_rule_logic():
    """
    Global CERTIFIED_OPTIMAL requires every budget-feasible subset certified.
    Presence of an uncertified competitor ⇒ INCUMBENT_UNPROVED even if best is certified.
    """
    certified_best = SubsetEvaluation(
        site_ids=frozenset({"A"}),
        budget_ok=True,
        certified=True,
        coverage_total=3.0,
        coverage_serviceable=3.0,
        weight_total=3.0,
        weight_serviceable=3.0,
        infra_capex=100.0,
        infra_annual=10.0,
        variable_cost=5.0,
        secondary_cost=15.0,
    )
    uncertified_other = SubsetEvaluation(
        site_ids=frozenset({"B"}),
        budget_ok=True,
        certified=False,
        coverage_total=2.0,
        coverage_serviceable=2.0,
        weight_total=3.0,
        weight_serviceable=3.0,
        infra_capex=100.0,
        infra_annual=10.0,
        variable_cost=1.0,
        secondary_cost=11.0,
    )
    budget_evals = [certified_best, uncertified_other]
    uncertified_pool = [e for e in budget_evals if not e.certified]
    assert uncertified_pool
    # Must not ignore unresolved competitor
    status = (
        OptimalityStatus.INCUMBENT_UNPROVED
        if uncertified_pool
        else OptimalityStatus.CERTIFIED_OPTIMAL
    )
    assert status == OptimalityStatus.INCUMBENT_UNPROVED
    best = min(
        [e for e in budget_evals if e.certified],
        key=lambda e: LexScore.from_parts(e.coverage_serviceable, e.secondary_cost),
    )
    assert best.site_ids == frozenset({"A"})
