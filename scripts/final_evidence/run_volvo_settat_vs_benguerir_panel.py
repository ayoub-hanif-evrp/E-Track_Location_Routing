#!/usr/bin/env python3
"""P2 — Full 14-mission Volvo panel: Settat CA+Larache RT vs Benguerir CA+Larache RT."""
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

OUT = ROOT / "results/final_evidence/experiments/volvo_settat_vs_benguerir"
TAB = ROOT / "results/final_evidence/tables/results"

CONFIGS = [
    ("V_benguerir_larache", {"y_benguerir_ca", "y_larache_rt"}),
    ("V_settat_larache", {"y_settat_ca", "y_larache_rt"}),
]
SOC_SCENARIOS = [
    ("stressed_mixed", None),  # per-mission stressed SOC
    ("common_soc_80", 0.8),
]


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    TAB.mkdir(parents=True, exist_ok=True)
    sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT).decode().strip()
    missions = stage_c._corridor_missions()
    assert len(missions) == 14, len(missions)

    orig = stage_c._patch_realistic_speed_policy()
    rows = []
    try:
        for soc_name, soc_override in SOC_SCENARIOS:
            for mdef in missions:
                od = mdef["od_id"]
                payload = float(mdef.get("cargo_payload_kg", 5300.0))
                soc = float(soc_override) if soc_override is not None else float(
                    mdef.get("E_init_soc_frac", 0.5)
                )
                cfg, vehicle, context, masks = stage_c._prepare_one(
                    vehicle_key="volvo_475", od_id=od, payload=payload, soc=soc, q=2
                )
                mid = context["missions"][0].id
                for cfg_id, installed in CONFIGS:
                    print(f"[volvo-panel] {soc_name} {od} {cfg_id}", flush=True)
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
                            "soc_scenario": soc_name,
                            "infra_config_id": cfg_id,
                            "installed": ",".join(sorted(installed)),
                            "n_directional_installations": 2,
                            "vehicle_key": "volvo_475",
                            "git_sha": sha,
                            "pipeline": "final_evidence_volvo_settat_vs_benguerir",
                        }
                    )
                    rows.append(row)
                    print(
                        f"  status={row.get('status')} ops={row.get('operationally_served')} "
                        f"energy={row.get('energy_status')} road_km={row.get('road_km')} "
                        f"drive_min={row.get('drive_min_phys')}",
                        flush=True,
                    )
                    pd.DataFrame(rows).to_csv(OUT / "volvo_settat_vs_benguerir_missions.csv", index=False)
    finally:
        import morocco_etruck.optimization.multiroute_placement_evaluation as mpe

        mpe.load_multiroute_pilot_config = orig

    df = pd.DataFrame(rows)
    df.to_csv(OUT / "volvo_settat_vs_benguerir_missions.csv", index=False)
    df.to_csv(TAB / "R-T02_volvo_settat_vs_benguerir_missions.csv", index=False)

    summary = (
        df.groupby(["soc_scenario", "infra_config_id"], as_index=False)
        .agg(
            ops_served=("operationally_served", "sum"),
            energy_served=("energy_feasible_energy_only", "sum"),
            n_missions=("od_id", "count"),
            mean_road_km=("road_km", "mean"),
            mean_drive_min=("drive_min_phys", "mean"),
            mean_objective=("objective", "mean"),
        )
    )
    # Pairwise deltas Settat vs Benguerir
    piv_ops = df.pivot_table(
        index=["soc_scenario", "od_id"],
        columns="infra_config_id",
        values="operationally_served",
        aggfunc="max",
    )
    piv_ops.to_csv(OUT / "volvo_settat_vs_benguerir_ops_matrix.csv")
    piv_ops.to_csv(TAB / "R-T02_volvo_settat_vs_benguerir_ops_matrix.csv")

    summary.to_csv(OUT / "volvo_settat_vs_benguerir_summary.csv", index=False)
    summary.to_csv(TAB / "R-T02_volvo_settat_vs_benguerir_summary.csv", index=False)
    print(summary.to_string(index=False))
    print(piv_ops.to_string())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
