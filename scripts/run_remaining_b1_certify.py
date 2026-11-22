#!/usr/bin/env python
"""Escalate all B1 single-site candidates at matched 600s/2e6 (eActros).

Writes enum_candidates_b1_certified.csv and updates E_certification if proved.
"""
from __future__ import annotations

import itertools
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import pandas as pd  # noqa: E402

import run_stage_c_hos_national as stage_c  # noqa: E402

OUT = ROOT / "results" / "validation" / "p3_b1_certify"
SITES = list(stage_c.FULL_SITE_IDS)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    orig = stage_c._patch_realistic_speed_policy()
    rows = []
    try:
        combos: list[set[str]] = [set(), *[{s} for s in SITES]]
        for installed in combos:
            label = ",".join(sorted(installed)) or "NONE"
            print(f"[b1-cert] eval {label}", flush=True)
            ev = stage_c._eval_installed_on_panel(
                vehicle_key="eactros_600",
                installed=set(installed),
                route_mode="multi",
                method_id="b1_cert_multi",
                budget="B1",
                q=2,
                max_seconds=stage_c.UNIFORM_MAX_SECONDS,
                max_expansions=stage_c.ABLATION_MAX_EXPANSIONS,
                include_energy_only=True,
            )
            rows.append(
                {
                    "tag": "b1_certify_eactros",
                    "vehicle_key": "eactros_600",
                    "budget": "B1",
                    "sites": label,
                    "n_sites": len(installed),
                    "ops": float(ev["operational_coverage"]),
                    "energy": float(ev["energy_coverage"]),
                    "n_limit": int(ev.get("n_limit_reached") or 0),
                    "n_optimal": int(ev.get("n_optimal") or 0),
                    "n_infeasible": int(ev.get("n_infeasible") or 0),
                    "n_ops": int(ev.get("n_operationally_served") or 0),
                    "max_seconds": stage_c.UNIFORM_MAX_SECONDS,
                    "max_expansions": stage_c.ABLATION_MAX_EXPANSIONS,
                    "eval_phase": "final_matched",
                    "git_sha": stage_c.SHA,
                }
            )
            stage_c._write_csv(OUT / "enum_candidates_b1_certified.csv", rows)
            stage_c._write_csv(
                OUT / f"missions_{label.replace(',', '_') or 'NONE'}.csv",
                ev["mission_rows"],
            )
            print(
                f"  ops={rows[-1]['ops']:.3f} limit={rows[-1]['n_limit']}",
                flush=True,
            )
    finally:
        import morocco_etruck.optimization.multiroute_placement_evaluation as mpe

        mpe.load_multiroute_pilot_config = orig

    df = pd.DataFrame(rows)
    best = df.sort_values(
        ["ops", "energy", "n_sites"], ascending=[False, False, True]
    ).iloc[0]
    any_limit = int(df["n_limit"].sum()) > 0
    cert = (
        "certified_exact_under_cap_B1_singles"
        if not any_limit
        else "best_of_matched_B1_singles_limit_contaminated"
    )
    summary = {
        "best_sites": best["sites"],
        "best_ops": float(best["ops"]),
        "any_limit": any_limit,
        "E_certification": cert,
        "n_candidates": len(df),
        "git_sha": stage_c.SHA,
    }
    (OUT / "b1_certification_summary.json").write_text(
        __import__("json").dumps(summary, indent=2), encoding="utf-8"
    )
    # Patch portfolio label if clean
    port = stage_c.OUT / "q2_critical_portfolio.csv"
    if port.exists() and not any_limit:
        pdf = pd.read_csv(port)
        m = (pdf.vehicle_key == "eactros_600") & (pdf.budget.astype(str) == "B1")
        if "E_certification" in pdf.columns:
            pdf.loc[m, "E_certification"] = cert
        pdf.to_csv(port, index=False)
    print(f"[b1-cert] {summary}", flush=True)


if __name__ == "__main__":
    main()
