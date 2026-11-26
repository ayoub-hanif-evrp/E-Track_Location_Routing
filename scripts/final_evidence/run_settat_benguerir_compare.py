#!/usr/bin/env python3
"""Task 7.1 — Settat CA vs Benguerir CA under identical protocol.

Singleton ledger on the 14-mission stressed panel (eActros) plus focused
Casa→Agadir operational decomposition.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import run_stage_c_hos_national as stage_c  # noqa: E402

OUT = ROOT / "results/final_evidence/experiments/settat_vs_benguerir"

CONFIGS = [
    ("S0_none", set()),
    ("S1_settat_ca", {"y_settat_ca"}),
    ("S1_benguerir_ca", {"y_benguerir_ca"}),
]


def _git_sha() -> str:
    try:
        return (
            subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT)
            .decode()
            .strip()
        )
    except Exception:  # noqa: BLE001
        return "unknown"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-seconds", type=float, default=600.0)
    ap.add_argument("--max-expansions", type=int, default=2_000_000)
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)

    fingerprint = {
        "git_sha": _git_sha(),
        "pipeline": "final_evidence_settat_vs_benguerir",
        "vehicle_key": "eactros_600",
        "soc_scenario": "stressed_mixed",
        "q": 2,
        "max_seconds": args.max_seconds,
        "max_expansions": args.max_expansions,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    (OUT / "run_fingerprint.json").write_text(
        json.dumps(fingerprint, indent=2) + "\n", encoding="utf-8"
    )

    orig = stage_c._patch_realistic_speed_policy()
    all_m: list[dict] = []
    summary: list[dict] = []
    try:
        for cfg_id, installed in CONFIGS:
            print(f"[settat] {cfg_id}", flush=True)
            t0 = time.perf_counter()
            ev = stage_c._eval_installed_on_panel(
                vehicle_key="eactros_600",
                installed=set(installed),
                route_mode="multi",
                method_id=f"settat_{cfg_id}",
                budget="settat",
                q=2,
                max_seconds=args.max_seconds,
                max_expansions=args.max_expansions,
                include_energy_only=True,
            )
            elapsed = time.perf_counter() - t0
            for mr in ev["mission_rows"]:
                row = dict(mr)
                row["infra_config_id"] = cfg_id
                row["git_sha"] = fingerprint["git_sha"]
                row["pipeline"] = fingerprint["pipeline"]
                all_m.append(row)
            summary.append(
                {
                    "infra_config_id": cfg_id,
                    "sites": ",".join(sorted(installed)),
                    "ops_served": int(ev["n_operationally_served"]),
                    "ops_frac": float(ev["operational_coverage"]),
                    "n_missions": int(ev["n_missions"]),
                    "n_optimal": int(ev.get("n_optimal") or 0),
                    "n_infeasible": int(ev.get("n_infeasible") or 0),
                    "n_limit_reached": int(ev.get("n_limit_reached") or 0),
                    "elapsed_sec": round(elapsed, 1),
                }
            )
            pd.DataFrame(all_m).to_csv(OUT / "singleton_missions.csv", index=False)
            pd.DataFrame(summary).to_csv(OUT / "singleton_ledger.csv", index=False)
            print(
                f"  ops={summary[-1]['ops_served']}/14 LIMIT={summary[-1]['n_limit_reached']}",
                flush=True,
            )
    finally:
        import morocco_etruck.optimization.multiroute_placement_evaluation as mpe

        mpe.load_multiroute_pilot_config = orig

    mdf = pd.DataFrame(all_m)
    # Casa-Agadir focused comparison
    focus = mdf[mdf["od_id"] == "casa_agadir"][
        [
            c
            for c in [
                "infra_config_id",
                "od_id",
                "status",
                "operationally_served",
                "energy_feasible",
                "objective",
                "min_soc",
                "arrival_soc",
                "road_km",
                "drive_min_phys",
                "charge_min_phys",
                "wait_min_phys",
                "pad_duration_min",
                "solve_sec",
            ]
            if c in mdf.columns
        ]
    ].copy()
    if {"drive_min_phys", "charge_min_phys", "wait_min_phys"}.issubset(focus.columns):
        journey = (
            focus["drive_min_phys"].fillna(0)
            + focus["charge_min_phys"].fillna(0)
            + focus["wait_min_phys"].fillna(0)
        )
        if "pad_duration_min" in focus.columns:
            journey = journey + focus["pad_duration_min"].fillna(0)
        focus["journey_min_phys"] = journey
    focus.to_csv(OUT / "casa_agadir_settat_vs_benguerir.csv", index=False)

    notes = [
        "# Settat CA vs Benguerir CA",
        "",
        "Identical eActros stressed panel, multi-route, q=2, 600s/2e6.",
        "",
        "| Config | Ops | LIMIT |",
        "|--------|-----|-------|",
    ]
    for s in summary:
        notes.append(
            f"| {s['infra_config_id']} | {s['ops_served']}/14 | {s['n_limit_reached']} |"
        )
    notes.extend(
        [
            "",
            "If coverage equal, report the tie. Stationary durations previously recorded",
            "as 120 min (Settat) vs 65 min (Benguerir) must be verified from",
            "`casa_agadir_settat_vs_benguerir.csv` charge+wait columns under this protocol.",
            "",
            "Do not attribute differences to HOS without a controlled experiment.",
            "",
        ]
    )
    (OUT / "settat_benguerir_notes.md").write_text("\n".join(notes), encoding="utf-8")
    print("Wrote", OUT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
