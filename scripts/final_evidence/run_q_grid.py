#!/usr/bin/env python3
"""Task 9 — Energy-grid resolution: q in {5,2,1} on selected missions."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import run_stage_c_hos_national as stage_c  # noqa: E402
from run_final_operational_correction import evaluate_mission_operational  # noqa: E402
from run_paper_scientific_results_campaign import FRIDGE  # noqa: E402

OUT = ROOT / "results/final_evidence/experiments/q_grid"

# Reproduce Agadir–Casablanca energy-grid result + near-boundary / feasible controls
CELLS = [
    # (od, soc, installed, note)
    ("agadir_casa", 0.8, set(), "headline_infeasible_control"),
    ("agadir_casa", 1.0, set(), "soc100_feasible_control"),
    ("casa_agadir", 0.5, {"y_benguerir_ca"}, "near_boundary_with_infra"),
    ("casa_rabat", 0.8, set(), "clearly_feasible"),
]


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT).decode().strip()
    orig = stage_c._patch_realistic_speed_policy()
    rows = []
    try:
        for od, soc, installed, note in CELLS:
            for q in (5, 2, 1):
                print(f"[qgrid] {od} q={q} soc={soc} sites={sorted(installed) or ['(none)']}", flush=True)
                cfg, vehicle, context, masks = stage_c._prepare_one(
                    vehicle_key="eactros_600", od_id=od, payload=5300.0, soc=soc, q=q
                )
                mid = context["missions"][0].id
                prep = context["prepared"][mid]
                mr = evaluate_mission_operational(
                    prep=prep,
                    cfg=cfg,
                    installed=set(installed),
                    mask=frozenset(masks[mid]["all"]),
                    vehicle=vehicle,
                    fridge_path=FRIDGE,
                    max_seconds=600.0,
                    max_expansions=2_000_000,
                    include_energy_only=True,
                )
                row = dict(mr)
                row.update(
                    {
                        "od_id": od,
                        "soc_frac": soc,
                        "q_kwh": q,
                        "installed": ",".join(sorted(installed)),
                        "note": note,
                        "vehicle_key": "eactros_600",
                        "git_sha": sha,
                        "pipeline": "final_evidence_q_grid",
                    }
                )
                rows.append(row)
                print(
                    f"  status={row.get('status')} ops={row.get('operationally_served')} "
                    f"energy={row.get('energy_feasible')} min_soc={row.get('min_soc')} "
                    f"sec={row.get('solve_sec')}",
                    flush=True,
                )
                pd.DataFrame(rows).to_csv(OUT / "q_grid_missions.csv", index=False)
    finally:
        import morocco_etruck.optimization.multiroute_placement_evaluation as mpe

        mpe.load_multiroute_pilot_config = orig

    df = pd.DataFrame(rows)
    df.to_csv(OUT / "q_grid_missions.csv", index=False)
    keep = [
        c
        for c in [
            "od_id",
            "soc_frac",
            "q_kwh",
            "installed",
            "status",
            "energy_feasible",
            "operationally_served",
            "min_soc",
            "solve_sec",
            "note",
        ]
        if c in df.columns
    ]
    df[keep].to_csv(
        ROOT / "results/final_evidence/tables/results/R-T11_energy_grid_resolution.csv",
        index=False,
    )
    print("Wrote", OUT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
