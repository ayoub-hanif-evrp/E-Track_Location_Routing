#!/usr/bin/env python
"""Task 04B — Certified placement B&B vs Task 04A enumeration optima."""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from morocco_etruck.optimization.branch_and_bound import (  # noqa: E402
    prepare_placement_context,
    run_branch_and_bound,
)
from morocco_etruck.optimization.morocco_adapter import load_pilot_config  # noqa: E402
from morocco_etruck.optimization.placement_problem import load_placement_config  # noqa: E402
from morocco_etruck.optimization.site_enumeration import run_enumeration  # noqa: E402
from morocco_etruck.optimization.synthetic_placement import (  # noqa: E402
    evaluate_synthetic_subset,
    load_synthetic_placement,
)
from morocco_etruck.optimization.branch_and_bound import (  # noqa: E402
    run_branch_and_bound_core,
)
from morocco_etruck.road_network import load_graph_from_csv  # noqa: E402


def _sites_equal(a: str, b: str) -> bool:
    def norm(s: str) -> set[str]:
        s = (s or "").strip()
        if not s or s.upper() == "NONE":
            return set()
        return {x.strip() for x in s.split(",") if x.strip()}

    return norm(a) == norm(b)


def run_morocco_comparison(args) -> pd.DataFrame:
    cfg = load_placement_config(args.config, root=ROOT)
    morocco_cfg = load_pilot_config(cfg.morocco_pilot_path)
    print("Loading road graph…", flush=True)
    G = load_graph_from_csv(ROOT / morocco_cfg["nodes_csv"], ROOT / morocco_cfg["edges_csv"])

    demands = args.demand or list(cfg.demand_scenarios.keys())
    capexes = args.capex or list(cfg.capex_scenarios.keys())
    prices = args.price or list(cfg.price_modes)

    # Optional: refresh enumeration optima for fair labels/comparison
    enum_opt_rows: list[dict] = []
    enum_t0 = time.perf_counter()
    if args.refresh_enumeration:
        for demand in demands:
            for capex in capexes:
                for price in prices:
                    print(f"Enumerate demand={demand} capex={capex} price={price}", flush=True)
                    res = run_enumeration(
                        cfg,
                        root=ROOT,
                        demand_name=demand,
                        capex_name=capex,
                        price_mode=price,
                        G=G,
                    )
                    enum_opt_rows.extend(res.optimal_rows)
        enum_df = pd.DataFrame(enum_opt_rows)
        out_opt = ROOT / cfg.outputs.get("optimal_csv", "results/location_optimal_solutions.csv")
        out_opt.parent.mkdir(parents=True, exist_ok=True)
        enum_df.to_csv(out_opt, index=False)
        print(f"Refreshed enumeration optima → {out_opt}", flush=True)
    else:
        enum_path = ROOT / cfg.outputs.get("optimal_csv", "results/location_optimal_solutions.csv")
        enum_df = pd.read_csv(enum_path)
    enum_prep_sec = time.perf_counter() - enum_t0

    rows: list[dict] = []
    for demand in demands:
        print(f"Preparing context demand={demand}…", flush=True)
        ctx = prepare_placement_context(cfg, root=ROOT, demand_name=demand, G=G)
        for capex in capexes:
            for price in prices:
                # Fresh memo per price mode (prices affect MRLS objectives)
                from morocco_etruck.optimization.placement_cache import PlacementMemo

                ctx["memo"] = PlacementMemo(
                    energy_model_fingerprint=ctx["memo"].energy_model_fingerprint
                )
                for bud in cfg.budgets:
                    bname = bud["name"]
                    print(
                        f"B&B demand={demand} capex={capex} price={price} budget={bname}",
                        flush=True,
                    )
                    t0 = time.perf_counter()
                    bb = run_branch_and_bound(
                        cfg,
                        root=ROOT,
                        demand_name=demand,
                        capex_name=capex,
                        price_mode=price,
                        budget_name=bname,
                        G=G,
                        context=ctx,
                    )
                    runtime = time.perf_counter() - t0
                    bb_row = bb.rows[0] if bb.rows else {}
                    ref = enum_df[
                        (enum_df["demand_scenario"] == demand)
                        & (enum_df["capex_scenario"] == capex)
                        & (enum_df["price_mode"] == price)
                        & (enum_df["budget_name"] == bname)
                    ]
                    if len(ref) != 1:
                        match = False
                        cov_ok = False
                        cost_ok = False
                        sites_ok = False
                        ref_sites = ""
                        ref_cov = None
                        ref_sec = None
                        ref_status = ""
                    else:
                        r = ref.iloc[0]
                        ref_sites = str(r.get("best_sites", ""))
                        ref_cov = float(r["coverage_serviceable"])
                        ref_sec = float(r["secondary_cost"])
                        ref_status = str(r.get("optimality_status", ""))
                        bb_sites = str(bb_row.get("best_sites", ""))
                        bb_cov = float(bb_row.get("coverage_serviceable", -1))
                        bb_sec = float(bb_row.get("secondary_cost", -1))
                        sites_ok = _sites_equal(bb_sites, ref_sites)
                        cov_ok = abs(bb_cov - ref_cov) < 1e-9
                        cost_ok = abs(bb_sec - ref_sec) < 1e-6
                        # Equal alternate optima: same cov+cost, possibly different sites
                        alternate_optima = bool(cov_ok and cost_ok and not sites_ok)
                        match = bool((sites_ok and cov_ok and cost_ok) or alternate_optima)
                    rows.append(
                        {
                            "demand_scenario": demand,
                            "capex_scenario": capex,
                            "price_mode": price,
                            "budget_name": bname,
                            "bb_sites": bb_row.get("best_sites", ""),
                            "enum_sites": ref_sites,
                            "bb_coverage": bb_row.get("coverage_serviceable"),
                            "enum_coverage": ref_cov,
                            "bb_secondary": bb_row.get("secondary_cost"),
                            "enum_secondary": ref_sec,
                            "bb_status": bb.optimality_status.value,
                            "enum_status": ref_status,
                            "match": match,
                            "sites_equal": sites_ok,
                            "alternate_optima": alternate_optima if len(ref) == 1 else False,
                            "coverage_equal": cov_ok,
                            "secondary_equal": cost_ok,
                            "nodes_visited": bb.stats.nodes_visited,
                            "nodes_expanded": bb.stats.nodes_expanded,
                            "leaves_evaluated": bb.stats.leaves_evaluated,
                            "prune_budget": bb.stats.prune_budget,
                            "prune_coverage": bb.stats.prune_coverage,
                            "prune_secondary": bb.stats.prune_secondary,
                            "mrls_calls": bb.stats.mrls_calls,
                            "mrls_cache_hits": bb.stats.mrls_cache_hits,
                            "runtime_sec": runtime,
                            "enum_refresh_sec": enum_prep_sec if args.refresh_enumeration else None,
                            "structural_ids": bb_row.get("structural_ids", ""),
                        }
                    )
                    print(
                        f"  status={bb.optimality_status.value} match={match} "
                        f"visited={bb.stats.nodes_visited} prune_c={bb.stats.prune_coverage} "
                        f"prune_s={bb.stats.prune_secondary} t={runtime:.1f}s",
                        flush=True,
                    )
    return pd.DataFrame(rows)


def run_synthetic_demo(args) -> pd.DataFrame:
    path = ROOT / args.synthetic_config
    problem = load_synthetic_placement(path)
    print(f"Synthetic placement: {len(problem.sites)} sites — {problem.note}", flush=True)
    out_rows = []
    for bud in problem.budgets:
        bname = bud["name"]
        max_c = bud.get("max_capex")
        print(f"Synthetic B&B budget={bname} max_capex={max_c}", flush=True)

        def evaluate_fn(installed: set[str]):
            return evaluate_synthetic_subset(
                installed, problem, max_capex=None if max_c is None else float(max_c)
            )

        t0 = time.perf_counter()
        res = run_branch_and_bound_core(
            site_ids=[s.id for s in problem.sites],
            capex=problem.capex,
            max_capex=None if max_c is None else float(max_c),
            crf=problem.crf,
            evaluate_fn=evaluate_fn,
        )
        runtime = time.perf_counter() - t0

        # Exhaustive reference for this budget (still feasible at n=12)
        from morocco_etruck.optimization.site_enumeration import all_subsets

        best = None
        for subset in all_subsets([s.id for s in problem.sites]):
            ev = evaluate_fn(set(subset))
            if max_c is not None and ev.infra_capex > float(max_c) + 1e-9:
                continue
            if not ev.certified:
                continue
            if best is None or (
                ev.coverage_serviceable > best.coverage_serviceable + 1e-12
                or (
                    abs(ev.coverage_serviceable - best.coverage_serviceable) < 1e-12
                    and ev.secondary_cost < best.secondary_cost - 1e-12
                )
            ):
                best = ev

        match = (
            res.incumbent is not None
            and best is not None
            and abs(res.incumbent.coverage_serviceable - best.coverage_serviceable) < 1e-9
            and abs(res.incumbent.secondary_cost - best.secondary_cost) < 1e-6
        )
        out_rows.append(
            {
                "kind": "synthetic",
                "budget_name": bname,
                "max_capex": max_c,
                "n_sites": len(problem.sites),
                "bb_sites": ",".join(sorted(res.incumbent.site_ids)) if res.incumbent else "",
                "enum_sites": ",".join(sorted(best.site_ids)) if best else "",
                "bb_coverage": res.incumbent.coverage_serviceable if res.incumbent else None,
                "enum_coverage": best.coverage_serviceable if best else None,
                "bb_secondary": res.incumbent.secondary_cost if res.incumbent else None,
                "enum_secondary": best.secondary_cost if best else None,
                "bb_status": res.optimality_status.value,
                "match": match,
                "nodes_visited": res.stats.nodes_visited,
                "nodes_expanded": res.stats.nodes_expanded,
                "leaves_evaluated": res.stats.leaves_evaluated,
                "prune_budget": res.stats.prune_budget,
                "prune_coverage": res.stats.prune_coverage,
                "prune_secondary": res.stats.prune_secondary,
                "runtime_sec": runtime,
                "proved_prunes": res.stats.prune_budget
                + res.stats.prune_coverage
                + res.stats.prune_secondary,
            }
        )
        print(
            f"  status={res.optimality_status.value} match={match} "
            f"prunes={out_rows[-1]['proved_prunes']} visited={res.stats.nodes_visited} "
            f"t={runtime:.1f}s",
            flush=True,
        )
    return pd.DataFrame(out_rows)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--config",
        type=Path,
        default=ROOT / "configs/optimization/placement_pilot.yaml",
    )
    p.add_argument(
        "--synthetic-config",
        type=Path,
        default=ROOT / "configs/optimization/branch_bound_benchmarks.yaml",
    )
    p.add_argument("--demand", action="append", default=None)
    p.add_argument("--capex", action="append", default=None)
    p.add_argument("--price", action="append", default=None)
    p.add_argument(
        "--refresh-enumeration",
        action="store_true",
        help="Re-run Task 04A enumeration before comparison (fair timing includes prep)",
    )
    p.add_argument("--skip-morocco", action="store_true")
    p.add_argument("--skip-synthetic", action="store_true")
    p.add_argument(
        "--out",
        type=Path,
        default=ROOT / "results/branch_bound_comparison.csv",
    )
    args = p.parse_args()

    frames = []
    if not args.skip_morocco:
        frames.append(run_morocco_comparison(args))
    if not args.skip_synthetic:
        frames.append(run_synthetic_demo(args))
    if not frames:
        print("Nothing to run", flush=True)
        return 1
    df = pd.concat(frames, ignore_index=True, sort=False)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(args.out, index=False)
    print(f"Wrote {args.out} ({len(df)} rows)", flush=True)
    if "match" in df.columns:
        n = int(df["match"].fillna(False).sum())
        print(f"Matches: {n}/{len(df)}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
