#!/usr/bin/env python
"""PASS 2B — targeted certification-aware q refinement diagnostic (not a theorem).

Compares fixed q=10, fixed q=5, and refine-if-coarse-INFEASIBLE on:
  (1) Northbound Case A (PASS 2A) — expected physical peak-motor dominated
  (2) Historical southbound CM H80-like counterexample (Task 08 diagnosis)

Reports whether *infrastructure decisions* (min sites / best sites) change.
Does NOT claim continuous optimality or novelty beyond a diagnostic wrapper.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from morocco_etruck.optimization.multiroute_placement import (  # noqa: E402
    load_multiroute_placement_config,
)
from morocco_etruck.optimization.multiroute_placement_evaluation import (  # noqa: E402
    all_optimal_site_sets,
    evaluate_multiroute_mission,
    prepare_multiroute_placement_context,
    run_multiroute_enumeration,
)

ROAD = 100.0


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:16]


def _min_sites_for_max_coverage(enum_rows: list[dict]) -> dict[str, Any]:
    feas = [r for r in enum_rows if r.get("budget_ok") and r.get("certified")]
    if not feas:
        return {
            "max_coverage": 0.0,
            "min_sites": None,
            "best_sites": "",
            "n_served_label": "none",
        }
    best_cov = max(float(r["coverage_serviceable"]) for r in feas)
    at = [r for r in feas if abs(float(r["coverage_serviceable"]) - best_cov) <= 1e-9]
    # prefer fewer sites among max coverage
    at.sort(key=lambda r: (int(r["n_sites"]), float(r["secondary_cost"])))
    best = at[0]
    return {
        "max_coverage": best_cov,
        "min_sites": int(best["n_sites"]),
        "best_sites": str(best["sites"]),
        "n_served_label": "served" if best_cov > 1e-12 else "unserved",
    }


def _eval_mission_q(
    *,
    cfg,
    demand: str,
    vpath: Path,
    fridge: Path,
    q: int,
    installed: set[str],
    max_alts: int = 2,
) -> dict[str, Any]:
    t0 = time.perf_counter()
    ctx = prepare_multiroute_placement_context(
        cfg,
        root=ROOT,
        demand_name=demand,
        energy_quantum_kwh=q,
        objective_mode="enroute_incremental_cost",
        vehicle_yaml=vpath,
        road_cost_per_km=ROAD,
        fridge_yaml=fridge,
        charger_power_kw=350.0,
        max_alternatives_for_union=max_alts,
    )
    prep = next(iter(ctx["prepared"].values()))
    r = evaluate_multiroute_mission(
        prep,
        installed=installed,
        sites=cfg.sites,
        max_seconds=60.0,
        max_expansions=100_000,
    )
    return {
        "q": q,
        "dem_complete": bool(prep.ctx.dem_complete),
        "status": r.status,
        "served": bool(r.served),
        "uncertified": bool(r.uncertified),
        "discrete_replay_ok": bool(r.discrete_replay_ok),
        "continuous_replay_ok": bool(r.continuous_replay_ok),
        "sec": time.perf_counter() - t0,
        "context": ctx,
    }


def _placement_at_q(
    *,
    cfg,
    demand: str,
    vpath: Path,
    fridge: Path,
    q: int,
    budget: str = "Ball",
) -> dict[str, Any]:
    t0 = time.perf_counter()
    ctx = prepare_multiroute_placement_context(
        cfg,
        root=ROOT,
        demand_name=demand,
        energy_quantum_kwh=q,
        objective_mode="enroute_incremental_cost",
        vehicle_yaml=vpath,
        road_cost_per_km=ROAD,
        fridge_yaml=fridge,
        charger_power_kw=350.0,
        max_alternatives_for_union=2,
    )
    if not next(iter(ctx["prepared"].values())).ctx.dem_complete:
        return {
            "q": q,
            "status": "DEM_INCOMPLETE",
            "max_coverage": None,
            "min_sites": None,
            "best_sites": "",
            "sec": time.perf_counter() - t0,
            "mrls_calls_proxy": None,
        }
    rows, best, _ = run_multiroute_enumeration(
        cfg,
        root=ROOT,
        demand_name=demand,
        capex_name="equal",
        budget_name=budget,
        context=ctx,
    )
    summary = _min_sites_for_max_coverage(rows)
    return {
        "q": q,
        "status": "OK",
        "max_coverage": summary["max_coverage"],
        "min_sites": summary["min_sites"],
        "best_sites": summary["best_sites"],
        "opt_sets": "|".join(all_optimal_site_sets(rows)),
        "n_subsets": len(rows),
        "sec": time.perf_counter() - t0,
        "incumbent_cov": None if best is None else best.coverage_serviceable,
    }


def refine_protocol(
    *,
    cfg,
    demand: str,
    vpath: Path,
    fridge: Path,
    coarse_q: int = 10,
    fine_q: int = 5,
) -> dict[str, Any]:
    """Smallest justified diagnostic: if Ball coarse is INFEASIBLE, re-eval at fine q."""
    t0 = time.perf_counter()
    all_ids = {s.id for s in cfg.sites}
    coarse = _eval_mission_q(
        cfg=cfg,
        demand=demand,
        vpath=vpath,
        fridge=fridge,
        q=coarse_q,
        installed=all_ids,
    )
    mrls = 1
    used_fine = False
    final = coarse
    if coarse["status"] == "INFEASIBLE" and not coarse["served"]:
        fine = _eval_mission_q(
            cfg=cfg,
            demand=demand,
            vpath=vpath,
            fridge=fridge,
            q=fine_q,
            installed=all_ids,
        )
        mrls += 1
        used_fine = True
        final = fine
        false_neg = bool(fine["served"])
    else:
        false_neg = False
    # Placement decision under refinement: use fine grid only if coarse Ball IF
    place_q = fine_q if used_fine else coarse_q
    place = _placement_at_q(
        cfg=cfg, demand=demand, vpath=vpath, fridge=fridge, q=place_q
    )
    return {
        "protocol": "refine_if_coarse_ball_infeasible",
        "coarse_q": coarse_q,
        "fine_q": fine_q,
        "coarse_ball_status": coarse["status"],
        "coarse_ball_served": coarse["served"],
        "fine_used": used_fine,
        "final_ball_status": final["status"],
        "final_ball_served": final["served"],
        "discrete_false_negative_feasibility": false_neg,
        "place_q_used": place_q,
        "place_max_coverage": place.get("max_coverage"),
        "place_min_sites": place.get("min_sites"),
        "place_best_sites": place.get("best_sites"),
        "mrls_mission_evals": mrls,
        "sec": time.perf_counter() - t0,
        "dem_complete": coarse["dem_complete"],
    }


def run_scenario(name: str, cfg_path: Path, demand: str, vpath: Path, fridge: Path) -> list[dict]:
    cfg = load_multiroute_placement_config(cfg_path, root=ROOT)
    rows: list[dict] = []
    print(f"\n=== PASS2B scenario={name} demand={demand} ===", flush=True)

    for q in (10, 5):
        # Ball mission probe
        all_ids = {s.id for s in cfg.sites}
        m = _eval_mission_q(
            cfg=cfg, demand=demand, vpath=vpath, fridge=fridge, q=q, installed=all_ids
        )
        p = _placement_at_q(cfg=cfg, demand=demand, vpath=vpath, fridge=fridge, q=q)
        rows.append(
            {
                "scenario": name,
                "method": f"fixed_q{q}",
                "demand": demand,
                "ball_status": m["status"],
                "ball_served": m["served"],
                "ball_disc_replay": m["discrete_replay_ok"],
                "ball_cont_replay": m["continuous_replay_ok"],
                "place_max_coverage": p.get("max_coverage"),
                "place_min_sites": p.get("min_sites"),
                "place_best_sites": p.get("best_sites"),
                "place_opt_sets": p.get("opt_sets"),
                "sec": m["sec"] + float(p.get("sec") or 0),
                "dem_complete": m["dem_complete"],
            }
        )
        print(
            f"  fixed q={q}: ball={m['status']} served={m['served']} "
            f"min_sites={p.get('min_sites')} cov={p.get('max_coverage')}",
            flush=True,
        )

    ref = refine_protocol(cfg=cfg, demand=demand, vpath=vpath, fridge=fridge)
    rows.append(
        {
            "scenario": name,
            "method": "targeted_refinement",
            "demand": demand,
            "ball_status": ref["final_ball_status"],
            "ball_served": ref["final_ball_served"],
            "ball_disc_replay": None,
            "ball_cont_replay": None,
            "place_max_coverage": ref["place_max_coverage"],
            "place_min_sites": ref["place_min_sites"],
            "place_best_sites": ref["place_best_sites"],
            "place_opt_sets": None,
            "discrete_false_negative_feasibility": ref[
                "discrete_false_negative_feasibility"
            ],
            "fine_used": ref["fine_used"],
            "mrls_mission_evals": ref["mrls_mission_evals"],
            "sec": ref["sec"],
            "dem_complete": ref["dem_complete"],
        }
    )
    print(
        f"  refine: false_neg={ref['discrete_false_negative_feasibility']} "
        f"min_sites={ref['place_min_sites']} fine_used={ref['fine_used']}",
        flush=True,
    )
    return rows


def write_report(df: pd.DataFrame) -> None:
    # Decision change detection
    lines = [
        "# PASS 2B — Discretization novelty result",
        "",
        "## Prior art (brief)",
        "",
        "- Vidotte Plaza et al. (2026) TR-C 105598: charger location + routing + HOS.",
        "- Layered SoC / discretized battery-energy graphs (e.g. 2024 Networks-type EVSPP).",
        "- Two-stage stochastic charging location-routing (e.g. 2026 Applied Energy family).",
        "",
        "Therefore: retrying MRLS at q=5 after q=10 fails is **not** by itself a top-tier "
        "new optimization method. This PASS tests only a **diagnostic wrapper** that asks "
        "whether infrastructure decisions depend on coarse-grid false infeasibility.",
        "",
        "## Protocol",
        "",
        "A. Fixed q=10  B. Fixed q=5  C. Refine Ball evaluation to q=5 iff q=10 Ball is INFEASIBLE.",
        "",
        "No continuous-optimality certificate is claimed.",
        "",
        "## Results",
        "",
        "| Scenario | Method | Ball status | Served | Min sites (Ball) | Best sites | False-neg? |",
        "| --- | --- | --- | --- | ---: | --- | --- |",
    ]
    for _, r in df.iterrows():
        lines.append(
            f"| {r.scenario} | {r.method} | {r.ball_status} | {r.ball_served} | "
            f"{r.place_min_sites} | {r.place_best_sites} | "
            f"{r.get('discrete_false_negative_feasibility', '')} |"
        )

    # Novelty verdict — keep coverage vs site-decision fields DISTINCT
    false_negs = df[
        (df.method == "targeted_refinement")
        & (df.get("discrete_false_negative_feasibility") == True)  # noqa: E712
    ]
    field_rows = []
    for scen in df.scenario.unique():
        sub = df[df.scenario == scen]
        a = sub[sub.method == "fixed_q10"]
        b = sub[sub.method == "fixed_q5"]
        if a.empty or b.empty:
            continue
        ra, rb = a.iloc[0], b.iloc[0]
        cov10 = float(ra.place_max_coverage or 0)
        cov5 = float(rb.place_max_coverage or 0)
        feas10 = str(ra.ball_status)
        feas5 = str(rb.ball_status)
        sites10 = str(ra.place_best_sites)
        sites5 = str(rb.place_best_sites)
        min10 = ra.place_min_sites
        min5 = rb.place_min_sites
        field_rows.append(
            {
                "scenario": scen,
                "feasibility_class_changed": bool(feas10 != feas5),
                "coverage_changed": bool(abs(cov10 - cov5) > 1e-9),
                "minimum_site_count_changed": bool(str(min10) != str(min5)),
                "optimal_site_set_changed": bool(sites10 != sites5),
                "objective_changed": bool(
                    abs(cov10 - cov5) > 1e-9
                    or str(min10) != str(min5)
                    or sites10 != sites5
                ),
                "min_sites_q10": min10,
                "min_sites_q5": min5,
                "coverage_q10": cov10,
                "coverage_q5": cov5,
                "sites_q10": sites10,
                "sites_q5": sites5,
            }
        )

    lines.extend(
        [
            "",
            "## Distinct change fields (q=10 vs q=5)",
            "",
            "Coverage / feasibility-class changes are **not** infrastructure installation changes.",
            "",
            "| Scenario | feasibility_class_changed | coverage_changed | minimum_site_count_changed | optimal_site_set_changed |",
            "| --- | --- | --- | --- | --- |",
        ]
    )
    for fr in field_rows:
        lines.append(
            f"| {fr['scenario']} | {fr['feasibility_class_changed']} | "
            f"{fr['coverage_changed']} | {fr['minimum_site_count_changed']} | "
            f"{fr['optimal_site_set_changed']} |"
        )
        lines.append(
            f"  - detail: coverage {fr['coverage_q10']}→{fr['coverage_q5']}; "
            f"min_sites {fr['min_sites_q10']}→{fr['min_sites_q5']}; "
            f"sites {fr['sites_q10']}→{fr['sites_q5']}"
        )

    any_site_decision = any(
        fr["minimum_site_count_changed"] or fr["optimal_site_set_changed"]
        for fr in field_rows
    )
    any_coverage = any(fr["coverage_changed"] for fr in field_rows)
    any_false_neg = not false_negs.empty

    lines.extend(
        [
            "",
            "## Novelty GO / NO-GO (PASS 2B)",
            "",
        ]
    )
    if any_false_neg and any_site_decision:
        verdict = (
            "**CONDITIONAL evidence only:** discrete false-negative feasibility exists "
            "and coarser grids can change **site installation decisions** on at least one "
            "scenario. This supports a **certification-aware diagnostic** claim, **not** a "
            "new continuous adaptive optimizer theorem."
        )
        go = "CONDITIONAL_DIAGNOSTIC_ONLY"
    elif any_false_neg and any_coverage and not any_site_decision:
        verdict = (
            "**NO-GO for infrastructure-design optimizer claim:** a discrete false-negative "
            "**coverage/feasibility** label changed, but **minimum site counts and optimal "
            "site sets did not**. Protocol is a conditional coarse-to-fine retry, not a "
            "proved selective-refinement algorithm. Keep as numerical-reliability finding."
        )
        go = "NO_GO_COVERAGE_ONLY_NOT_SITE_DECISION"
    elif any_false_neg and not any_site_decision:
        verdict = (
            "**NO-GO for infrastructure-refinement contribution:** a discrete false-negative "
            "routing label was observed, but **optimal site sets / min site counts did not "
            "change**. Withdraw methods claim; keep as numerical hygiene note."
        )
        go = "NO_GO_INFRASTRUCTURE_METHODS"
    else:
        verdict = (
            "**NO-GO for adaptive refinement contribution on these instances:** "
            "no discrete false-negative feasibility that alters planning was demonstrated "
            "beyond prior Task 08 diagnosis."
        )
        go = "NO_GO"

    lines.append(verdict)
    lines.append(f"\n`novelty_decision: {go}`\n")
    # Persist machine-readable field splits beside CSV consumers
    import json as _json

    (ROOT / "results/pass2_refinement_change_fields.json").write_text(
        _json.dumps(field_rows, indent=2, default=str), encoding="utf-8"
    )
    lines.extend(
        [
            "",
            "## Reproduction",
            "",
            "```bash",
            "python scripts/run_pass2b_discretization_refinement.py",
            "```",
            "",
            f"CSV: `results/pass2_refinement_comparison.csv`",
            "",
        ]
    )
    (ROOT / "reports/pass2_discretization_novelty_result.md").write_text(
        "\n".join(lines), encoding="utf-8"
    )
    print(f"novelty_decision={go}", flush=True)


def main() -> int:
    rows: list[dict] = []
    # (1) Northbound Case A
    rows.extend(
        run_scenario(
            "northbound_A80_tomato",
            ROOT / "configs/optimization/multiroute_placement_pass2a.yaml",
            "A_nb_tomato_p5300_soc08",
            ROOT / "configs/vehicles/volvo_fh_electric_4x2_540kwh.yaml",
            ROOT / "configs/energy/pass2_tomato_firm_ripe.yaml",
        )
    )
    # (2) Historical southbound counterexample portfolio cell (Task 08 H80-like)
    # Use Task 08 config demand H80 for casa_marrakech-containing portfolio
    rows.extend(
        run_scenario(
            "southbound_H80_task08_portfolio",
            ROOT / "configs/optimization/multiroute_placement_08.yaml",
            "H80_dem_p15000_soc08",
            ROOT / "configs/vehicles/volvo_fh_electric_4x2_540kwh.yaml",
            ROOT / "configs/energy/task07b_thermal_nominal.yaml",
        )
    )

    out = ROOT / "results/pass2_refinement_comparison.csv"
    df = pd.DataFrame(rows)
    df.to_csv(out, index=False)
    print(f"Wrote {out} ({len(df)} rows)", flush=True)
    write_report(df)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
