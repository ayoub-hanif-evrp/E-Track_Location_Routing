#!/usr/bin/env python
"""Escalate LIMIT ODs for y_settat_ca B1 candidate; refresh certification."""
from __future__ import annotations

import json
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

OUT = ROOT / "results" / "validation" / "p3_b1_certify"
SITE = {"y_settat_ca"}


def main() -> None:
    miss = pd.read_csv(OUT / "missions_y_settat_ca.csv")
    lim = miss[miss.status.astype(str).str.upper() == "LIMIT_REACHED"]
    print(f"[esc] LIMIT ODs={lim.od_id.tolist()}", flush=True)
    orig = sc._patch_realistic_speed_policy()
    rows = miss.to_dict("records")
    try:
        for od in lim.od_id.astype(str).tolist():
            # recover payload/soc from corridor missions
            mdef = next(m for m in sc._corridor_missions() if str(m["od_id"]) == od)
            payload = float(mdef.get("cargo_payload_kg", 5300.0))
            soc = float(mdef.get("E_init_soc_frac", 0.8))
            cfg, vehicle, context, masks = sc._prepare_one(
                vehicle_key="eactros_600", od_id=od, payload=payload, soc=soc, q=2
            )
            mid = context["missions"][0].id
            prep = context["prepared"][mid]
            mask = frozenset(masks[mid]["all"])
            print(f"[esc] {od} 2e6", flush=True)
            mr = evaluate_mission_operational(
                prep=prep,
                cfg=cfg,
                installed=SITE,
                mask=mask,
                vehicle=vehicle,
                fridge_path=sc.FRIDGE,
                max_seconds=600.0,
                max_expansions=2_000_000,
                include_energy_only=True,
            )
            print(f"  status={mr.get('status')} ops={mr.get('operationally_served')}", flush=True)
            for r in rows:
                if str(r.get("od_id")) == od:
                    for k in (
                        "status",
                        "operationally_served",
                        "energy_feasible_energy_only",
                        "energy_feasible",
                        "solve_sec",
                        "min_soc",
                        "objective",
                    ):
                        if k in mr:
                            r[k] = mr[k]
                    r["weight"] = 1.0
    finally:
        import morocco_etruck.optimization.multiroute_placement_evaluation as mpe

        mpe.load_multiroute_pilot_config = orig

    cov = coverage_from_mission_rows([{**r, "weight": float(r.get("weight") or 1)} for r in rows])
    sc._write_csv(OUT / "missions_y_settat_ca_esc2e6.csv", rows)
    cand = pd.read_csv(OUT / "enum_candidates_b1_certified.csv")
    cand.loc[cand.sites == "y_settat_ca", "ops"] = cov["operational_coverage"]
    cand.loc[cand.sites == "y_settat_ca", "n_limit"] = cov["n_limit_reached"]
    cand.loc[cand.sites == "y_settat_ca", "n_ops"] = cov["n_operationally_served"]
    cand.loc[cand.sites == "y_settat_ca", "n_optimal"] = cov["n_optimal"]
    sc._write_csv(OUT / "enum_candidates_b1_certified.csv", cand.to_dict("records"))
    any_limit = int(cand["n_limit"].sum()) > 0
    best = cand.sort_values(["ops", "n_sites"], ascending=[False, True]).iloc[0]
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
        "n_candidates": len(cand),
        "settat_ops_after_escalate": cov["operational_coverage"],
        "git_sha": sc.SHA,
    }
    (OUT / "b1_certification_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    port = sc.OUT / "q2_critical_portfolio.csv"
    if port.exists() and not any_limit:
        pdf = pd.read_csv(port)
        m = (pdf.vehicle_key == "eactros_600") & (pdf.budget.astype(str) == "B1")
        if "E_certification" in pdf.columns:
            pdf.loc[m, "E_certification"] = cert
        pdf.to_csv(port, index=False)
    print(summary, flush=True)


if __name__ == "__main__":
    main()
