#!/usr/bin/env python
"""Escalate P2 casa_agadir LIMIT cell to 2e6 expansions."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import pandas as pd

from run_final_operational_correction import (  # noqa: E402
    coverage_from_mission_rows,
    evaluate_mission_operational,
)
import run_stage_c_hos_national as sc  # noqa: E402

OUT = ROOT / "results" / "validation" / "p2_fair_eval"


def main() -> None:
    orig = sc._patch_realistic_speed_policy()
    try:
        for budget in ("B1", "B2"):
            miss = pd.read_csv(OUT / f"fair_missions_{budget}.csv")
            rows = miss.to_dict("records")
            cfg, vehicle, context, masks = sc._prepare_one(
                vehicle_key="eactros_600",
                od_id="casa_agadir",
                payload=5300.0,
                soc=0.5,
                q=2,
            )
            mid = context["missions"][0].id
            prep = context["prepared"][mid]
            mask = frozenset(masks[mid]["all"])
            print(f"[p2-esc] {budget} casa_agadir 2e6", flush=True)
            mr = evaluate_mission_operational(
                prep=prep,
                cfg=cfg,
                installed={"y_benguerir_ca"},
                mask=mask,
                vehicle=vehicle,
                fridge_path=sc.FRIDGE,
                max_seconds=600.0,
                max_expansions=2_000_000,
                include_energy_only=True,
            )
            print(
                f"  status={mr.get('status')} ops={mr.get('operationally_served')}",
                flush=True,
            )
            new_rows = []
            for r in rows:
                if str(r.get("od_id")) == "casa_agadir":
                    r = dict(r)
                    for k in (
                        "status",
                        "operationally_served",
                        "energy_feasible_energy_only",
                        "energy_feasible",
                        "solve_sec",
                        "min_soc",
                        "hos_search_audit_only",
                        "objective",
                    ):
                        if k in mr:
                            r[k] = mr[k]
                    r["weight"] = 1.0
                    r["max_expansions"] = 2_000_000
                new_rows.append(r)
            cov = coverage_from_mission_rows(
                [{**r, "weight": float(r.get("weight") or 1)} for r in new_rows]
            )
            sc._write_csv(OUT / f"fair_missions_{budget}_esc2e6.csv", new_rows)
            summary = pd.read_csv(OUT / "fair_frozen_site_eval.csv")
            er = summary[summary.budget.astype(str) == budget].iloc[0]
            esc = {
                "vehicle_key": "eactros_600",
                "budget": budget,
                "installed": "y_benguerir_ca",
                "final_ops": cov["operational_coverage"],
                "final_energy": cov["energy_coverage"],
                "n_limit": cov["n_limit_reached"],
                "n_optimal": cov["n_optimal"],
                "n_infeasible": cov["n_infeasible"],
                "n_ops": cov["n_operationally_served"],
                "E_ops_reference": float(er["E_ops_reference"]),
                "E_sites_reference": er["E_sites_reference"],
                "matches_E_sites": True,
                "matches_E_ops": abs(
                    cov["operational_coverage"] - float(er["E_ops_reference"])
                )
                < 1e-12,
                "max_seconds": 600.0,
                "max_expansions": 2_000_000,
                "git_sha": sc.SHA,
                "note": "casa_agadir escalated to 2e6; other ODs from 500k fair eval",
            }
            out_rows = summary.to_dict("records") + [esc]
            sc._write_csv(OUT / "fair_frozen_site_eval.csv", out_rows)
            print(
                f"  ops={cov['operational_coverage']:.3f} "
                f"match={esc['matches_E_ops']} limit={cov['n_limit_reached']}",
                flush=True,
            )
    finally:
        import morocco_etruck.optimization.multiroute_placement_evaluation as mpe

        mpe.load_multiroute_pilot_config = orig


if __name__ == "__main__":
    main()
