#!/usr/bin/env python3
"""P4 — Investigate D-T05 continuity_ok=False and steep reconstructed grades."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts/final_evidence"))
from elevation_profiles import reconstruct_od_elevation  # noqa: E402

FE = ROOT / "results/final_evidence"
OUT = FE / "dataset"


def main() -> int:
    elev = pd.read_csv(FE / "tables/dataset/D-T05_elevation_by_mission.csv")
    method_col = next(
        (c for c in ("route_method", "method", "path_method") if c in elev.columns),
        None,
    )
    if method_col is None:
        short = elev.copy()
    else:
        short = elev[
            elev[method_col].astype(str).str.contains("shortest", case=False, na=False)
        ].copy()
        if not len(short):
            short = elev.copy()
    rows = []
    for _, r in short.iterrows():
        od = str(r.od_id)
        method = str(r[method_col]) if method_col else "shortest_distance"
        prof = reconstruct_od_elevation(od, method=method)
        jump_notes = [n for n in prof.notes if n.startswith("elevation_jump_")]
        steep = [n for n in prof.notes if n.startswith("steep_grade_")]
        # Classify likely origin of issues
        if jump_notes and float(prof.max_abs_grade or 0) > 0.20:
            origin = "junction_discontinuity_and_or_within_arc_steep_grade"
        elif jump_notes:
            origin = "junction_discontinuity_dem_tile_or_sampling"
        elif steep:
            origin = "within_arc_steep_grade_review_dem_resolution_or_genuine_grade"
        elif not prof.continuity_ok:
            origin = "continuity_flag_without_jump_note"
        else:
            origin = "ok"
        rows.append(
            {
                "od_id": od,
                "method": method,
                "continuity_ok": prof.continuity_ok,
                "max_abs_grade": prof.max_abs_grade,
                "cum_gain_m": prof.cum_gain_m,
                "cum_loss_m": prof.cum_loss_m,
                "n_junction_jumps": len(jump_notes),
                "n_steep_grade_arcs": len(steep),
                "dem_coverage_frac": prof.dem_coverage_frac,
                "length_error_m": prof.length_error_m,
                "origin_hypothesis": origin,
                "notes": ";".join(prof.notes[:12]),
            }
        )
        # write updated row values back conceptually via regenerating table later
    inv = pd.DataFrame(rows)
    inv.to_csv(OUT / "elevation_continuity_grade_investigation.csv", index=False)

    md = [
        "# Elevation continuity and steep-grade investigation",
        "",
        "Gain, loss and maximum gradient are computed **within each decision arc**.",
        "Artificial junction elevation jumps (>5 m) are recorded for continuity diagnostics",
        "but are **excluded** from gain/loss/max-grade statistics.",
        "",
        "Missing DEM segments are not bridged with invented elevations; distance advances",
        "by arc length and continuity is broken across the gap.",
        "",
        "Steep within-arc grades (>20%) may reflect genuine geography, DEM resolution,",
        "or sampling densification — they are not silently clipped.",
        "",
        f"Shortest-route rows with continuity_ok=False: "
        f"**{int((inv.continuity_ok == False).sum())}** / {len(inv)}.",  # noqa: E712
        "",
        "## Origin summary",
        "",
        inv.groupby("origin_hypothesis").size().to_string(),
        "",
        "## Rows",
        "",
        inv.sort_values(["continuity_ok", "max_abs_grade"], ascending=[True, False]).to_string(
            index=False
        ),
        "",
    ]
    (OUT / "elevation_continuity_grade_notes.md").write_text("\n".join(md), encoding="utf-8")
    print(inv.to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
