#!/usr/bin/env python3
"""Canonical freeze-correction workflow (P0–P6).

Order matters: regenerate science artifacts first; executable_validation LAST
(so the SHA-256 manifest hashes final bytes and excludes itself).
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = [
    "scripts/final_evidence/postprocess_unevaluated_hos_fields.py",
    "scripts/final_evidence/diagnose_volvo_marrakech_agadir.py",
    "scripts/final_evidence/build_primary_i0_i3_panel.py",
    "scripts/final_evidence/run_volvo_settat_vs_benguerir_panel.py",
    "scripts/final_evidence/rebuild_dem_vs_flat_tables.py",
    "scripts/final_evidence/plot_casa_marrakech_terrain_triptych.py",
    "scripts/final_evidence/regen_elevation_artifacts.py",
    "scripts/final_evidence/investigate_elevation_continuity.py",
    "scripts/final_evidence/plot_r_figure1_coverage.py",
    "scripts/final_evidence/plot_r_figure2_executed_routes.py",
    "scripts/final_evidence/plot_r_figure3_feasibility_matrix.py",
    "scripts/final_evidence/plot_r_figure5_multipanel.py",
    # R-Figure 9 via generate_remaining helper is invoked separately if needed
    "scripts/final_evidence/executable_validation.py",
]


def main() -> int:
    for rel in SCRIPTS:
        print(f"=== {rel} ===", flush=True)
        rc = subprocess.call([sys.executable, str(ROOT / rel)], cwd=ROOT)
        if rc != 0:
            print(f"FAILED {rel} rc={rc}", flush=True)
            return rc
    print("WORKFLOW_DONE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
