#!/usr/bin/env python
"""P0.4 — Re-run 8-site synthetic shared-road B&B after budget-relaxed cert fix."""

from __future__ import annotations

import csv
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

# Reuse Task 08 synthetic shared-road builder
sys.path.insert(0, str(ROOT / "scripts"))
from run_task08_final_validation import (  # noqa: E402
    build_shared_road_problem,
    run_shared_road_benchmark,
)

OUT_CSV = ROOT / "results/bb_relaxed_bound_before_after.csv"
OUT_MD = ROOT / "reports/bb_relaxed_bound_certification.md"
HIST = ROOT / "results/task08_algorithm_benchmarks_historical_8site.csv"


def main() -> int:
    t0 = time.perf_counter()
    rows = run_shared_road_benchmark()
    sec = time.perf_counter() - t0
    # Annotate certification semantics
    out_rows = []
    for r in rows:
        r = dict(r)
        r["cert_semantics"] = (
            "routing_certified_independent_of_budget;"
            "incumbent_requires_budget_ok;"
            "coverage_UB_may_use_overbudget_superset_if_routing_certified"
        )
        r["benchmark_sec_wall"] = sec
        out_rows.append(r)

    # Historical comparison if available
    hist_rows = []
    if HIST.exists():
        import pandas as pd

        hist = pd.read_csv(HIST)
        for _, h in hist.iterrows():
            hist_rows.append(
                {
                    "phase": "before_HISTORICAL_task08",
                    "budget": h.get("budget_name") or h.get("budget"),
                    "method": h.get("method"),
                    "nodes": h.get("nodes_visited") or h.get("bb_nodes"),
                    "coverage_prunes": h.get("prune_coverage"),
                    "mrls_calls": h.get("mrls_calls") or h.get("n_mrls"),
                    "sec": h.get("sec") or h.get("runtime_s"),
                    "agree": h.get("enum_bb_agree") or h.get("objective_agreement"),
                }
            )

    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    keys = []
    seen = set()
    for r in out_rows:
        for k in r:
            if k not in seen:
                seen.add(k)
                keys.append(k)
    with OUT_CSV.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=keys, extrasaction="ignore")
        w.writeheader()
        for r in out_rows:
            w.writerow(
                {
                    k: json.dumps(v) if isinstance(v, (dict, list, set)) else v
                    for k, v in r.items()
                }
            )

    lines = [
        "# B&B budget-relaxed bound certification",
        "",
        "## Defect",
        "",
        "`evaluate_multiroute_subset` previously set "
        "`certified = budget_ok and routing_ok`. Coverage upper bounds evaluate "
        "`installed ∪ undecided` while relaxing the budget; an over-budget but "
        "routing-resolved superset was marked uncertified, blocking safe pruning.",
        "",
        "## Correction",
        "",
        "- `certified` := all mission evaluations routing-resolved (not uncertified).",
        "- `budget_ok` remains separate.",
        "- Incumbents require `certified and budget_ok` (`_lex_better`).",
        "- Leaves still reject over-budget CAPEX via explicit infra check.",
        "- LIMIT_REACHED / invalid replay still cannot certify bounds or global optimality.",
        "",
        "Monotonicity assumption unchanged: independent missions, optional sites, "
        "no shared charger capacity (see `placement_bounds.py`).",
        "",
        "## Synthetic shared-road 8-site benchmark (after fix)",
        "",
        "| Budget / row | Key fields |",
        "| --- | --- |",
    ]
    for r in out_rows[:12]:
        cache = r.get("cache_mode", "")
        lines.append(
            f"| {r.get('budget_name')}/{cache} | "
            f"agree={r.get('objective_agreement')} "
            f"opt={r.get('optimality_status')} "
            f"nodes={r.get('bb_nodes_visited')} "
            f"prune_cov={r.get('bb_prunes_coverage')} "
            f"mrls={r.get('bb_mrls_calls')} "
            f"bb_sec={r.get('bb_sec')} "
            f"faster={r.get('faster_method')} |"
        )
    lines.extend(
        [
            "",
            "Do **not** claim B&B is generally faster than enumeration. Report observed "
            "nodes/prunes/runtime honestly.",
            "",
            "## Reproduction",
            "",
            "```bash",
            "python scripts/run_bb_relaxed_bound_benchmark.py",
            "pytest -q tests/unit/test_branch_and_bound.py",
            "```",
            "",
            f"CSV: `{OUT_CSV.relative_to(ROOT).as_posix()}`",
            "",
        ]
    )
    OUT_MD.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote {OUT_CSV} ({len(out_rows)} rows) in {sec:.1f}s")
    print(f"Wrote {OUT_MD}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
