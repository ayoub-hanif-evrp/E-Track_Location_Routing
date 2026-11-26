#!/usr/bin/env python3
"""Run robustness variants for one OD into an isolated CSV (safe to parallelize)."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts/final_evidence"))
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import run_remaining_p2_p3 as p2  # noqa: E402
import run_stage_c_hos_national as stage_c  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--od", required=True)
    ap.add_argument("--payload", type=float, required=True)
    ap.add_argument("--soc", type=float, required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    sha = p2._sha()
    out = Path(args.out)
    rows = []
    if out.exists() and out.stat().st_size > 0:
        import pandas as pd

        prev = pd.read_csv(out)
        if {"od_id", "variant", "block", "status"}.issubset(prev.columns):
            rows = prev.to_dict(orient="records")
    done = {(r["od_id"], r["variant"], r["block"]) for r in rows}
    orig = stage_c._patch_realistic_speed_policy()
    try:
        for vname, opts in p2.FRIDGE_VARIANTS:
            key = (args.od, vname, "refrigeration")
            if key in done:
                continue
            rows.append(
                p2._eval_row(args.od, args.payload, args.soc, p2.SITE, vname, opts, sha, "refrigeration")
            )
            done.add(key)
            p2._save_df(out, rows)
        for vname, opts in p2.SENS_VARIANTS:
            key = (args.od, vname, "sensitivity")
            if key in done:
                continue
            rows.append(
                p2._eval_row(args.od, args.payload, args.soc, p2.SITE, vname, opts, sha, "sensitivity")
            )
            done.add(key)
            p2._save_df(out, rows)
        for vname, opts in p2.ADVERSE:
            key = (args.od, vname, "adverse")
            if key in done:
                continue
            rows.append(
                p2._eval_row(args.od, args.payload, args.soc, p2.SITE, vname, opts, sha, "adverse")
            )
            done.add(key)
            p2._save_df(out, rows)
    finally:
        import morocco_etruck.optimization.multiroute_placement_evaluation as mpe

        mpe.load_multiroute_pilot_config = orig
    print(f"DONE od_worker {args.od} rows={len(rows)}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
