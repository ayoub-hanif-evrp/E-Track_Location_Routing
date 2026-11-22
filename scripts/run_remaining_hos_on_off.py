#!/usr/bin/env python
"""P7: matched HOS-on vs energy-only (HOS-off search) on Benguerir install."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from run_final_operational_correction import (  # noqa: E402
    coverage_from_mission_rows,
    evaluate_mission_operational,
)
import run_stage_c_hos_national as stage_c  # noqa: E402

OUT = ROOT / "results" / "validation" / "p7_hos_on_off"
SITE = {"y_benguerir_ca"}


def main() -> None:
    """Compare dual-solve energy_feasible_energy_only vs operationally_served.

    Uses the production evaluator: energy-only path is hos_in_search=False;
    ops path is hos_in_search=True. Same sites/masks/limits.
    """
    OUT.mkdir(parents=True, exist_ok=True)
    orig = stage_c._patch_realistic_speed_policy()
    rows = []
    try:
        for mdef in stage_c._corridor_missions():
            od = str(mdef["od_id"])
            payload = float(mdef.get("cargo_payload_kg", 5300.0))
            soc = float(mdef.get("E_init_soc_frac", 0.8))
            print(f"[hos] {od}", flush=True)
            ev = stage_c._eval_installed_on_panel(
                vehicle_key="eactros_600",
                installed=SITE,
                route_mode="multi",
                method_id="hos_compare",
                budget="B1",
                q=2,
                max_seconds=stage_c.UNIFORM_MAX_SECONDS,
                max_expansions=stage_c.ABLATION_MAX_EXPANSIONS,
                od_filter={od},
                include_energy_only=True,
            )
            for mr in ev["mission_rows"]:
                rows.append(
                    {
                        "od_id": mr.get("od_id"),
                        "status_ops": mr.get("status"),
                        "status_energy": mr.get("energy_status"),
                        "ops_hos_on": bool(mr.get("operationally_served")),
                        "energy_hos_off": bool(
                            mr.get("energy_feasible_energy_only") or mr.get("energy_feasible")
                        ),
                        "min_soc": mr.get("min_soc"),
                        "hos_search_audit_only": mr.get("hos_search_audit_only"),
                        "solve_sec": mr.get("solve_sec"),
                        "installed": ",".join(sorted(SITE)),
                        "git_sha": stage_c.SHA,
                        "pipeline": "p7_hos_on_off",
                        "weight": float(mr.get("weight") or 1.0),
                    }
                )
                print(
                    f"  energy={rows[-1]['energy_hos_off']} ops={rows[-1]['ops_hos_on']} "
                    f"status={rows[-1]['status_ops']}/{rows[-1]['status_energy']}",
                    flush=True,
                )
            stage_c._write_csv(OUT / "hos_on_off_missions.csv", rows)
    finally:
        import morocco_etruck.optimization.multiroute_placement_evaluation as mpe

        mpe.load_multiroute_pilot_config = orig

    n = len(rows)
    n_ops = sum(1 for r in rows if r["ops_hos_on"])
    n_en = sum(1 for r in rows if r["energy_hos_off"])
    n_diff = sum(1 for r in rows if r["energy_hos_off"] and not r["ops_hos_on"])
    summary = [
        {
            "metric": "energy_hos_off_coverage",
            "value": n_en / n if n else 0.0,
            "n": n_en,
            "git_sha": stage_c.SHA,
        },
        {
            "metric": "ops_hos_on_coverage",
            "value": n_ops / n if n else 0.0,
            "n": n_ops,
            "git_sha": stage_c.SHA,
        },
        {
            "metric": "energy_true_ops_false",
            "value": n_diff / n if n else 0.0,
            "n": n_diff,
            "note": "HOS/search operational gap vs energy-only",
            "git_sha": stage_c.SHA,
        },
    ]
    stage_c._write_csv(OUT / "hos_on_off_summary.csv", summary)
    print(summary, flush=True)


if __name__ == "__main__":
    main()
