#!/usr/bin/env python3
"""P1 primary comparison: 2 vehicles × 2 SOC scenarios × I0/I1/I2 × 14 missions.

Reuses Path A eActros stressed results only when explicitly requested AND the
mission-level statuses are copied as historical_reference (not silently mixed
with new solves). Default: solve all cells on the current implementation.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import run_stage_c_hos_national as stage_c  # noqa: E402
from run_final_operational_correction import (  # noqa: E402
    coverage_from_mission_rows,
    evaluate_mission_operational,
)
from run_paper_scientific_results_campaign import FRIDGE  # noqa: E402

OUT = ROOT / "results/final_evidence/experiments/primary_comparison"
MAN = ROOT / "results/final_evidence/manifests"

INFRA = [
    ("I0_none", set()),
    ("I1_benguerir_ca", {"y_benguerir_ca"}),
    ("I2_benguerir_larache", {"y_benguerir_ca", "y_larache_rt"}),
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


def _missions_with_soc(soc_scenario: str) -> list[dict]:
    raw = yaml.safe_load(stage_c.CFG_HEADLINE.read_text(encoding="utf-8"))
    missions = list(raw["demand_scenarios"]["corridor_eactros_equal"]["missions"])
    out = []
    for m in missions:
        m2 = dict(m)
        stressed = float(m["E_init_soc_frac"])
        m2["stressed_soc_frac"] = stressed
        if soc_scenario == "common_soc_80":
            m2["E_init_soc_frac"] = 0.8
        else:
            m2["E_init_soc_frac"] = stressed
        m2["soc_scenario"] = soc_scenario
        out.append(m2)
    return out


def _eval_panel(
    *,
    vehicle_key: str,
    installed: set[str],
    infra_id: str,
    soc_scenario: str,
    q: int,
    max_seconds: float,
    max_expansions: int,
) -> list[dict]:
    rows: list[dict] = []
    for mdef in _missions_with_soc(soc_scenario):
        od = str(mdef["od_id"])
        payload = float(mdef.get("cargo_payload_kg", 5300.0))
        soc = float(mdef["E_init_soc_frac"])
        cfg, vehicle, context, masks = stage_c._prepare_one(
            vehicle_key=vehicle_key, od_id=od, payload=payload, soc=soc, q=q
        )
        mid = context["missions"][0].id
        prep = context["prepared"][mid]
        all_mask = frozenset(masks[mid]["all"])
        mr = evaluate_mission_operational(
            prep=prep,
            cfg=cfg,
            installed=installed,
            mask=all_mask,
            vehicle=vehicle,
            fridge_path=FRIDGE,
            max_seconds=max_seconds,
            max_expansions=max_expansions,
            include_energy_only=True,
        )
        row = dict(mr)
        row.update(
            {
                "vehicle_key": vehicle_key,
                "soc_scenario": soc_scenario,
                "soc_frac": soc,
                "stressed_soc_frac": float(mdef["stressed_soc_frac"]),
                "payload_kg": payload,
                "q": q,
                "route_mode": "multi",
                "installed": ",".join(sorted(installed)),
                "infra_config_id": infra_id,
                "od_id": od,
                "n_all_arcs": len(all_mask),
                "max_seconds": max_seconds,
                "max_expansions": max_expansions,
                "git_sha": _git_sha(),
                "pipeline": "final_evidence_primary_comparison",
                "fridge": str(FRIDGE.relative_to(ROOT)).replace("\\", "/"),
            }
        )
        rows.append(row)
        print(
            f"  {vehicle_key}|{soc_scenario}|{infra_id}|{od}: "
            f"status={row.get('status')} ops={row.get('operationally_served')} "
            f"energy={row.get('energy_feasible')} duty={row.get('duty_scope')}",
            flush=True,
        )
    return rows


def _summarize(missions: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for (veh, soc_sc, infra), g in missions.groupby(
        ["vehicle_key", "soc_scenario", "infra_config_id"], sort=False
    ):
        n = len(g)
        rows.append(
            {
                "vehicle_key": veh,
                "soc_scenario": soc_sc,
                "infra_config_id": infra,
                "n_missions": n,
                "ops_served": int(g["operationally_served"].fillna(False).astype(bool).sum()),
                "ops_frac": float(g["operationally_served"].fillna(False).astype(bool).mean()),
                "energy_served": int(g["energy_feasible"].fillna(False).astype(bool).sum()),
                "n_optimal": int((g["status"] == "OPTIMAL").sum()),
                "n_infeasible": int((g["status"] == "INFEASIBLE").sum()),
                "n_limit_reached": int((g["status"] == "LIMIT_REACHED").sum()),
                "n_audit_failed": int(
                    (
                        (g["status"] == "OPTIMAL")
                        & (~g["operationally_served"].fillna(False).astype(bool))
                    ).sum()
                ),
                "installed": g["installed"].iloc[0] if len(g) else "",
            }
        )
    return pd.DataFrame(rows)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--vehicles",
        default="eactros_600,volvo_475",
        help="Comma-separated vehicle keys",
    )
    ap.add_argument(
        "--soc-scenarios",
        default="stressed_mixed,common_soc_80",
        help="Comma-separated: stressed_mixed,common_soc_80",
    )
    ap.add_argument("--infra", default="I0_none,I1_benguerir_ca,I2_benguerir_larache")
    ap.add_argument("--max-seconds", type=float, default=600.0)
    ap.add_argument("--max-expansions", type=int, default=2_000_000)
    ap.add_argument("--q", type=int, default=2)
    args = ap.parse_args()

    OUT.mkdir(parents=True, exist_ok=True)
    MAN.mkdir(parents=True, exist_ok=True)

    vehicles = [v.strip() for v in args.vehicles.split(",") if v.strip()]
    soc_scenarios = [s.strip() for s in args.soc_scenarios.split(",") if s.strip()]
    infra_wanted = {s.strip() for s in args.infra.split(",") if s.strip()}
    infra_cfgs = [(i, s) for i, s in INFRA if i in infra_wanted]

    fingerprint = {
        "git_sha": _git_sha(),
        "pipeline": "final_evidence_primary_comparison",
        "vehicles": vehicles,
        "soc_scenarios": soc_scenarios,
        "infra": [i for i, _ in infra_cfgs],
        "q": args.q,
        "max_seconds": args.max_seconds,
        "max_expansions": args.max_expansions,
        "fridge": str(FRIDGE.relative_to(ROOT)).replace("\\", "/"),
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "note": (
            "LIMIT_REACHED never equated to INFEASIBLE; "
            "stressed_mixed preserves 50% southbound Casa→Marrakech/Agadir + Marrakech→Agadir"
        ),
    }
    (OUT / "run_fingerprint.json").write_text(
        json.dumps(fingerprint, indent=2) + "\n", encoding="utf-8"
    )
    (MAN / "primary_comparison_fingerprint.json").write_text(
        json.dumps(fingerprint, indent=2) + "\n", encoding="utf-8"
    )

    missions_path = OUT / "primary_missions.csv"
    summary_path = OUT / "primary_summary.csv"
    all_rows: list[dict] = []
    if missions_path.exists():
        prev = pd.read_csv(missions_path)
        all_rows = prev.to_dict(orient="records")

    orig = stage_c._patch_realistic_speed_policy()
    try:
        for soc_scenario in soc_scenarios:
            for vehicle_key in vehicles:
                for infra_id, installed in infra_cfgs:
                    # Skip if already complete for this block
                    existing = [
                        r
                        for r in all_rows
                        if r.get("vehicle_key") == vehicle_key
                        and r.get("soc_scenario") == soc_scenario
                        and r.get("infra_config_id") == infra_id
                    ]
                    if len(existing) >= 14:
                        print(
                            f"[skip] {vehicle_key}|{soc_scenario}|{infra_id} already have {len(existing)} rows",
                            flush=True,
                        )
                        continue
                    # Drop partial block
                    all_rows = [
                        r
                        for r in all_rows
                        if not (
                            r.get("vehicle_key") == vehicle_key
                            and r.get("soc_scenario") == soc_scenario
                            and r.get("infra_config_id") == infra_id
                        )
                    ]
                    print(
                        f"[run] {vehicle_key}|{soc_scenario}|{infra_id} sites={sorted(installed) or ['(none)']}",
                        flush=True,
                    )
                    t0 = time.perf_counter()
                    rows = _eval_panel(
                        vehicle_key=vehicle_key,
                        installed=set(installed),
                        infra_id=infra_id,
                        soc_scenario=soc_scenario,
                        q=args.q,
                        max_seconds=args.max_seconds,
                        max_expansions=args.max_expansions,
                    )
                    elapsed = time.perf_counter() - t0
                    for r in rows:
                        r["block_elapsed_sec"] = round(elapsed, 1)
                    all_rows.extend(rows)
                    mdf = pd.DataFrame(all_rows)
                    mdf.to_csv(missions_path, index=False)
                    sdf = _summarize(mdf)
                    sdf.to_csv(summary_path, index=False)
                    cov = coverage_from_mission_rows(rows)
                    print(
                        f"  done in {elapsed:.1f}s ops={cov.get('n_operationally_served')}/14 "
                        f"limit={sum(1 for r in rows if r.get('status')=='LIMIT_REACHED')}",
                        flush=True,
                    )
    finally:
        import morocco_etruck.optimization.multiroute_placement_evaluation as mpe

        mpe.load_multiroute_pilot_config = orig

    mdf = pd.DataFrame(all_rows)
    mdf.to_csv(missions_path, index=False)
    _summarize(mdf).to_csv(summary_path, index=False)
    print("Wrote", missions_path)
    print("Wrote", summary_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
