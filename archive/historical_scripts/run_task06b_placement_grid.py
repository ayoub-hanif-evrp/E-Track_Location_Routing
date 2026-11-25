#!/usr/bin/env python
"""Task 06B — placement robustness across energy grids and objective modes."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from morocco_etruck.optimization.multiroute_adapter import (  # noqa: E402
    clone_physics_instance_for_subset,
    load_multiroute_pilot_config,
)
from morocco_etruck.optimization.multiroute_placement import (  # noqa: E402
    load_multiroute_placement_config,
)
from morocco_etruck.optimization.multiroute_placement_evaluation import (  # noqa: E402
    prepare_multiroute_placement_context,
    run_multiroute_branch_and_bound,
    run_multiroute_enumeration,
)
from morocco_etruck.optimization.label_setting import SolverStatus, solve_mrls  # noqa: E402
from morocco_etruck.optimization.placement_certification import OptimalityStatus  # noqa: E402
from morocco_etruck.optimization.multiroute_replay import continuous_replay_multiroute  # noqa: E402
from morocco_etruck.optimization.replay import replay_solution  # noqa: E402


OBJECTIVES = ("enroute_incremental_cost", "energy_replenishment_cost")


def _mission_detail(ev) -> str:
    parts = []
    for m in ev.missions:
        parts.append(
            f"{m.mission_id}:{m.status}:served={int(m.served)}:"
            f"chg={m.charges or ''}:obj={m.objective_cents}"
        )
    return ";".join(parts)


def run_placement_matrix(
    *,
    quanta: list[int],
    objectives: list[str],
    budgets: list[str] | None,
    q2_b1_only: bool,
) -> tuple[list[dict], list[dict]]:
    cfg = load_multiroute_placement_config(
        ROOT / "configs/optimization/multiroute_placement_pilot.yaml", root=ROOT
    )
    place_rows: list[dict] = []
    obj_rows: list[dict] = []

    for q in quanta:
        for mode in objectives:
            scope_budgets = list(cfg.budgets)
            unresolved_note = ""
            if q == 2 and q2_b1_only:
                scope_budgets = [b for b in cfg.budgets if str(b["name"]) == "B1"]
                unresolved_note = "q2_restricted_to_B1"

            print(f"\n=== q={q} mode={mode} ===", flush=True)
            t_prep = time.perf_counter()
            try:
                context = prepare_multiroute_placement_context(
                    cfg,
                    root=ROOT,
                    demand_name="default",
                    energy_quantum_kwh=q,
                    objective_mode=mode,
                )
            except Exception as exc:  # noqa: BLE001 — record unresolved prep
                place_rows.append(
                    {
                        "energy_quantum_kwh": q,
                        "objective_mode": mode,
                        "budget_name": "ALL",
                        "method": "prep",
                        "status": "UNRESOLVED",
                        "reason": f"prep_failed:{exc}",
                        "enum_agreement": False,
                    }
                )
                print(f"PREP FAILED q={q} mode={mode}: {exc}", flush=True)
                continue
            prep_s = time.perf_counter() - t_prep
            print(
                f"Prepared in {prep_s:.1f}s; serviceability={context['serviceability']}",
                flush=True,
            )

            # Objective comparison on single-mission probes (all sites / no sites)
            for mid, prep in context["prepared"].items():
                for with_chg, label in ((False, "no_charge"), (True, "all_sites")):
                    active = set(prep.template.stations.keys()) if with_chg else set()
                    inst = clone_physics_instance_for_subset(
                        prep.template, active_stations=active, name=f"{mid}:{label}"
                    )
                    t0 = time.perf_counter()
                    res = solve_mrls(
                        inst,
                        max_seconds=cfg.solver_max_seconds,
                        max_expansions=cfg.solver_max_expansions,
                    )
                    solve_s = time.perf_counter() - t0
                    disc_ok = False
                    cont_ok = False
                    cont_reason = None
                    if res.status == SolverStatus.OPTIMAL and res.final_label is not None:
                        disc = replay_solution(inst, res.actions, expected_cost=res.objective)
                        disc_ok = disc.ok
                        crep, extras = continuous_replay_multiroute(
                            prep.ctx,
                            inst,
                            res.actions,
                            discrete_cost=res.objective,
                            discrete_t=res.final_label.t,
                            discrete_E_truck=res.final_label.E_truck,
                        )
                        cont_ok = crep.ok
                        cont_reason = crep.reason
                        charges = [
                            {"node": a["node"], "delta_e_kwh": a["delta_e_kwh"]}
                            for a in res.actions
                            if a.get("type") == "CHARGE"
                        ]
                        arc_ids = [
                            a.get("arc_id") for a in res.actions if a.get("type") == "DRIVE"
                        ]
                        obj_rows.append(
                            {
                                "mission_id": mid,
                                "energy_quantum_kwh": q,
                                "objective_mode": mode,
                                "scenario": label,
                                "mrls_status": res.status.value,
                                "objective": res.objective,
                                "enroute_cost": res.final_label.cost,
                                "final_E_truck": res.final_label.E_truck,
                                "path": "->".join(res.path_nodes),
                                "road_distance_m": extras.length_m if cont_ok else None,
                                "charges_json": json.dumps(charges),
                                "arc_ids_json": json.dumps(arc_ids),
                                "discrete_replay_ok": disc_ok,
                                "continuous_replay_ok": cont_ok,
                                "continuous_replay_reason": cont_reason,
                                "labels_expanded": res.stats.get("labels_expanded"),
                                "labels_generated": res.stats.get("labels_generated"),
                                "solve_sec": solve_s,
                            }
                        )
                    else:
                        obj_rows.append(
                            {
                                "mission_id": mid,
                                "energy_quantum_kwh": q,
                                "objective_mode": mode,
                                "scenario": label,
                                "mrls_status": res.status.value,
                                "objective": res.objective,
                                "enroute_cost": None,
                                "final_E_truck": None,
                                "path": "",
                                "road_distance_m": None,
                                "charges_json": "[]",
                                "arc_ids_json": "[]",
                                "discrete_replay_ok": False,
                                "continuous_replay_ok": False,
                                "continuous_replay_reason": res.status.value,
                                "labels_expanded": res.stats.get("labels_expanded"),
                                "labels_generated": res.stats.get("labels_generated"),
                                "solve_sec": solve_s,
                            }
                        )

            for bud in scope_budgets:
                bname = str(bud["name"])
                if budgets is not None and bname not in budgets:
                    continue
                print(f"  budget {bname} ...", flush=True)
                t0 = time.perf_counter()
                enum_rows, best, context = run_multiroute_enumeration(
                    cfg,
                    root=ROOT,
                    demand_name="default",
                    capex_name="equal",
                    budget_name=bname,
                    context=context,
                )
                enum_s = time.perf_counter() - t0
                t1 = time.perf_counter()
                bb, context = run_multiroute_branch_and_bound(
                    cfg,
                    root=ROOT,
                    demand_name="default",
                    capex_name="equal",
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
                        and set(best.site_ids) == set(inc.site_ids)
                    )
                elif best is None and inc is None:
                    agree = True

                status = bb.optimality_status.value
                if any(
                    m.status == SolverStatus.LIMIT_REACHED.value
                    for ev in ([best] if best else [])
                    for m in (ev.missions if ev else [])
                ):
                    status = "UNRESOLVED"

                place_rows.append(
                    {
                        "energy_quantum_kwh": q,
                        "objective_mode": mode,
                        "budget_name": bname,
                        "max_capex": bud.get("max_capex"),
                        "method": "branch_and_bound",
                        "best_sites": ",".join(sorted(inc.site_ids)) if inc else "",
                        "enum_best_sites": ",".join(sorted(best.site_ids)) if best else "",
                        "n_sites": 0 if inc is None else len(inc.site_ids),
                        "coverage_serviceable": None if inc is None else inc.coverage_serviceable,
                        "secondary_cost": None if inc is None else inc.secondary_cost,
                        "variable_cost": None if inc is None else inc.variable_cost,
                        "infra_annual": None if inc is None else inc.infra_annual,
                        "optimality_status": status,
                        "certified": bb.optimality_status == OptimalityStatus.CERTIFIED_OPTIMAL,
                        "enum_agreement": agree,
                        "nodes_visited": bb.stats.nodes_visited,
                        "nodes_expanded": bb.stats.nodes_expanded,
                        "prune_budget": bb.stats.prune_budget,
                        "prune_coverage": bb.stats.prune_coverage,
                        "prune_secondary": bb.stats.prune_secondary,
                        "prep_sec": prep_s,
                        "enum_sec": enum_s,
                        "bb_sec": bb_s,
                        "serviceability_json": json.dumps(context.get("serviceability") or {}),
                        "mission_detail": _mission_detail(inc) if inc else "",
                        "note": unresolved_note,
                        "n_enum_rows": len(enum_rows),
                    }
                )
                print(
                    f"  {bname}: sites={place_rows[-1]['best_sites'] or 'NONE'} "
                    f"cov={place_rows[-1]['coverage_serviceable']} "
                    f"agree={agree} status={status}",
                    flush=True,
                )

    return place_rows, obj_rows


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--quanta", default="10,5,2")
    p.add_argument(
        "--objectives",
        default="enroute_incremental_cost,energy_replenishment_cost",
    )
    p.add_argument(
        "--q2-b1-only",
        action="store_true",
        default=True,
        help="If q=2 is too heavy, restrict placement to B1 (default True).",
    )
    p.add_argument("--no-q2-b1-only", action="store_true")
    args = p.parse_args()
    quanta = [int(x) for x in str(args.quanta).split(",") if x.strip()]
    objectives = [x.strip() for x in str(args.objectives).split(",") if x.strip()]
    q2_b1 = False if args.no_q2_b1_only else bool(args.q2_b1_only)

    place_rows, obj_rows = run_placement_matrix(
        quanta=quanta,
        objectives=objectives,
        budgets=None,
        q2_b1_only=q2_b1,
    )
    out_place = ROOT / "results/task06b_placement_grid_comparison.csv"
    out_obj = ROOT / "results/task06b_objective_comparison.csv"
    out_place.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(place_rows).to_csv(out_place, index=False)
    pd.DataFrame(obj_rows).to_csv(out_obj, index=False)
    print(f"Wrote {out_place} ({len(place_rows)} rows)", flush=True)
    print(f"Wrote {out_obj} ({len(obj_rows)} rows)", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
