#!/usr/bin/env python3
"""Canonical final-evidence workflow orchestrator (P0–P5 stages).

Runs stages selectively. Expensive solves are resumable via their own scripts.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


STAGES = {
    "p0_audit": [
        [sys.executable, "scripts/final_evidence/audit_dataset.py"],
        [sys.executable, "scripts/final_evidence/build_dt07_and_inventory.py"],
    ],
    "p1_primary": [
        [sys.executable, "scripts/final_evidence/run_primary_comparison.py"],
    ],
    "p1_settat": [
        [sys.executable, "scripts/final_evidence/run_settat_benguerir_compare.py"],
    ],
    "p1_diagnosis": [
        [sys.executable, "scripts/final_evidence/run_infeasible_diagnosis.py"],
    ],
    "figures_dataset": [
        [sys.executable, "scripts/final_evidence/plot_d_figure1_study_area.py"],
        [sys.executable, "scripts/final_evidence/plot_d_figure6_dataset_stats.py"],
    ],
    "figures_results": [
        [sys.executable, "scripts/final_evidence/plot_r_figure1_coverage.py"],
        [sys.executable, "scripts/final_evidence/plot_r_figure3_feasibility_matrix.py"],
    ],
}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--stages",
        default="p0_audit,figures_dataset",
        help="Comma-separated stages: " + ",".join(STAGES),
    )
    args = ap.parse_args()
    wanted = [s.strip() for s in args.stages.split(",") if s.strip()]
    for stage in wanted:
        if stage not in STAGES:
            print("Unknown stage", stage)
            return 2
        print(f"=== STAGE {stage} ===", flush=True)
        for cmd in STAGES[stage]:
            print("+", " ".join(cmd), flush=True)
            r = subprocess.run(cmd, cwd=ROOT)
            if r.returncode != 0:
                print("FAILED", stage, r.returncode)
                return r.returncode
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
