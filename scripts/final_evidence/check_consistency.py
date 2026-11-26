#!/usr/bin/env python3
"""Mandatory consistency checks for final evidence package.

Returns nonzero exit status on mandatory failures.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "results/final_evidence/validation"
FE = ROOT / "results/final_evidence"

CLAIMED = {
    "motorway_nodes": 58002,
    "motorway_edges": 58157,
    "expanded_nodes": 391653,
    "expanded_edges": 397255,
    "decision_nodes": 198,
    "decision_arcs": 293,
    "od_pairs": 18,
    "path_records": 36,
    "service_area_inventory": 19,
    "headline_missions": 14,
}


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    failures = []
    warnings = []

    recount = FE / "dataset/independent_recount_summary.json"
    if not recount.exists():
        failures.append("missing independent_recount_summary.json")
    else:
        summary = json.loads(recount.read_text(encoding="utf-8"))
        for k, v in CLAIMED.items():
            actual = summary.get("verified_counts", {}).get(k)
            if actual != v:
                failures.append(f"count mismatch {k}: claimed={v} verified={actual}")

    primary = FE / "experiments/primary_comparison/primary_summary.csv"
    missions = FE / "experiments/primary_comparison/primary_missions.csv"
    if primary.exists() and missions.exists():
        s = pd.read_csv(primary)
        m = pd.read_csv(missions)
        if len(m) != 168:
            failures.append(f"primary missions rows={len(m)} expected 168")
        if len(s) != 12:
            failures.append(f"primary summary rows={len(s)} expected 12")
        # LIMIT never counted as served
        bad = m[(m.status == "LIMIT_REACHED") & (m.operationally_served == True)]  # noqa: E712
        if len(bad):
            failures.append(f"LIMIT_REACHED counted as served: {len(bad)}")
        # Historical eActros stressed ladder
        for infra, expect in [
            ("I0_none", 9),
            ("I1_benguerir_ca", 11),
            ("I2_benguerir_larache", 12),
        ]:
            row = s[
                (s.vehicle_key == "eactros_600")
                & (s.soc_scenario == "stressed_mixed")
                & (s.infra_config_id == infra)
            ]
            if len(row) != 1:
                failures.append(f"missing eActros stressed {infra}")
            elif int(row.iloc[0].ops_served) != expect:
                warnings.append(
                    f"eActros stressed {infra} ops={row.iloc[0].ops_served} "
                    f"(historical reference {expect}) — report transparently"
                )
    else:
        failures.append("missing primary comparison outputs")

    # Figure/table agreement on coverage
    rt02 = FE / "tables/results/R-T02_infrastructure_coverage.csv"
    if rt02.exists() and primary.exists():
        a = pd.read_csv(rt02)
        b = pd.read_csv(primary)
        if not a[["vehicle_key", "soc_scenario", "infra_config_id", "ops_served"]].equals(
            b[["vehicle_key", "soc_scenario", "infra_config_id", "ops_served"]]
        ):
            failures.append("R-T02 ops_served disagrees with primary_summary")

    report = {
        "ok": len(failures) == 0,
        "n_failures": len(failures),
        "n_warnings": len(warnings),
        "failures": failures,
        "warnings": warnings,
    }
    (OUT / "consistency_report.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
