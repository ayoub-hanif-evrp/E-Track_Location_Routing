#!/usr/bin/env python
"""Priority 2: fair final eval of frozen Benguerir (same sites as E).

Does not re-run full blind greedy. Scores {y_benguerir_ca} once under the
matched panel aggregator and compares to portfolio E_ops.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import pandas as pd  # noqa: E402

import run_stage_c_hos_national as stage_c  # noqa: E402

OUT = ROOT / "results" / "validation" / "p2_fair_eval"
SITE = {"y_benguerir_ca"}


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    orig = stage_c._patch_realistic_speed_policy()
    rows = []
    try:
        for budget in ("B1", "B2"):
            print(f"[p2] final eval {sorted(SITE)} budget={budget}", flush=True)
            ev = stage_c._eval_installed_on_panel(
                vehicle_key="eactros_600",
                installed=set(SITE),
                route_mode="multi",
                method_id="fair_final_benguerir",
                budget=budget,
                q=2,
                max_seconds=stage_c.UNIFORM_MAX_SECONDS,
                max_expansions=stage_c.ABLATION_MAX_EXPANSIONS,
            )
            port = pd.read_csv(stage_c.OUT / "q2_critical_portfolio.csv")
            er = port[
                (port.vehicle_key == "eactros_600") & (port.budget.astype(str) == budget)
            ]
            e_ops = float(er.iloc[0]["E_ops"]) if not er.empty else None
            e_sites = (
                stage_c._parse_sites(er.iloc[0]["E_sites"]) if not er.empty else set()
            )
            rows.append(
                {
                    "vehicle_key": "eactros_600",
                    "budget": budget,
                    "installed": ",".join(sorted(SITE)),
                    "final_ops": float(ev["operational_coverage"]),
                    "final_energy": float(ev["energy_coverage"]),
                    "n_limit": int(ev.get("n_limit_reached") or 0),
                    "n_optimal": int(ev.get("n_optimal") or 0),
                    "n_infeasible": int(ev.get("n_infeasible") or 0),
                    "n_ops": int(ev.get("n_operationally_served") or 0),
                    "E_ops_reference": e_ops,
                    "E_sites_reference": ",".join(sorted(e_sites)),
                    "matches_E_sites": set(SITE) == e_sites,
                    "matches_E_ops": e_ops is not None
                    and abs(float(ev["operational_coverage"]) - e_ops) < 1e-12,
                    "max_seconds": stage_c.UNIFORM_MAX_SECONDS,
                    "git_sha": stage_c.SHA,
                    "note": "frozen site set scored with coverage_from_mission_rows",
                }
            )
            stage_c._write_csv(OUT / "fair_frozen_site_eval.csv", rows)
            stage_c._write_csv(OUT / f"fair_missions_{budget}.csv", ev["mission_rows"])
            print(
                f"  ops={rows[-1]['final_ops']:.3f} E_ref={e_ops} "
                f"match={rows[-1]['matches_E_ops']} limit={rows[-1]['n_limit']}",
                flush=True,
            )
    finally:
        import morocco_etruck.optimization.multiroute_placement_evaluation as mpe

        mpe.load_multiroute_pilot_config = orig
    print(f"[p2] wrote {OUT}", flush=True)


if __name__ == "__main__":
    main()
