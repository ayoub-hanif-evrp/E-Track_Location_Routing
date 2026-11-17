#!/usr/bin/env python
"""Build publication Results A–D tables from paper_campaign artifacts.

Does not re-solve; reads CSVs written by run_paper_scientific_results_campaign.py.
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "results/paper_campaign"
PUB = OUT / "publication_tables"
PUB.mkdir(parents=True, exist_ok=True)


def _flip_inventory(confirm: pd.DataFrame) -> pd.DataFrame:
    c = confirm.copy()
    c["multi_change"] = c["multi_ops_q5"] != c["multi_ops"]
    c["fixed_change"] = c["fixed_ops_q5"] != c["fixed_ops"]
    flips = c[c["multi_change"] | c["fixed_change"]].copy()
    flips["change_class"] = flips.apply(
        lambda r: (
            "both"
            if r.multi_change and r.fixed_change
            else ("multi_only" if r.multi_change else "fixed_only")
        ),
        axis=1,
    )
    return flips[
        [
            "vehicle_key",
            "od_id",
            "payload_kg",
            "soc_frac",
            "infra_label",
            "multi_ops_q5",
            "multi_ops",
            "fixed_ops_q5",
            "fixed_ops",
            "multi_min_soc",
            "change_class",
            "survives_q2",
        ]
    ]


def _frontier_summary(front: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict] = []
    for keys, g in front.groupby(["vehicle_key", "od_id", "payload_kg", "soc_frac"]):
        served = g[g["multi_ops"] == True]  # noqa: E712
        rows.append(
            {
                "vehicle_key": keys[0],
                "od_id": keys[1],
                "payload_kg": keys[2],
                "soc_frac": keys[3],
                "multi_any": bool(g["multi_ops"].max()),
                "fixed_any": bool(g["fixed_ops"].max()),
                "flex_any": bool(g["flexibility_ops_gain"].max()),
                "min_sites_multi": int(served["n_sites"].min()) if len(served) else -1,
                "best_infra_multi": (
                    served.sort_values(["n_sites", "infra_label"]).iloc[0]["infra_label"]
                    if len(served)
                    else ""
                ),
            }
        )
    return pd.DataFrame(rows)


def main() -> None:
    front = pd.read_csv(OUT / "payload_soc_frontier.csv")
    confirm = pd.read_csv(OUT / "payload_soc_frontier_q2_confirm.csv")
    flips = _flip_inventory(confirm)
    flips.to_csv(PUB / "table_q2_flip_inventory.csv", index=False)

    summ = _frontier_summary(front)
    summ.to_csv(PUB / "table_payload_soc_feasibility.csv", index=False)

    # Result A: coverage vs budget from AF + headline
    rows = []
    for name in ("q2_critical_portfolio.csv", "method_comparison_AF.csv"):
        p = OUT / name
        if p.exists():
            df = pd.read_csv(p)
            df = df.copy()
            df["source"] = name
            rows.append(df)
    if rows:
        pd.concat(rows, ignore_index=True).to_csv(
            PUB / "table_coverage_vs_budget.csv", index=False
        )

    if (OUT / "robustness_matrix.csv").exists():
        pd.read_csv(OUT / "robustness_matrix.csv").to_csv(
            PUB / "table_robustness_summary.csv", index=False
        )

    if (OUT / "operational_efficiency.csv").exists():
        pd.read_csv(OUT / "operational_efficiency.csv").to_csv(
            PUB / "table_mission_routing_performance.csv", index=False
        )

    meta = {
        "frontier_rows": int(len(front)),
        "confirm_rows": int(len(confirm)),
        "agree_multi": int((confirm.multi_ops_q5 == confirm.multi_ops).sum()),
        "agree_both_methods": int(
            (
                (confirm.multi_ops_q5 == confirm.multi_ops)
                & (confirm.fixed_ops_q5 == confirm.fixed_ops)
            ).sum()
        ),
        "n_flips_any_method": int(len(flips)),
        "frontier_git_sha_unique": sorted(map(str, front.get("git_sha", pd.Series(dtype=str)).unique())),
        "restored_from_logs": bool(
            front.get("git_sha", pd.Series(dtype=str)).astype(str).str.contains("restored").any()
        ),
    }
    (PUB / "evidence_crosswalk.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    print(json.dumps(meta, indent=2))
    print("Wrote", PUB)


if __name__ == "__main__":
    main()
