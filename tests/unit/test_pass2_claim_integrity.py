"""PASS 2 — claim/status integrity guards."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]


def _load_diag_module():
    path = ROOT / "scripts/run_final_heavy_vehicle_diagnosis.py"
    spec = importlib.util.spec_from_file_location("heavy_diag", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_publishable_claim_matches_served_diagnosis():
    mod = _load_diag_module()
    assert mod._publishable_claim("served").startswith("served_")
    assert "infeasible" not in mod._publishable_claim("served")
    assert "discrete_grid_reject" in mod._publishable_claim("discrete_grid_reject")
    assert "peak_motor" in mod._publishable_claim("peak_motor")


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
