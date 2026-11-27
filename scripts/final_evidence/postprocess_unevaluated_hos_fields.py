#!/usr/bin/env python3
"""Replace unevaluated HOS defaults (False with no ops trace) by null / NOT_EVALUATED."""
from __future__ import annotations

from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
FE = ROOT / "results/final_evidence"

TARGETS = [
    FE / "experiments/primary_comparison/primary_missions.csv",
    FE / "experiments/i3_three_site/i3_missions.csv",
    FE / "experiments/volvo_targeted_infra/volvo_targeted_infra_missions.csv",
    FE / "experiments/dem_vs_flat/dem_vs_flat_missions.csv",
    FE / "tables/results/R-T03_mission_level_operational_results.csv",
]


def _fix_frame(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    if "status" not in out.columns:
        return out
    no_trace = out["status"].astype(str) != "OPTIMAL"
    if "n_trace_actions" in out.columns:
        no_trace = no_trace | (out["n_trace_actions"].fillna(0).astype(int) <= 0)
    if "drive_min_phys" in out.columns:
        no_trace = no_trace | out["drive_min_phys"].isna()
    for col in ("hos_ok", "daily_driving_ok"):
        if col in out.columns:
            # Cast away strict bool dtype so nulls are representable.
            out[col] = out[col].astype(object)
            mask = no_trace & out[col].isin([False, 0, "False", "false"])
            out.loc[mask, col] = None
    if "duty_scope" in out.columns:
        out.loc[no_trace, "duty_scope"] = "NOT_EVALUATED"
    return out


def main() -> int:
    for path in TARGETS:
        if not path.exists():
            print("skip missing", path)
            continue
        df = pd.read_csv(path)
        fixed = _fix_frame(df)
        fixed.to_csv(path, index=False)
        n = int((fixed.get("duty_scope") == "NOT_EVALUATED").sum()) if "duty_scope" in fixed.columns else 0
        print(f"updated {path.relative_to(ROOT)} not_evaluated_rows={n}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
