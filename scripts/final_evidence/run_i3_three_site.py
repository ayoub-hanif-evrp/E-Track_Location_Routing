#!/usr/bin/env python3
"""P4.1 — Evaluate I3 = Benguerir CA + Larache RT + Benguerir AC on the 14-mission panel.

Not a claim of globally optimal three-site placement — an evaluated configuration.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import run_stage_c_hos_national as stage_c  # noqa: E402

OUT = ROOT / "results/final_evidence/experiments/i3_three_site"
I3 = {"y_benguerir_ca", "y_larache_rt", "y_benguerir_ac"}


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT).decode().strip()
    # Reuse Stage C ablation runner pattern for both vehicles / SOC scenarios
    rows = stage_c.run_ablation_panel(
        vehicles=("eactros_600", "volvo_475"),
        installed_configs={
            "I3_benguerir_ca_larache_benguerir_ac": I3,
        },
        soc_scenarios=("stressed_mixed", "common_soc_80"),
        out_csv=OUT / "i3_missions.csv",
    ) if hasattr(stage_c, "run_ablation_panel") else None

    if rows is None:
        # Fallback: mirror primary comparison loop for I3 only
        from run_final_operational_correction import evaluate_mission_operational

        orig = stage_c._patch_realistic_speed_policy()
        out_rows = []
        try:
            missions = stage_c._corridor_missions()
            for vehicle_key in ("eactros_600", "volvo_475"):
                for soc_scenario in ("stressed_mixed", "common_soc_80"):
                    for mdef in missions:
                        od = mdef["od_id"]
                        payload = float(mdef.get("cargo_payload_kg", 5300.0))
                        if soc_scenario == "common_soc_80":
                            soc = 0.8
                        else:
                            soc = float(mdef.get("E_init_soc_frac", 0.8))
                        print(
                            f"[I3] {vehicle_key} {soc_scenario} {od} p={payload} soc={soc}",
                            flush=True,
                        )
                        cfg, vehicle, context, masks = stage_c._prepare_one(
                            vehicle_key=vehicle_key, od_id=od, payload=payload, soc=soc, q=2
                        )
                        mid = context["missions"][0].id
                        mr = evaluate_mission_operational(
                            prep=context["prepared"][mid],
                            cfg=cfg,
                            installed=set(I3),
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
                                "soc_scenario": soc_scenario,
                                "infra_config_id": "I3_benguerir_ca_larache_benguerir_ac",
                                "installed": ",".join(sorted(I3)),
                                "vehicle_key": vehicle_key,
                                "git_sha": sha,
                                "pipeline": "final_evidence_i3",
                            }
                        )
                        out_rows.append(row)
                        print(
                            f"  status={row.get('status')} ops={row.get('operationally_served')}",
                            flush=True,
                        )
                        pd.DataFrame(out_rows).to_csv(OUT / "i3_missions.csv", index=False)
        finally:
            import morocco_etruck.optimization.multiroute_placement_evaluation as mpe

            mpe.load_multiroute_pilot_config = orig
        df = pd.DataFrame(out_rows)
    else:
        df = pd.DataFrame(rows)

    df.to_csv(OUT / "i3_missions.csv", index=False)
    # Compare to primary I2 coverage
    primary = pd.read_csv(
        ROOT / "results/final_evidence/experiments/primary_comparison/primary_summary.csv"
    )
    summary = (
        df.groupby(["vehicle_key", "soc_scenario"])
        .agg(
            n_missions=("od_id", "count"),
            ops_served=("operationally_served", "sum"),
            n_optimal=("status", lambda s: int((s == "OPTIMAL").sum())),
            n_infeasible=("status", lambda s: int((s == "INFEASIBLE").sum())),
            n_limit=("status", lambda s: int((s == "LIMIT_REACHED").sum())),
        )
        .reset_index()
    )
    summary["infra_config_id"] = "I3_benguerir_ca_larache_benguerir_ac"
    summary.to_csv(OUT / "i3_summary.csv", index=False)
    summary.to_csv(
        ROOT / "results/final_evidence/tables/results/R-T02_i3_coverage_addendum.csv",
        index=False,
    )
    (OUT / "run_fingerprint.json").write_text(
        json.dumps(
            {
                "git_sha": sha,
                "installed": sorted(I3),
                "note": "evaluated_config_not_global_optimum",
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(summary.to_string(index=False))
    print("primary I2 reference:\n", primary[primary.infra_config_id.str.contains("I2")].to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
