"""Replay failure must not certify feasibility or justify B&B prunes (Task 05A)."""

from __future__ import annotations

from morocco_etruck.optimization.branch_and_bound import run_branch_and_bound_core
from morocco_etruck.optimization.placement_bounds import can_prune_coverage, coverage_upper_bound
from morocco_etruck.optimization.placement_cache import (
    PlacementMemo,
    build_mission_energy_fingerprint,
)
from morocco_etruck.optimization.placement_certification import OptimalityStatus
from morocco_etruck.optimization.placement_evaluation import SubsetEvaluation
from morocco_etruck.optimization.placement_problem import capital_recovery_factor


def _ev(sites, *, cov, var, capex_map, crf, certified=True):
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


def test_replay_failure_uncertified_blocks_coverage_prune():
    """Injected replay-invalid UB must not prune against a high incumbent."""
    crf = 0.1
    capex = {"A": 100.0}

    def evaluate_fn(installed: set[str]) -> SubsetEvaluation:
        # Simulate OPTIMAL discrete but continuous replay fail → uncertified, cov undercount
        return _ev(installed, cov=0.0, var=0.0, capex_map=capex, crf=crf, certified=False)

    ub = coverage_upper_bound(installed=set(), undecided={"A"}, evaluate_fn=evaluate_fn)
    assert not ub.ub_certified
    assert not can_prune_coverage(ub=ub, incumbent_coverage=5.0)


def test_replay_failure_leaf_prevents_certified_optimal():
    crf = capital_recovery_factor(0.08, 15)
    capex = {"A": 50.0}

    def evaluate_fn(installed: set[str]) -> SubsetEvaluation:
        if not installed:
            return _ev(set(), cov=0.0, var=0.0, capex_map=capex, crf=crf, certified=True)
        # Leaf {A}: looks like coverage 1 but uncertified (replay failure injection)
        return _ev(installed, cov=1.0, var=1.0, capex_map=capex, crf=crf, certified=False)

    res = run_branch_and_bound_core(
        site_ids=["A"],
        capex=capex,
        max_capex=None,
        crf=crf,
        evaluate_fn=evaluate_fn,
    )
    # Uncertified leaf ⇒ cannot claim CERTIFIED_OPTIMAL; no certified incumbent accepted
    assert res.optimality_status != OptimalityStatus.CERTIFIED_OPTIMAL
    assert res.optimality_status in {
        OptimalityStatus.INCUMBENT_UNPROVED,
        OptimalityStatus.NO_FEASIBLE,
    }


def test_memo_fingerprint_changes_with_weather_or_gcm():
    base = dict(
        version="04b.1",
        q=5,
        time_step_min=5,
        gcm="light",
        terrain_mode="dem",
        weather_id="cool",
        refrigeration="off",
        power_source="A",
        direction="casablanca_to_agadir",
        terrain_hash="abc",
    )
    fp1 = build_mission_energy_fingerprint(**base)
    fp2 = build_mission_energy_fingerprint(**{**base, "weather_id": "hot"})
    fp3 = build_mission_energy_fingerprint(**{**base, "gcm": "heavy"})
    assert fp1 != fp2
    assert fp1 != fp3

    memo = PlacementMemo(energy_model_fingerprint=fp1)
    key1 = memo.make_key(
        mission_id="M1",
        active_station_keys=frozenset({"settat"}),
        price_mode="uniform",
        q=5,
        time_step_min=5,
    )
    from morocco_etruck.optimization.placement_cache import CachedMissionResult

    memo.put(
        key1,
        CachedMissionResult(
            status="OPTIMAL",
            served=True,
            uncertified=False,
            objective_cents=10,
            charge_kwh=0,
            charges="",
            path="O->D",
            continuous_replay_ok=True,
            discrete_replay_ok=True,
        ),
    )
    memo2 = PlacementMemo(energy_model_fingerprint=fp2)
    key2 = memo2.make_key(
        mission_id="M1",
        active_station_keys=frozenset({"settat"}),
        price_mode="uniform",
        q=5,
        time_step_min=5,
    )
    # Different fingerprint ⇒ different key ⇒ miss
    assert memo2.get(key2) is None
    assert key1 != key2
