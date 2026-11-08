"""MRLS vs independent exhaustive reference on all synthetic cases."""

from __future__ import annotations

from pathlib import Path

import pytest

from morocco_etruck.optimization.instances import load_synthetic_instances
from morocco_etruck.optimization.label_setting import SolverStatus, solve_mrls
from morocco_etruck.optimization.reference_solver import solve_reference

ROOT = Path(__file__).resolve().parents[2]
INSTANCES = load_synthetic_instances(ROOT / "configs/optimization/synthetic_instances.yaml")


@pytest.mark.parametrize("inst", INSTANCES, ids=[i.name for i in INSTANCES])
def test_mrls_matches_reference(inst):
    mrls = solve_mrls(inst, use_dominance=True)
    ref = solve_reference(inst)
    assert mrls.status == ref.status
    assert mrls.objective == ref.objective
    if mrls.status == SolverStatus.OPTIMAL:
        assert mrls.path_nodes == ref.path_nodes
        # Charge totals should match for these instances
        def ch(actions):
            return sum(int(a.get("delta_e_kwh", 0)) for a in actions if a.get("type") == "CHARGE")

        assert ch(mrls.actions) == ch(ref.actions)


def test_dominance_on_off_same_optimum():
    inst = next(i for i in INSTANCES if i.name == "I_dominance")
    on = solve_mrls(inst, use_dominance=True)
    off = solve_mrls(inst, use_dominance=False)
    assert on.status == off.status == SolverStatus.OPTIMAL
    assert on.objective == off.objective


@pytest.mark.parametrize("inst", INSTANCES, ids=[i.name for i in INSTANCES])
def test_matches_yaml_expected(inst):
    mrls = solve_mrls(inst, use_dominance=True)
    exp = inst.expected
    if not exp:
        return
    assert mrls.status.value == exp["status"]
    if "objective" in exp:
        assert mrls.objective == exp["objective"]
    if "path" in exp:
        assert mrls.path_nodes == list(exp["path"])
    if "charge_total_kwh" in exp:
        ch = sum(int(a.get("delta_e_kwh", 0)) for a in mrls.actions if a.get("type") == "CHARGE")
        assert ch == int(exp["charge_total_kwh"])
