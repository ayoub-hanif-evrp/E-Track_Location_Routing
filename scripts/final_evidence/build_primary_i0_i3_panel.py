#!/usr/bin/env python3
"""P1 — Authoritative 224-cell I0–I3 infrastructure panel (2×2×4×14)."""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
FE = ROOT / "results/final_evidence"
EXP = FE / "experiments"
TAB = FE / "tables/results"
FIG = FE / "figures/results"

EXPECTED = {
    ("eactros_600", "stressed_mixed"): {"I0_none": 9, "I1_benguerir_ca": 11, "I2_benguerir_larache": 12, "I3_benguerir_ca_larache_benguerir_ac": 13},
    ("eactros_600", "common_soc_80"): {"I0_none": 11, "I1_benguerir_ca": 12, "I2_benguerir_larache": 13, "I3_benguerir_ca_larache_benguerir_ac": 14},
    ("volvo_475", "stressed_mixed"): {"I0_none": 7, "I1_benguerir_ca": 7, "I2_benguerir_larache": 8, "I3_benguerir_ca_larache_benguerir_ac": 8},
    ("volvo_475", "common_soc_80"): {"I0_none": 8, "I1_benguerir_ca": 9, "I2_benguerir_larache": 10, "I3_benguerir_ca_larache_benguerir_ac": 10},
}

# Explicit directional installation counts (not geography-only site names).
INSTALLATION_META = {
    "I0_none": {
        "n_directional_installations": 0,
        "directional_site_ids": "",
        "provenance": "primary_comparison",
    },
    "I1_benguerir_ca": {
        "n_directional_installations": 1,
        "directional_site_ids": "y_benguerir_ca",
        "provenance": "primary_comparison",
    },
    "I2_benguerir_larache": {
        "n_directional_installations": 2,
        "directional_site_ids": "y_benguerir_ca,y_larache_rt",
        "provenance": "primary_comparison",
    },
    "I3_benguerir_ca_larache_benguerir_ac": {
        "n_directional_installations": 3,
        "directional_site_ids": "y_benguerir_ca,y_larache_rt,y_benguerir_ac",
        "provenance": "i3_three_site",
    },
}


def main() -> int:
    prim = pd.read_csv(EXP / "primary_comparison/primary_missions.csv")
    i3 = pd.read_csv(EXP / "i3_three_site/i3_missions.csv")

    # Normalize I3 infra id if needed
    if "infra_config_id" in i3.columns:
        i3 = i3.copy()
        i3["infra_config_id"] = i3["infra_config_id"].replace(
            {
                "I3_plus_benguerir_ac": "I3_benguerir_ca_larache_benguerir_ac",
                "I3_benguerir_ca_larache_ac": "I3_benguerir_ca_larache_benguerir_ac",
            }
        )

    keep = [
        c
        for c in [
            "mission_id",
            "od_id",
            "vehicle_key",
            "soc_scenario",
            "soc_frac",
            "stressed_soc_frac",
            "payload_kg",
            "infra_config_id",
            "installed",
            "status",
            "energy_status",
            "energy_feasible_energy_only",
            "energy_feasible",
            "operationally_served",
            "hos_ok",
            "daily_driving_ok",
            "duty_scope",
            "audit_ok",
            "min_soc",
            "arrival_soc",
            "road_km",
            "drive_min_phys",
            "charge_min_phys",
            "wait_min_phys",
            "objective",
            "solve_sec",
            "git_sha",
            "pipeline",
            "action_trace_json",
            "n_trace_actions",
        ]
        if c in set(prim.columns) | set(i3.columns)
    ]
    for c in keep:
        if c not in prim.columns:
            prim[c] = pd.NA
        if c not in i3.columns:
            i3[c] = pd.NA

    panel = pd.concat([prim[keep], i3[keep]], ignore_index=True)
    panel["experiment_source"] = panel["infra_config_id"].map(
        lambda x: INSTALLATION_META.get(str(x), {}).get("provenance", "unknown")
    )
    panel["n_directional_installations"] = panel["infra_config_id"].map(
        lambda x: INSTALLATION_META.get(str(x), {}).get("n_directional_installations")
    )
    panel["directional_site_ids"] = panel["infra_config_id"].map(
        lambda x: INSTALLATION_META.get(str(x), {}).get("directional_site_ids", "")
    )

    key = ["vehicle_key", "soc_scenario", "infra_config_id", "od_id"]
    assert panel.drop_duplicates(key).shape[0] == len(panel), "duplicate scenario keys"
    assert len(panel) == 224, f"expected 224 rows, got {len(panel)}"

    out_dir = EXP / "primary_i0_i3_panel"
    out_dir.mkdir(parents=True, exist_ok=True)
    panel.to_csv(out_dir / "primary_i0_i3_missions.csv", index=False)
    panel.to_csv(TAB / "R-T03_mission_level_operational_results.csv", index=False)

    summary = (
        panel.groupby(["vehicle_key", "soc_scenario", "infra_config_id"], as_index=False)
        .agg(
            ops_served=("operationally_served", "sum"),
            energy_served=("energy_feasible_energy_only", "sum"),
            n_missions=("od_id", "count"),
            n_directional_installations=("n_directional_installations", "first"),
            directional_site_ids=("directional_site_ids", "first"),
            experiment_source=("experiment_source", "first"),
        )
    )
    summary["ops_coverage"] = summary["ops_served"] / summary["n_missions"]
    summary["energy_coverage"] = summary["energy_served"] / summary["n_missions"]
    summary.to_csv(out_dir / "primary_i0_i3_summary.csv", index=False)
    summary.to_csv(TAB / "R-T02_infrastructure_coverage.csv", index=False)

    # Ladder check (informational; do not hard-fail here)
    ladder_rows = []
    mismatches = []
    for (vk, soc), exp in EXPECTED.items():
        for infra, n_exp in exp.items():
            hit = summary[
                (summary.vehicle_key == vk)
                & (summary.soc_scenario == soc)
                & (summary.infra_config_id == infra)
            ]
            got = int(hit.iloc[0].ops_served) if len(hit) else None
            ladder_rows.append(
                {
                    "vehicle_key": vk,
                    "soc_scenario": soc,
                    "infra_config_id": infra,
                    "ops_served": got,
                    "expected": n_exp,
                    "match": got == n_exp,
                }
            )
            if got != n_exp:
                mismatches.append((vk, soc, infra, got, n_exp))
    ladder = pd.DataFrame(ladder_rows)
    ladder.to_csv(out_dir / "coverage_ladder_check.csv", index=False)
    (out_dir / "panel_fingerprint.json").write_text(
        json.dumps(
            {
                "n_rows": int(len(panel)),
                "n_unique_keys": int(panel.drop_duplicates(key).shape[0]),
                "infra_levels": sorted(panel.infra_config_id.astype(str).unique()),
                "n_directional_note": (
                    "Counts distinct directional installation IDs "
                    "(y_benguerir_ca, y_larache_rt, y_benguerir_ac), not undirected "
                    "geographical service-area locations."
                ),
                "optimality_claim": (
                    "No global optimality or minimum-infrastructure claim; "
                    "panel reports evaluated configurations only."
                ),
                "ladder_mismatches": [
                    {"vehicle": a, "soc": b, "infra": c, "got": d, "expected": e}
                    for a, b, c, d, e in mismatches
                ],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(summary.to_string(index=False))
    if mismatches:
        print("LADDER_MISMATCHES", mismatches)
    else:
        print("LADDER_OK")
    print("Wrote 224-cell panel + R-T02/R-T03")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
