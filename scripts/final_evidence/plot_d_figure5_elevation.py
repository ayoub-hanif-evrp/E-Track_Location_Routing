#!/usr/bin/env python3
"""D-Figure 5 — Ordered DEM elevation profiles for representative corridors.

Uses path-ordered decision-arc reconstruction (not length-sorted arc bags).
"""
from __future__ import annotations

import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts/final_evidence"))

from elevation_profiles import (  # noqa: E402
    audit_decision_arc_dem_coverage,
    reconstruct_od_elevation,
)

FIG = ROOT / "results/final_evidence/figures/dataset"
SRC = FIG / "source_data"
DS = ROOT / "results/final_evidence/dataset"

CORRIDORS = [
    ("casa_agadir", "Casablanca → Agadir"),
    ("agadir_casa", "Agadir → Casablanca"),
    ("casa_marrakech", "Casablanca → Marrakech"),
    ("rabat_fes", "Rabat → Fès"),
]


def main() -> None:
    FIG.mkdir(parents=True, exist_ok=True)
    SRC.mkdir(parents=True, exist_ok=True)

    fig, axes = plt.subplots(2, 2, figsize=(11, 7), constrained_layout=True)
    fig.patch.set_facecolor("white")
    summary_rows = []
    for ax, (od, title) in zip(axes.ravel(), CORRIDORS):
        ax.set_facecolor("white")
        # Primary: shortest; secondary: diversity alternative dashed if distinct
        short = reconstruct_od_elevation(od, method="shortest_distance")
        alt = reconstruct_od_elevation(od, method="edge_penalty")
        if len(short.distances_m):
            ax.plot(
                short.distances_m / 1000.0,
                short.elevations_m,
                color="#0072B2",
                lw=1.4,
                label="shortest",
            )
            short.to_frame().to_csv(SRC / f"D-Fig5_{od}_shortest_profile.csv", index=False)
        if (
            len(alt.distances_m)
            and abs(alt.path_length_m - short.path_length_m) > 500.0
        ):
            ax.plot(
                alt.distances_m / 1000.0,
                alt.elevations_m,
                color="#E69F00",
                lw=1.0,
                ls="--",
                label="edge_penalty alt",
            )
            alt.to_frame().to_csv(SRC / f"D-Fig5_{od}_edge_penalty_profile.csv", index=False)
        # Keep legacy filename as shortest (authoritative display path)
        if len(short.distances_m):
            short.to_frame().assign(
                route_method="shortest_distance"
            ).to_csv(SRC / f"D-Fig5_{od}_profile.csv", index=False)

        err_km = short.length_error_m / 1000.0
        ax.set_title(
            f"{title}\n"
            f"+{short.cum_gain_m:.0f} m / −{short.cum_loss_m:.0f} m | "
            f"L={short.path_length_m/1000:.1f} km "
            f"(Δstitch={err_km:+.2f} km) | cov={short.dem_coverage_frac:.0%}"
        )
        ax.set_xlabel("Distance along ordered route (km)")
        ax.set_ylabel("Elevation (m)")
        ax.grid(True, ls=":", lw=0.4)
        if len(short.distances_m) or len(alt.distances_m):
            ax.legend(fontsize=7, loc="best")
        else:
            ax.text(0.5, 0.5, "No DEM profiles", ha="center", transform=ax.transAxes)

        summary_rows.append(
            {
                "od_id": od,
                "method": "shortest_distance",
                "path_length_km": short.path_length_m / 1000.0,
                "stitched_length_km": short.stitched_length_m / 1000.0,
                "length_error_km": short.length_error_m / 1000.0,
                "cum_gain_m": short.cum_gain_m,
                "cum_loss_m": short.cum_loss_m,
                "dem_coverage_frac": short.dem_coverage_frac,
                "n_arcs": len(short.arc_ids),
                "n_missing": len(short.missing_arc_ids),
                "continuity_ok": short.continuity_ok,
                "notes": ";".join(short.notes),
            }
        )

    fig.suptitle(
        "D-Figure 5 — Ordered DEM elevation profiles (path-specific reconstruction)",
        fontsize=12,
    )
    base = FIG / "D-Figure5_elevation_profiles"
    fig.savefig(base.with_suffix(".pdf"))
    fig.savefig(base.with_suffix(".png"), dpi=400)
    fig.savefig(base.with_suffix(".svg"))
    plt.close(fig)
    pd.DataFrame(summary_rows).to_csv(SRC / "D-Fig5_panel_summary.csv", index=False)

    # Grade distribution from ordered shortest profiles (not bag of arcs)
    grades = []
    for od, _ in CORRIDORS:
        prof = reconstruct_od_elevation(od, method="shortest_distance")
        if len(prof.distances_m) < 2:
            continue
        dd = np.diff(prof.distances_m)
        dz = np.diff(prof.elevations_m)
        ok = dd > 1.0
        if np.any(ok):
            grades.extend((np.abs(dz[ok] / dd[ok]) * 100.0).tolist())
    fig2, ax = plt.subplots(figsize=(5.5, 3.8))
    if grades:
        ax.hist(grades, bins=30, color="#56B4E9", edgecolor="white")
        pd.Series(grades, name="abs_grade_pct").describe().to_frame().to_csv(
            SRC / "D-Fig5_grade_distribution.csv"
        )
    ax.set_xlabel("|grade| along ordered route samples (%)")
    ax.set_ylabel("Count")
    ax.set_title("Representative-corridor gradient distribution")
    base2 = FIG / "D-Figure5b_gradient_distribution"
    fig2.savefig(base2.with_suffix(".pdf"))
    fig2.savefig(base2.with_suffix(".png"), dpi=400)
    plt.close(fig2)

    # Persist decision-arc DEM coverage audit
    cov = audit_decision_arc_dem_coverage()
    cov.to_csv(DS / "dem_decision_arc_coverage_audit.csv", index=False)
    (FIG / "D-Figure5_description.md").write_text(
        "D-Figure 5: Path-ordered DEM elevation for shortest (and diversity) "
        "alternatives using OD-local decision-arc contraction. Distance verified "
        "against path_alternatives.length_m; junction duplicates dropped.\n",
        encoding="utf-8",
    )
    print("Wrote", base, base2)
    print(pd.DataFrame(summary_rows).to_string(index=False))


if __name__ == "__main__":
    main()
