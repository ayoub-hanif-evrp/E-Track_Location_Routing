#!/usr/bin/env python3
"""Task 7.2 — Diagnose marrakech_agadir and agadir_casa infeasibility.

Evaluates targeted existing candidate configs and operating changes.
Does not invent new infrastructure sites.
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import run_stage_c_hos_national as stage_c  # noqa: E402
from run_final_operational_correction import evaluate_mission_operational  # noqa: E402
from run_paper_scientific_results_campaign import FRIDGE  # noqa: E402

OUT = ROOT / "results/final_evidence/experiments/infeasible_diagnosis"

# Focus ODs remaining infeasible under I2 stressed eActros
FOCUS_ODS = ("marrakech_agadir", "agadir_casa")

# Targeted remedies using EXISTING directional candidates / SOC / payload only
REMEDIES = [
    ("baseline_I2", {"y_benguerir_ca", "y_larache_rt"}, None, None),
    ("amskroud_ca_only", {"y_amskroud_ca"}, None, None),
    ("amskroud_plus_benguerir_ca", {"y_amskroud_ca", "y_benguerir_ca"}, None, None),
    ("benguerir_ac_only", {"y_benguerir_ac"}, None, None),
    ("settat_ac_only", {"y_settat_ac"}, None, None),
    ("benguerir_ac_settat_ac", {"y_benguerir_ac", "y_settat_ac"}, None, None),
    ("I2_plus_amskroud", {"y_benguerir_ca", "y_larache_rt", "y_amskroud_ca"}, None, None),
    ("I2_soc90", {"y_benguerir_ca", "y_larache_rt"}, 0.9, None),
    ("I2_soc100", {"y_benguerir_ca", "y_larache_rt"}, 1.0, None),
    ("none_soc100", set(), 1.0, None),
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
    OUT.mkdir(parents=True, exist_ok=True)
    fp = {
        "git_sha": _git_sha(),
        "pipeline": "final_evidence_infeasible_diagnosis",
        "focus_ods": list(FOCUS_ODS),
        "q": 2,
        "max_seconds": 600.0,
        "max_expansions": 2_000_000,
        "note": "Existing candidates / SOC only; no new sites",
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    (OUT / "run_fingerprint.json").write_text(json.dumps(fp, indent=2) + "\n", encoding="utf-8")

    orig = stage_c._patch_realistic_speed_policy()
    rows = []
    try:
        for od in FOCUS_ODS:
            # default stressed SOC from headline yaml via prepare_one defaults
            for name, installed, soc_override, payload_override in REMEDIES:
                # Determine baseline soc from corridor missions
                mdef = next(m for m in stage_c._corridor_missions() if m["od_id"] == od)
                payload = float(payload_override or mdef.get("cargo_payload_kg", 5300.0))
                soc = float(soc_override if soc_override is not None else mdef.get("E_init_soc_frac", 0.8))
                print(f"[diag] {od}|{name} sites={sorted(installed) or ['(none)']} soc={soc}", flush=True)
                cfg, vehicle, context, masks = stage_c._prepare_one(
                    vehicle_key="eactros_600", od_id=od, payload=payload, soc=soc, q=2
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
                        "remedy_id": name,
                        "od_id": od,
                        "installed": ",".join(sorted(installed)),
                        "soc_frac": soc,
                        "payload_kg": payload,
                        "vehicle_key": "eactros_600",
                        "pipeline": fp["pipeline"],
                        "git_sha": fp["git_sha"],
                    }
                )
                rows.append(row)
                print(
                    f"  status={row.get('status')} ops={row.get('operationally_served')} "
                    f"energy={row.get('energy_feasible')}",
                    flush=True,
                )
                import pandas as pd

                pd.DataFrame(rows).to_csv(OUT / "infeasible_remedy_missions.csv", index=False)
    finally:
        import morocco_etruck.optimization.multiroute_placement_evaluation as mpe

        mpe.load_multiroute_pilot_config = orig

    import pandas as pd

    df = pd.DataFrame(rows)
    df.to_csv(OUT / "infeasible_remedy_missions.csv", index=False)
    # Compact ledger
    keep = [
        c
        for c in [
            "od_id",
            "remedy_id",
            "installed",
            "soc_frac",
            "status",
            "energy_feasible",
            "operationally_served",
            "min_soc",
            "arrival_soc",
            "charge_min_phys",
            "wait_min_phys",
            "road_km",
        ]
        if c in df.columns
    ]
    df[keep].to_csv(
        ROOT / "results/final_evidence/tables/results/R-T12_infeasible_diagnosis.csv",
        index=False,
    )
    print("Wrote", OUT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
