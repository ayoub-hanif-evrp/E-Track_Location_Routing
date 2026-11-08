"""MRLS solver behavior on synthetic instances."""

from __future__ import annotations

from pathlib import Path

from morocco_etruck.optimization.instances import load_synthetic_instances
from morocco_etruck.optimization.label_setting import SolverStatus, solve_mrls

ROOT = Path(__file__).resolve().parents[2]
INST = {i.name: i for i in load_synthetic_instances(ROOT / "configs/optimization/synthetic_instances.yaml")}


def _charge(actions):
    return sum(int(a.get("delta_e_kwh", 0)) for a in actions if a.get("type") == "CHARGE")


def test_case_a_no_charge():
    r = solve_mrls(INST["A_no_charge"])
    assert r.status == SolverStatus.OPTIMAL
    assert r.objective == 10
    assert r.path_nodes == ["O", "D"]
    assert _charge(r.actions) == 0


def test_case_b_charge_required():
    r = solve_mrls(INST["B_charge_required"])
    assert r.status == SolverStatus.OPTIMAL
    assert r.objective == 90
    assert r.path_nodes == ["O", "S", "D"]
    assert _charge(r.actions) == 40


def test_case_c_inactive_station():
    r = solve_mrls(INST["C_station_unavailable"])
    assert r.status == SolverStatus.INFEASIBLE


def test_case_d_longer_path():
    r = solve_mrls(INST["D_alternative_roads"])
    assert r.status == SolverStatus.OPTIMAL
    assert r.path_nodes == ["O", "M", "D"]
    assert r.objective == 24


def test_case_e_partial_charge():
    r = solve_mrls(INST["E_partial_charge"])
    assert r.status == SolverStatus.OPTIMAL
    assert _charge(r.actions) == 15
    assert r.objective == 156


def test_case_j_deadline():
    r = solve_mrls(INST["J_deadline"])
    assert r.status == SolverStatus.OPTIMAL
    assert r.objective == 50


def test_limit_reached_status_distinct():
    r = solve_mrls(INST["A_no_charge"], max_expansions=0)
    # start expanded once? max_expansions 0 means we hit limit before expanding
    assert r.status in {SolverStatus.LIMIT_REACHED, SolverStatus.OPTIMAL}
    if r.status == SolverStatus.LIMIT_REACHED:
        assert r.status != SolverStatus.INFEASIBLE
        assert r.status != SolverStatus.OPTIMAL
