#!/usr/bin/env python3
"""P4.3 — Targeted Volvo infrastructure alternatives for failed stressed missions.

Small topology/energy-justified set — not unrestricted enumeration.
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

OUT = ROOT / "results/final_evidence/experiments/volvo_targeted_infra"

# Failed stressed Volvo ODs under eActros-selected Benguerir CA
FAILED_ODS = [
    "casa_agadir",
    "agadir_casa",
    "casa_marrakech",
    "marrakech_agadir",
    "casa_tangier",
    "tangier_casa",
    "rabat_tangier",
]

# Topology-justified alternatives (directional / corridor-relevant)
CONFIGS = [
    ("V0_none", set()),
    ("V_benguerir_ca", {"y_benguerir_ca"}),  # eActros-selected (known no gain)
    ("V_benguerir_ac", {"y_benguerir_ac"}),  # northbound / reverse-direction
    ("V_settat_ca", {"y_settat_ca"}),
    ("V_larache_rt", {"y_larache_rt"}),
    ("V_amskroud_ca", {"y_amskroud_ca"}),
    ("V_benguerir_ac_larache", {"y_benguerir_ac", "y_larache_rt"}),
    ("V_settat_larache", {"y_settat_ca", "y_larache_rt"}),
]


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT).decode().strip()
    missions = {m["od_id"]: m for m in stage_c._corridor_missions()}
    orig = stage_c._patch_realistic_speed_policy()
    rows = []
    try:
        for od in FAILED_ODS:
            mdef = missions[od]
            payload = float(mdef.get("cargo_payload_kg", 5300.0))
            soc = float(mdef.get("E_init_soc_frac", 0.5))  # stressed
            cfg, vehicle, context, masks = stage_c._prepare_one(
                vehicle_key="volvo_475", od_id=od, payload=payload, soc=soc, q=2
            )
            mid = context["missions"][0].id
            for cfg_id, installed in CONFIGS:
                print(f"[volvo-infra] {od} {cfg_id}", flush=True)
                mr = evaluate_mission_operational(
                    prep=context["prepared"][mid],
                    cfg=cfg,
                    installed=set(installed),
                    mask=frozenset(masks[mid]["all"]),
                    vehicle=vehicle,
                    fridge_path=stage_c.FRIDGE,
                    max_seconds=600.0,
                    max_expansions=2_000_000,
                    include_energy_only=True,
                )
                row = dict(mr)
                row.update(
                    {
                        "od_id": od,
                        "payload_kg": payload,
                        "soc_frac": soc,
                        "soc_scenario": "stressed_mixed",
                        "infra_config_id": cfg_id,
                        "installed": ",".join(sorted(installed)),
                        "vehicle_key": "volvo_475",
                        "git_sha": sha,
                        "pipeline": "final_evidence_volvo_targeted_infra",
                        "justification": "topology_or_direction_for_failed_volvo_od",
                    }
                )
                rows.append(row)
                print(
                    f"  status={row.get('status')} ops={row.get('operationally_served')} "
                    f"energy={row.get('energy_status')}",
                    flush=True,
                )
                pd.DataFrame(rows).to_csv(OUT / "volvo_targeted_infra_missions.csv", index=False)
    finally:
        import morocco_etruck.optimization.multiroute_placement_evaluation as mpe

        mpe.load_multiroute_pilot_config = orig

    df = pd.DataFrame(rows)
    df.to_csv(OUT / "volvo_targeted_infra_missions.csv", index=False)
    piv = (
        df.pivot_table(
            index="od_id",
            columns="infra_config_id",
            values="operationally_served",
            aggfunc="max",
        )
        .fillna(False)
        .astype(bool)
    )
    piv.to_csv(OUT / "volvo_targeted_infra_ops_matrix.csv")
    piv.to_csv(
        ROOT / "results/final_evidence/tables/results/R-T02_volvo_targeted_infra_matrix.csv"
    )
    # Coverage vs Benguerir CA baseline
    base = df[df.infra_config_id == "V_benguerir_ca"].operationally_served.sum()
    summary = (
        df.groupby("infra_config_id")
        .agg(ops=("operationally_served", "sum"), n=("od_id", "count"))
        .reset_index()
        .sort_values("ops", ascending=False)
    )
    summary["delta_vs_benguerir_ca"] = summary["ops"] - int(base)
    summary.to_csv(OUT / "volvo_targeted_infra_summary.csv", index=False)
    print(summary.to_string(index=False))
    print(piv.to_string())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
