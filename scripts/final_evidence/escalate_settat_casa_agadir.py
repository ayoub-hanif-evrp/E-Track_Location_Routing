#!/usr/bin/env python3
"""Escalate Settat CA casa_agadir LIMIT under final-evidence protocol (multi)."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import run_stage_c_hos_national as stage_c  # noqa: E402

OUT = ROOT / "results/final_evidence/experiments/settat_vs_benguerir"
MAX_EXP = 5_000_000
MAX_SEC = 1200.0


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT).decode().strip()
    orig = stage_c._patch_realistic_speed_policy()
    rows = []
    try:
        print(f"[escalate] settat casa_agadir multi {MAX_SEC}s/{MAX_EXP}", flush=True)
        ev = stage_c._eval_installed_on_panel(
            vehicle_key="eactros_600",
            installed={"y_settat_ca"},
            route_mode="multi",
            method_id="escalate_settat_casa_agadir_multi",
            budget="settat",
            q=2,
            max_seconds=MAX_SEC,
            max_expansions=MAX_EXP,
            od_filter={"casa_agadir"},
            include_energy_only=True,
        )
        for mr in ev["mission_rows"]:
            row = dict(mr)
            row["git_sha"] = sha
            row["pipeline"] = "final_evidence_settat_escalate"
            rows.append(row)
            print(
                f"  status={row.get('status')} ops={row.get('operationally_served')} "
                f"charge={row.get('charge_min_phys')} wait={row.get('wait_min_phys')} "
                f"min_soc={row.get('min_soc')}",
                flush=True,
            )
    finally:
        import morocco_etruck.optimization.multiroute_placement_evaluation as mpe

        mpe.load_multiroute_pilot_config = orig

    pd.DataFrame(rows).to_csv(OUT / "settat_casa_agadir_escalate.csv", index=False)
    # Also copy historical Path A escalate as reference
    hist = ROOT / "results/validation/path_a/limit_escalate/settat_casa_agadir_escalate.csv"
    if hist.exists():
        hdf = pd.read_csv(hist)
        hdf["source"] = "path_a_historical_reference"
        hdf.to_csv(OUT / "settat_casa_agadir_escalate_path_a_reference.csv", index=False)
    print("Wrote", OUT / "settat_casa_agadir_escalate.csv")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
