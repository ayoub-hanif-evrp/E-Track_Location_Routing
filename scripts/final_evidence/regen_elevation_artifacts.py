#!/usr/bin/env python3
"""Regenerate corrected elevation tables/figures without full dataset audit."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts/final_evidence"))

from elevation_profiles import (  # noqa: E402
    audit_decision_arc_dem_coverage,
    investigate_invalid_profiles,
    reconstruct_all_od_methods,
    reconstruct_od_elevation,
)
import plot_d_figure5_elevation as fig5  # noqa: E402

OUT = ROOT / "results/final_evidence"
DS = OUT / "dataset"
TAB = OUT / "tables/dataset"

HEADLINE = {
    "casa_marrakech",
    "casa_agadir",
    "marrakech_agadir",
    "agadir_marrakech",
    "marrakech_casa",
    "agadir_casa",
    "casa_tangier",
    "tangier_casa",
    "tangier_rabat",
    "rabat_tangier",
    "casa_rabat",
    "rabat_casa",
    "rabat_fes",
    "fes_rabat",
}


def main() -> int:
    DS.mkdir(parents=True, exist_ok=True)
    TAB.mkdir(parents=True, exist_ok=True)

    by_method = reconstruct_all_od_methods()
    by_method.to_csv(DS / "elevation_by_od_method.csv", index=False)

    rows = []
    for od in sorted(by_method["od_id"].unique()):
        short = reconstruct_od_elevation(od, method="shortest_distance")
        rows.append(
            {
                "od_id": od,
                "route_method": "shortest_distance",
                "n_arcs_on_route": len(short.arc_ids),
                "n_missing_profiles": len(short.missing_arc_ids),
                "n_invalid_profiles": len(short.invalid_arc_ids),
                "dem_coverage_frac": short.dem_coverage_frac,
                "path_length_m": short.path_length_m,
                "stitched_length_m": short.stitched_length_m,
                "length_error_m": short.length_error_m,
                "cum_gain_m": short.cum_gain_m,
                "cum_loss_m": short.cum_loss_m,
                "max_abs_grade": short.max_abs_grade,
                "continuity_ok": short.continuity_ok,
                "n_route_alternatives_profiled": int((by_method.od_id == od).sum()),
                "in_headline": od in HEADLINE,
                "notes": ";".join(short.notes),
            }
        )
    elev = pd.DataFrame(rows)
    elev.to_csv(TAB / "D-T05_elevation_by_mission.csv", index=False)

    cov = audit_decision_arc_dem_coverage()
    cov.to_csv(DS / "dem_decision_arc_coverage_audit.csv", index=False)
    inv = investigate_invalid_profiles()
    inv.to_csv(DS / "dem_invalid_profile_investigation.csv", index=False)

    # Update D-T03 elevation columns if present
    dt03 = TAB / "D-T03_od_inventory.csv"
    if dt03.exists():
        od = pd.read_csv(dt03)
        drop_cols = [
            c
            for c in od.columns
            if c
            in {
                "n_profiles_used",
                "cum_gain_m",
                "cum_loss_m",
                "n_arcs_on_route",
                "n_missing_profiles",
                "dem_coverage_frac",
                "path_length_m",
                "stitched_length_m",
                "length_error_m",
                "max_abs_grade",
                "continuity_ok",
                "route_method",
                "n_invalid_profiles",
                "n_route_alternatives_profiled",
                "notes",
            }
        ]
        od = od.drop(columns=drop_cols, errors="ignore")
        elev_merge = elev.drop(columns=["in_headline"], errors="ignore")
        od = od.merge(elev_merge, on="od_id", how="left")
        od.to_csv(dt03, index=False)
        if "in_headline" in od.columns:
            od[od["in_headline"]].to_csv(TAB / "D-T03_od_inventory_headline14.csv", index=False)

    # Patch independent recount dem notes
    recount = DS / "independent_recount_summary.json"
    if recount.exists():
        obj = json.loads(recount.read_text(encoding="utf-8"))
        obj["elevation_reconstruction"] = {
            "method": "ordered_decision_arc_along_path_alternative",
            "n_od_methods": int(len(by_method)),
            "mean_abs_length_error_m_shortest": float(
                elev["length_error_m"].abs().mean()
            ),
            "min_dem_coverage_frac_shortest": float(elev["dem_coverage_frac"].min()),
            "n_invalid_profiles": int(len(inv)),
            "n_missing_profiles_on_decision_arcs": int((~cov["profile_exists"]).sum()),
        }
        recount.write_text(json.dumps(obj, indent=2) + "\n", encoding="utf-8")

    fig5.main()
    print("D-T05 rows", len(elev))
    print(elev[["od_id", "path_length_m", "stitched_length_m", "length_error_m", "cum_gain_m", "dem_coverage_frac"]].to_string(index=False))
    print("invalid profiles:\n", inv.to_string(index=False) if len(inv) else "none")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
