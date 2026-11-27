#!/usr/bin/env python3
"""Rebuild R-T09 pairwise tables from dem_vs_flat_missions.csv without re-solving."""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts/final_evidence"))
from run_dem_vs_flat import _pairwise, _trace_metrics  # noqa: E402

OUT = ROOT / "results/final_evidence/experiments/dem_vs_flat"
TAB = ROOT / "results/final_evidence/tables/results"


def main() -> int:
    src = OUT / "dem_vs_flat_missions.csv"
    df = pd.read_csv(src)
    # Recompute energy metrics with corrected null handling
    rows = []
    for _, r in df.iterrows():
        d = r.to_dict()
        # Prefer existing action_trace_json; recompute metrics
        metrics = _trace_metrics(d)
        d.update(metrics)
        rows.append(d)
    fixed = pd.DataFrame(rows)
    fixed.to_csv(src, index=False)

    fixed_pw = _pairwise(fixed, "fixed_short")
    reopt_pw = _pairwise(fixed, "reoptimized_multi")
    both = pd.concat([fixed_pw, reopt_pw], ignore_index=True)
    both.to_csv(TAB / "R-T09_dem_vs_flat.csv", index=False)
    fixed_pw.to_csv(TAB / "R-T09_dem_vs_flat_fixed_route.csv", index=False)
    reopt_pw.to_csv(TAB / "R-T09_dem_vs_flat_reoptimized.csv", index=False)

    # Highlight Casa–Marrakech 50% fixed-route three-way finding
    cm = both[(both.od_id == "casa_marrakech") & (both.soc_frac == 0.5)]
    note = OUT / "dem_vs_flat_interpretation.md"
    lines = [
        "# DEM vs flat interpretation notes",
        "",
        "## Comparison families",
        "",
        "1. `fixed_short`: identical shortest-path mask; terrain-only effect when both traces exist.",
        "2. `reoptimized_multi`: multi-route union; routing/charging may change with terrain.",
        "",
        "Infeasible solutions without an OPTIMAL action trace use missing energy values",
        "(not zeros). Feasibility differences are reported separately from energy deltas.",
        "",
        "## Casa–Marrakech @ 50% SOC (authoritative three-outcome contrast)",
        "",
    ]
    if len(cm):
        lines.append(cm.to_string(index=False))
        lines.extend(
            [
                "",
                "Scientific reading (fixed route):",
                "- Flat-road fixed route: feasible without charging (when ops_flat True / trace present).",
                "- DEM-aware fixed route: infeasible (no OPTIMAL trace ⇒ no zero-energy claim).",
                "- DEM-aware flexible/reoptimized route: may restore feasibility via Benguerir charging",
                "  and/or route selection — see reoptimized family rows.",
                "",
            ]
        )
    note.write_text("\n".join(lines), encoding="utf-8")
    print(both.to_string(index=False))
    print("Rebuilt R-T09 from", src)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
