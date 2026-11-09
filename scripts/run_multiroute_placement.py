#!/usr/bin/env python
"""Task 05C — Joint multi-route placement: exhaustive enum vs B&B."""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from morocco_etruck.optimization.multiroute_placement import (  # noqa: E402
    load_multiroute_placement_config,
)
from morocco_etruck.optimization.multiroute_placement_evaluation import (  # noqa: E402
    prepare_multiroute_placement_context,
    run_multiroute_branch_and_bound,
    run_multiroute_enumeration,
)
from morocco_etruck.optimization.placement_certification import OptimalityStatus  # noqa: E402


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--config",
        type=Path,
        default=ROOT / "configs/optimization/multiroute_placement_pilot.yaml",
    )
    p.add_argument("--demand", default="default")
    p.add_argument("--capex", default="equal")
    args = p.parse_args()

    cfg = load_multiroute_placement_config(args.config, root=ROOT)
    print(cfg.disclaimer.strip()[:240], "...", flush=True)

    t_prep = time.perf_counter()
    context = prepare_multiroute_placement_context(
        cfg, root=ROOT, demand_name=args.demand
    )
    prep_s = time.perf_counter() - t_prep
    print(
        f"Prepared {len(context['missions'])} missions in {prep_s:.1f}s; "
        f"serviceability={context['serviceability']}",
        flush=True,
    )

    enum_rows: list[dict] = []
    bb_rows: list[dict] = []
    for bud in cfg.budgets:
        bname = str(bud["name"])
        print(f"\n=== Budget {bname} (max_capex={bud.get('max_capex')}) ===", flush=True)
        t0 = time.perf_counter()
        rows, best, context = run_multiroute_enumeration(
            cfg,
            root=ROOT,
            demand_name=args.demand,
            capex_name=args.capex,
            budget_name=bname,
            context=context,
        )
        enum_s = time.perf_counter() - t0
        for r in rows:
            r["prep_sec"] = prep_s
            r["solve_sec"] = enum_s
        enum_rows.extend(rows)
        best_sites = ",".join(sorted(best.site_ids)) if best else ""
        print(
            f"Enumeration: {len(rows)} feasible subsets; "
            f"best={best_sites or 'NONE'} "
            f"cov={None if best is None else best.coverage_serviceable} "
            f"sec={None if best is None else best.secondary_cost:.4f} "
            f"({enum_s:.1f}s)",
            flush=True,
        )

        t1 = time.perf_counter()
        bb, context = run_multiroute_branch_and_bound(
            cfg,
            root=ROOT,
            demand_name=args.demand,
            capex_name=args.capex,
            budget_name=bname,
            context=context,
        )
        bb_s = time.perf_counter() - t1
        inc = bb.incumbent
        agree = False
        if best is not None and inc is not None:
            agree = (
                abs(best.coverage_serviceable - inc.coverage_serviceable) <= 1e-9
                and abs(best.secondary_cost - inc.secondary_cost) <= 1e-6
            )
        elif best is None and inc is None:
            agree = True
        bb_rows.append(
            {
                "method": "branch_and_bound",
                "demand_scenario": args.demand,
                "capex_scenario": args.capex,
                "budget_name": bname,
                "max_capex": bud.get("max_capex"),
                "best_sites": ",".join(sorted(inc.site_ids)) if inc else "",
                "n_sites": 0 if inc is None else len(inc.site_ids),
                "coverage_serviceable": None if inc is None else inc.coverage_serviceable,
                "coverage_total": None if inc is None else inc.coverage_total,
                "infra_capex": None if inc is None else inc.infra_capex,
                "infra_annual": None if inc is None else inc.infra_annual,
                "variable_cost": None if inc is None else inc.variable_cost,
                "secondary_cost": None if inc is None else inc.secondary_cost,
                "optimality_status": bb.optimality_status.value,
                "certified": bb.optimality_status == OptimalityStatus.CERTIFIED_OPTIMAL,
                "enum_agreement": agree,
                "enum_best_sites": best_sites,
                "nodes_visited": bb.stats.nodes_visited,
                "nodes_expanded": bb.stats.nodes_expanded,
                "leaves_evaluated": bb.stats.leaves_evaluated,
                "prune_budget": bb.stats.prune_budget,
                "prune_coverage": bb.stats.prune_coverage,
                "prune_secondary": bb.stats.prune_secondary,
                "mrls_cache_hits": bb.stats.mrls_cache_hits,
                "prep_sec": prep_s,
                "solve_sec": bb_s,
                "serviceability_json": str(context["serviceability"]),
                "mission_detail": ""
                if inc is None
                else ";".join(
                    f"{m.mission_id}:{m.status}:served={int(m.served)}:chg={m.charges}"
                    for m in inc.missions
                ),
            }
        )
        print(
            f"B&B: status={bb.optimality_status.value} "
            f"best={bb_rows[-1]['best_sites'] or 'NONE'} "
            f"agree_enum={agree} "
            f"nodes={bb.stats.nodes_visited} "
            f"prunes=B{bb.stats.prune_budget}/C{bb.stats.prune_coverage}/S{bb.stats.prune_secondary} "
            f"({bb_s:.1f}s)",
            flush=True,
        )

    out_enum = ROOT / cfg.outputs.get(
        "enumeration_csv", "results/multiroute_placement_enumeration.csv"
    )
    out_bb = ROOT / cfg.outputs.get(
        "branch_bound_csv", "results/multiroute_placement_branch_bound.csv"
    )
    out_enum.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(enum_rows).to_csv(out_enum, index=False)
    pd.DataFrame(bb_rows).to_csv(out_bb, index=False)
    print(f"\nWrote {out_enum} ({len(enum_rows)} rows)", flush=True)
    print(f"Wrote {out_bb} ({len(bb_rows)} rows)", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
