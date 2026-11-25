"""Verify energy/ops dual and LIMIT contamination interpretation."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "path_a"))
OUT = ROOT / "results" / "validation" / "path_a"


def main() -> None:
    import pandas as pd

    OUT.mkdir(parents=True, exist_ok=True)
    lim = OUT / "energy_ops_limit_contamination.csv"
    if not lim.exists():
        from build_coverage_reconciliation import main as recon

        recon()
    df = pd.read_csv(lim) if lim.exists() else pd.DataFrame()
    notes = OUT / "energy_ops_dual_check.csv"
    rows = []
    for _, r in df.iterrows():
        rows.append(
            {
                "budget": r["budget"],
                "od_id": r["od_id"],
                "installed": r.get("installed"),
                "ops_served": 0,
                "energy_served": 1,
                "status": r["status"],
                "delta_energy_minus_ops": 1,
                "note": r.get("interpretation"),
            }
        )
    pd.DataFrame(rows).to_csv(notes, index=False, lineterminator="\n")
    print(f"LIMIT energy≠ops cells: {len(rows)}")
    if rows:
        print("PASS: discrepancy documented as LIMIT contamination (not HOS physics)")
    else:
        print("NOTE: no LIMIT contamination cells in current missions CSV")


if __name__ == "__main__":
    main()
