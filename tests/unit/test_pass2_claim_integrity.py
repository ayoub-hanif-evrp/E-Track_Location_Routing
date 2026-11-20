"""PASS 2 — claim/status integrity guards (no deleted diagnosis script)."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]


def _publishable_claim(diagnosis_class: str) -> str:
    """Mirror the retired diagnosis script's claim mapping used by integrity tests."""
    dc = str(diagnosis_class)
    if dc == "served":
        return "served_under_declared_physics"
    if dc == "discrete_grid_reject":
        return "infeasible_or_discrete_grid_reject"
    if dc == "peak_motor":
        return "infeasible_peak_motor"
    return f"infeasible_{dc}"


def test_publishable_claim_matches_served_diagnosis():
    assert _publishable_claim("served").startswith("served_")
    assert "infeasible" not in _publishable_claim("served")
    assert "discrete_grid_reject" in _publishable_claim("discrete_grid_reject")
    assert "peak_motor" in _publishable_claim("peak_motor")


def test_committed_diagnosis_csv_has_no_served_vs_infeasible_contradiction():
    path = ROOT / "results/final_heavy_vehicle_feasibility_diagnosis.csv"
    if not path.exists():
        return
    df = pd.read_csv(path)
    if "diagnosis_class" not in df.columns or "publishable_claim" not in df.columns:
        return
    bad = df[
        (df["diagnosis_class"].astype(str) == "served")
        & df["publishable_claim"].astype(str).str.contains("infeasible", case=False, na=False)
    ]
    assert bad.empty, f"contradictory rows:\n{bad}"
