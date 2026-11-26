#!/usr/bin/env python3
"""Reproduce historical Agadir→Casa 15 t / 80% SOC / Benguerir AC q-grid.

Separate scenario family from the 5.3 t q-grid experiments.
Matches Path A / Priority-5 protocol: multi + fixed, q in {5,2,1}.
"""
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

OUT = ROOT / "results/final_evidence/experiments/q_grid"
TAB = ROOT / "results/final_evidence/tables/results"
OD = "agadir_casa"
PAYLOAD = 15000.0
SOC = 0.8
SITE = {"y_benguerir_ac"}
QUANTA = (5, 2, 1)


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT).decode().strip()
    orig = stage_c._patch_realistic_speed_policy()
    rows = []
    try:
        for q in QUANTA:
            for mode in ("multi", "fixed"):
                print(f"[q15t] q={q} mode={mode} {OD} p={PAYLOAD} soc={SOC}", flush=True)
                cfg, vehicle, context, masks = stage_c._prepare_one(
                    vehicle_key="eactros_600",
                    od_id=OD,
                    payload=PAYLOAD,
                    soc=SOC,
                    q=q,
                )
                mid = context["missions"][0].id
                short = frozenset(masks[mid]["short"])
                all_mask = frozenset(masks[mid]["all"])
                mask = short if mode == "fixed" else all_mask
                mr = evaluate_mission_operational(
                    prep=context["prepared"][mid],
                    cfg=cfg,
                    installed=set(SITE),
                    mask=mask,
                    vehicle=vehicle,
                    fridge_path=stage_c.FRIDGE,
                    max_seconds=stage_c.UNIFORM_MAX_SECONDS,
                    max_expansions=int(cfg.solver_max_expansions),
                    include_energy_only=True,
                )
                row = dict(mr)
                row.update(
                    {
                        "vehicle_key": "eactros_600",
                        "od_id": OD,
                        "payload_kg": PAYLOAD,
                        "soc_frac": SOC,
                        "q_kwh": q,
                        "route_mode": mode,
                        "installed": ",".join(sorted(SITE)),
                        "max_seconds": stage_c.UNIFORM_MAX_SECONDS,
                        "max_expansions": int(cfg.solver_max_expansions),
                        "scenario_family": "historical_15t_benguerir_ac",
                        "note": "historical_15t_reproduction",
                        "git_sha": sha,
                        "pipeline": "final_evidence_q_grid_historical_15t",
                        "weather_id": "cool",
                        "refrigeration": str(stage_c.FRIDGE.relative_to(ROOT)).replace("\\", "/"),
                    }
                )
                rows.append(row)
                print(
                    f"  status={row.get('status')} ops={row.get('operationally_served')} "
                    f"min_soc={row.get('min_soc')} sec={row.get('solve_sec')}",
                    flush=True,
                )
                pd.DataFrame(rows).to_csv(OUT / "q_grid_historical_15t.csv", index=False)
    finally:
        import morocco_etruck.optimization.multiroute_placement_evaluation as mpe

        mpe.load_multiroute_pilot_config = orig

    hist = pd.DataFrame(rows)
    hist.to_csv(OUT / "q_grid_historical_15t.csv", index=False)

    # Rebuild authoritative R-T11 from 5.3t + historical 15t families
    parts = []
    light = OUT / "q_grid_missions.csv"
    ac = OUT / "q_grid_agadir_casa_benguerir_ac.csv"
    if light.exists():
        a = pd.read_csv(light)
        a["scenario_family"] = a.get("scenario_family", "headline_5p3t")
        if "scenario_family" not in a.columns or a["scenario_family"].isna().all():
            a["scenario_family"] = "headline_5p3t"
        if "payload_kg" not in a.columns:
            a["payload_kg"] = 5300.0
        if "route_mode" not in a.columns:
            a["route_mode"] = "multi"
        parts.append(a)
    if ac.exists():
        b = pd.read_csv(ac)
        if "scenario_family" not in b.columns:
            b["scenario_family"] = "headline_5p3t_benguerir_ac"
        if "payload_kg" not in b.columns:
            b["payload_kg"] = 5300.0
        if "route_mode" not in b.columns:
            b["route_mode"] = "multi"
        parts.append(b)
    parts.append(hist)
    allp = pd.concat(parts, ignore_index=True, sort=False)
    keep = [
        c
        for c in [
            "scenario_family",
            "od_id",
            "payload_kg",
            "soc_frac",
            "q_kwh",
            "installed",
            "route_mode",
            "status",
            "energy_feasible",
            "operationally_served",
            "min_soc",
            "solve_sec",
            "max_seconds",
            "max_expansions",
            "note",
            "pipeline",
            "git_sha",
        ]
        if c in allp.columns
    ]
    allp[keep].to_csv(TAB / "R-T11_energy_grid_resolution.csv", index=False)
    print(hist[["q_kwh", "route_mode", "status", "operationally_served", "min_soc", "solve_sec"]].to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
