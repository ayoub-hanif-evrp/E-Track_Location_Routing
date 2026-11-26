#!/usr/bin/env python3
"""D-Figure 6 — Dataset quality and descriptive statistics (programmatic)."""
from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
TAB = ROOT / "results/final_evidence/tables/dataset"
DS = ROOT / "results/final_evidence/dataset"
FIG = ROOT / "results/final_evidence/figures/dataset"
SRC = FIG / "source_data"

# Colorblind-safe palette (Okabe–Ito)
C = {
    "blue": "#0072B2",
    "orange": "#E69F00",
    "green": "#009E73",
    "sky": "#56B4E9",
    "vermillion": "#D55E00",
    "purple": "#CC79A7",
    "grey": "#999999",
}


def main() -> None:
    FIG.mkdir(parents=True, exist_ok=True)
    SRC.mkdir(parents=True, exist_ok=True)

    hw = pd.read_csv(DS / "highway_class_directed_km.csv")
    od = pd.read_csv(TAB / "D-T03_od_inventory.csv")
    div = pd.read_csv(DS / "path_diversity_audit_copy.csv")
    dem = pd.read_csv(DS / "dem_arc_meta_summary.csv")
    cand = pd.read_csv(TAB / "D-T04_candidate_inventory.csv")

    fig, axes = plt.subplots(2, 3, figsize=(12.5, 7.5), constrained_layout=True)
    fig.patch.set_facecolor("white")

    # (a) Road-class composition (expanded)
    ax = axes[0, 0]
    exp = hw[hw.network == "expanded_motorway_trunk_primary"].sort_values("directed_km")
    ax.barh(exp["highway"], exp["directed_km"], color=C["blue"])
    ax.set_xlabel("Directed length (km)")
    ax.set_title("(a) Expanded network road classes")
    exp.to_csv(SRC / "D-Fig6a_highway_km.csv", index=False)

    # (b) OD distances
    ax = axes[0, 1]
    od_plot = od.copy()
    od_plot["km"] = od_plot["length_m_shortest"] / 1000.0
    colors = [C["green"] if x else C["grey"] for x in od_plot["in_headline"]]
    ax.barh(od_plot["od_id"], od_plot["km"], color=colors)
    ax.set_xlabel("Shortest alternative (km)")
    ax.set_title("(b) OD distances (green=headline 14)")
    od_plot[["od_id", "km", "in_headline"]].to_csv(SRC / "D-Fig6b_od_km.csv", index=False)

    # (c) Route diversity
    ax = axes[0, 2]
    d2 = div.copy()
    # one row per OD: max jaccard among non-shortest methods if present
    g = d2.groupby("od_id").agg(
        max_jaccard=("jaccard_distance_vs_shortest", "max"),
        max_ratio=("length_ratio_vs_shortest", "max"),
    ).reset_index()
    ax.scatter(g["max_ratio"], g["max_jaccard"], c=C["orange"], s=40, edgecolors="k", linewidths=0.3)
    ax.set_xlabel("Length ratio vs shortest")
    ax.set_ylabel("Max Jaccard distance vs shortest")
    ax.set_title("(c) Route diversity")
    ax.axhline(0.05, color=C["grey"], ls="--", lw=0.8, label="near-duplicate")
    g.to_csv(SRC / "D-Fig6c_diversity.csv", index=False)

    # (d) DEM grade distribution
    ax = axes[1, 0]
    grades = dem["max_abs_grade"].dropna() * 100.0
    ax.hist(grades, bins=30, color=C["sky"], edgecolor="white")
    ax.set_xlabel("Arc max |grade| (%)")
    ax.set_ylabel("Arc count")
    ax.set_title("(d) DEM grade distribution")
    grades.describe().to_csv(SRC / "D-Fig6d_grade_summary.csv")

    # (e) Candidate matching status
    ax = axes[1, 1]
    vc = cand["location_match_status"].value_counts()
    ax.bar(vc.index.astype(str), vc.values, color=[C["green"], C["vermillion"]][: len(vc)])
    ax.set_ylabel("Count")
    ax.set_title("(e) Candidate OSM match status")
    ax.tick_params(axis="x", rotation=20)
    vc.rename_axis("status").reset_index(name="n").to_csv(
        SRC / "D-Fig6e_candidate_match.csv", index=False
    )

    # (f) Access status
    ax = axes[1, 2]
    ac = cand["directed_access_status"].value_counts()
    ax.barh(ac.index.astype(str), ac.values, color=C["purple"])
    ax.set_xlabel("Count")
    ax.set_title("(f) Directed access status")
    ac.rename_axis("status").reset_index(name="n").to_csv(
        SRC / "D-Fig6f_candidate_access.csv", index=False
    )

    for ax in axes.ravel():
        ax.set_facecolor("white")
        for spine in ax.spines.values():
            spine.set_color("#333333")

    out_base = FIG / "D-Figure6_dataset_descriptive_stats"
    fig.savefig(out_base.with_suffix(".pdf"))
    fig.savefig(out_base.with_suffix(".png"), dpi=400)
    fig.savefig(out_base.with_suffix(".svg"))
    plt.close(fig)

    desc = FIG / "D-Figure6_description.md"
    desc.write_text(
        "\n".join(
            [
                "# D-Figure 6 — Dataset quality and descriptive statistics",
                "",
                "**Purpose:** Summarise constructed-network composition, OD distances,",
                "route diversity, DEM grades, and candidate match/access status.",
                "",
                "**Sources:** `tables/dataset/D-T03*`, `D-T04*`, `dataset/highway_class_directed_km.csv`,",
                "`dataset/dem_arc_meta_summary.csv`, `dataset/path_diversity_audit_copy.csv`.",
                "",
                "**Script:** `scripts/final_evidence/plot_d_figure6_dataset_stats.py`",
                "",
                "**Validation:** Counts must agree with independent recount summary.",
                "",
            ]
        ),
        encoding="utf-8",
    )
    print("Wrote", out_base)


if __name__ == "__main__":
    main()
