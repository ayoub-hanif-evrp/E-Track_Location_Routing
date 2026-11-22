"""Validation helpers: shared coverage aggregator + nesting classification."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from run_final_operational_correction import coverage_from_mission_rows  # noqa: E402
from run_stage_c_hos_national import _classify_nesting_corner  # noqa: E402


def test_coverage_counts_ops_without_requiring_optimal():
    rows = [
        {"weight": 1.0, "status": "OPTIMAL", "operationally_served": True, "energy_feasible": True},
        {
            "weight": 1.0,
            "status": "LIMIT_REACHED",
            "operationally_served": False,
            "energy_feasible": True,
        },
        {
            "weight": 1.0,
            "status": "INFEASIBLE",
            "operationally_served": False,
            "energy_feasible": False,
        },
    ]
    cov = coverage_from_mission_rows(rows)
    assert cov["n_missions"] == 3
    assert cov["n_operationally_served"] == 1
    assert cov["n_limit_reached"] == 1
    assert cov["n_infeasible"] == 1
    assert abs(cov["operational_coverage"] - 1.0 / 3.0) < 1e-12
    # Resolved = 2 non-LIMIT; 1 served ⇒ 0.5
    assert abs(cov["certified_ops_among_resolved"] - 0.5) < 1e-12


def test_coverage_does_not_inflate_ops_from_limit():
    rows = [
        {
            "weight": 1.0,
            "status": "LIMIT_REACHED",
            "operationally_served": False,
            "energy_feasible": False,
        }
    ]
    cov = coverage_from_mission_rows(rows)
    assert cov["operational_coverage"] == 0.0
    assert cov["n_limit_reached"] == 1
    assert cov["certified_ops_among_resolved"] is None


@pytest.mark.parametrize(
    "of,om,sf,sm,expected",
    [
        (True, False, "OPTIMAL", "LIMIT_REACHED", "LIMIT_ARTIFACT"),
        (True, False, "OPTIMAL", "OPTIMAL", "AUDIT_NONNESTED"),
        (True, False, "OPTIMAL", "INFEASIBLE", "TRUE_MODEL_INFEAS"),
        (False, True, "INFEASIBLE", "OPTIMAL", "FLEX_GAIN"),
        (True, True, "OPTIMAL", "OPTIMAL", "BOTH_OPS"),
        (False, False, "LIMIT_REACHED", "INFEASIBLE", "LIMIT_CONTAMINATED"),
        (False, False, "INFEASIBLE", "INFEASIBLE", "BOTH_FAIL"),
    ],
)
def test_classify_nesting_corner(of, om, sf, sm, expected):
    assert (
        _classify_nesting_corner(
            ops_fixed=of, ops_multi=om, status_fixed=sf, status_multi=sm
        )
        == expected
    )
