#!/usr/bin/env python3
"""Addendum: Agadir→Casa with Benguerir AC across q∈{5,2,1}."""
from __future__ import annotations

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
TAB = ROOT / "results/final_evidence/tables/results/R-T11_energy_grid_resolution.csv"


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    orig = stage_c._patch_realistic_speed_policy()
    rows = []
    try:
        for q in (5, 2, 1):
            print(f"[qgrid+] agadir_casa +benguerir_ac q={q}", flush=True)
            cfg, vehicle, context, masks = stage_c._prepare_one(
                vehicle_key="eactros_600", od_id="agadir_casa", payload=5300.0, soc=0.8, q=q
            )
            mid = context["missions"][0].id
            mr = evaluate_mission_operational(
                prep=context["prepared"][mid],
                cfg=cfg,
                installed={"y_benguerir_ac"},
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
                    "od_id": "agadir_casa",
                    "soc_frac": 0.8,
                    "q_kwh": q,
                    "installed": "y_benguerir_ac",
                    "note": "directional_ac_near_boundary",
                    "vehicle_key": "eactros_600",
                    "pipeline": "final_evidence_q_grid_ac",
                }
            )
            rows.append(row)
            print(
                f"  status={row.get('status')} ops={row.get('operationally_served')} "
                f"energy={row.get('energy_feasible')} min_soc={row.get('min_soc')} "
                f"sec={row.get('solve_sec')}",
                flush=True,
            )
    finally:
        import morocco_etruck.optimization.multiroute_placement_evaluation as mpe

        mpe.load_multiroute_pilot_config = orig

    extra = pd.DataFrame(
        [
            {
                k: r.get(k)
                for k in [
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
            }
            for r in rows
        ]
    )
    base = pd.read_csv(TAB) if TAB.exists() else pd.DataFrame()
    pd.concat([base, extra], ignore_index=True).to_csv(TAB, index=False)
    pd.DataFrame(rows).to_csv(OUT / "q_grid_agadir_casa_benguerir_ac.csv", index=False)
    print(extra.to_string())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
