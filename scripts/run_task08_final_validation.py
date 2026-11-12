#!/usr/bin/env python
"""Task 08 — SOC/payload robustness, economics audit, shared-road B&B benchmark."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from morocco_etruck.energy.vehicle import (  # noqa: E402
    empty_combination_kg,
    gcm_from_payload,
    load_vehicle,
    validate_gcm,
)
from morocco_etruck.optimization.branch_and_bound import run_branch_and_bound_core  # noqa: E402
from morocco_etruck.optimization.label_setting import SolverStatus, solve_mrls  # noqa: E402
from morocco_etruck.optimization.multiroute_adapter import (  # noqa: E402
    build_physics_od_instance,
    clone_physics_instance_for_subset,
    load_multiroute_pilot_config,
    shortest_path_allowed_arc_ids,
)
from morocco_etruck.optimization.multiroute_placement import (  # noqa: E402
    load_multiroute_placement_config,
)
from morocco_etruck.optimization.multiroute_placement_evaluation import (  # noqa: E402
    all_optimal_site_sets,
    prepare_multiroute_placement_context,
    run_multiroute_branch_and_bound,
    run_multiroute_enumeration,
)
from morocco_etruck.optimization.placement_certification import OptimalityStatus  # noqa: E402
from morocco_etruck.optimization.placement_evaluation import SubsetEvaluation  # noqa: E402
from morocco_etruck.optimization.placement_problem import (  # noqa: E402
    PlacementSite,
    annualized_infra_cost,
    budget_ok,
    capital_recovery_factor,
    subset_capex,
)
from morocco_etruck.optimization.problem import ArcData, RoutingInstance, StationData  # noqa: E402
from morocco_etruck.optimization.site_enumeration import all_subsets  # noqa: E402

VEHICLES = {
    "eactros_600": ROOT / "configs/vehicles/eactros_600.yaml",
    "volvo_475": ROOT / "configs/vehicles/volvo_fh_electric_4x2_540kwh.yaml",
    "volvo_460": ROOT / "configs/vehicles/volvo_fh_electric_4x2_540kwh_usable460.yaml",
}
CFG08 = ROOT / "configs/optimization/multiroute_placement_08.yaml"
ROAD_CENTS = 100.0
FRIDGE = ROOT / "configs/energy/task07b_thermal_nominal.yaml"

CELLS = [
    {"id": "S50", "demand": "S50_dem_p5300_soc05", "soc": 0.5, "payload": 5300.0},
    {"id": "S80", "demand": "S80_dem_p5300_soc08", "soc": 0.8, "payload": 5300.0},
    {"id": "S100", "demand": "S100_dem_p5300_soc10", "soc": 1.0, "payload": 5300.0},
    {"id": "H50", "demand": "H50_dem_p15000_soc05", "soc": 0.5, "payload": 15000.0},
    {"id": "H80", "demand": "H80_dem_p15000_soc08", "soc": 0.8, "payload": 15000.0},
]


def _write(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(path, index=False)
    print(f"Wrote {path} ({len(rows)} rows)", flush=True)


def run_placement() -> list[dict]:
    cfg = load_multiroute_placement_config(CFG08, root=ROOT)
    rows: list[dict] = []
    for cell in CELLS:
        for vkey in ("eactros_600", "volvo_475"):
            vpath = VEHICLES[vkey]
            print(
                f"\n=== place {cell['id']} veh={vkey} soc={cell['soc']} "
                f"payload={cell['payload']} ===",
                flush=True,
            )
            t0 = time.perf_counter()
            try:
                context = prepare_multiroute_placement_context(
                    cfg,
                    root=ROOT,
                    demand_name=cell["demand"],
                    energy_quantum_kwh=10,
                    objective_mode="enroute_incremental_cost",
                    vehicle_yaml=vpath,
                    road_cost_per_km=ROAD_CENTS,
                    fridge_yaml=FRIDGE,
                    charger_power_kw=350.0,
                    max_alternatives_for_union=2,
                )
            except Exception as exc:  # noqa: BLE001
                rows.append(
                    {
                        "cell_id": cell["id"],
                        "vehicle_key": vkey,
                        "status": "BUILD_ERROR",
                        "error": str(exc),
                        "soc_init": cell["soc"],
                        "cargo_payload_kg": cell["payload"],
                    }
                )
                continue
            dem_bad = [
                mid
                for mid, prep in context["prepared"].items()
                if str(prep.mission.terrain_mode) == "dem" and not prep.ctx.dem_complete
            ]
            if dem_bad:
                rows.append(
                    {
                        "cell_id": cell["id"],
                        "vehicle_key": vkey,
                        "status": "dem_incomplete",
                        "unresolved_ids": ",".join(dem_bad),
                        "soc_init": cell["soc"],
                        "cargo_payload_kg": cell["payload"],
                    }
                )
                continue
            prep_s = time.perf_counter() - t0
            missions = cfg.demand_scenarios[cell["demand"]]
            infeas_w = sum(
                float(m.weight)
                for m in missions
                if context["serviceability"].get(m.id) == "unserved_all_candidates"
            )
            vehicle = load_vehicle(vpath)
            gcm = gcm_from_payload(cell["payload"], vehicle)
            for bud in cfg.budgets:
                bname = str(bud["name"])
                enum_rows, best, context = run_multiroute_enumeration(
                    cfg,
                    root=ROOT,
                    demand_name=cell["demand"],
                    capex_name="equal",
                    budget_name=bname,
                    context=context,
                )
                bb, context = run_multiroute_branch_and_bound(
                    cfg,
                    root=ROOT,
                    demand_name=cell["demand"],
                    capex_name="equal",
                    budget_name=bname,
                    context=context,
                )
                inc = bb.incumbent
                opt_sets = all_optimal_site_sets(enum_rows)
                obj_agree = False
                if best is not None and inc is not None:
                    obj_agree = (
                        abs(best.coverage_serviceable - inc.coverage_serviceable)
                        <= 1e-9
                        and abs(best.secondary_cost - inc.secondary_cost) <= 1e-6
                    )
                elif best is None and inc is None:
                    obj_agree = True
                n_sites = len(inc.site_ids) if inc else 0
                rows.append(
                    {
                        "cell_id": cell["id"],
                        "demand_name": cell["demand"],
                        "vehicle_key": vkey,
                        "usable_kwh": vehicle.usable_kwh,
                        "soc_init": cell["soc"],
                        "cargo_payload_kg": cell["payload"],
                        "gcm_realized_kg": gcm,
                        "empty_combination_kg": empty_combination_kg(vehicle),
                        "gcm_limit_kg": vehicle.gcm_limit_kg,
                        "terrain_mode": "dem",
                        "energy_quantum_kwh": 10,
                        "budget_name": bname,
                        "weight_total_demand": context["weight_total_demand"],
                        "coverage_serviceable": (
                            None if inc is None else inc.coverage_serviceable
                        ),
                        "n_sites_installed": n_sites,
                        "infeasible_under_candidates_weight": infeas_w,
                        "unresolved_weight": context["unresolved_weight"],
                        "best_sites_bb": (
                            ",".join(sorted(inc.site_ids)) if inc else ""
                        ),
                        "best_sites_enum": (
                            ",".join(sorted(best.site_ids)) if best else ""
                        ),
                        "secondary_cost": None if inc is None else inc.secondary_cost,
                        "objective_agreement": obj_agree,
                        "all_optimal_site_sets": "|".join(opt_sets),
                        "n_optimal_site_sets": len(opt_sets),
                        "optimality_status": bb.optimality_status.value,
                        "certified_full_portfolio": (
                            bb.optimality_status == OptimalityStatus.CERTIFIED_OPTIMAL
                        ),
                        "serviceability_json": json.dumps(
                            context.get("serviceability") or {}
                        ),
                        "prep_sec": prep_s,
                        "claim_scope": "task08_soc_payload",
                    }
                )
                print(
                    f"  {bname}: cov={rows[-1]['coverage_serviceable']} "
                    f"sites={rows[-1]['best_sites_bb'] or 'NONE'} agree={obj_agree}",
                    flush=True,
                )
    # Min sites for max coverage summary fields
    return rows


def run_matched_routing(cells: list[dict]) -> list[dict]:
    """B/C same-graph masks for selected cells on CM+CA."""
    rows: list[dict] = []
    cfg = load_multiroute_pilot_config(
        ROOT / "configs/optimization/multiroute_pilot.yaml", root=ROOT
    )
    path_rows = pd.read_csv(cfg.path_alternatives_csv).to_dict(orient="records")
    for cell in cells:
        for vkey in ("eactros_600", "volvo_475"):
            vpath = VEHICLES[vkey]
            vehicle = load_vehicle(vpath)
            gcm = gcm_from_payload(cell["payload"], vehicle)
            e_init = int(round(cell["soc"] * float(vehicle.usable_kwh)))
            for od_id in ("casa_marrakech", "casa_agadir"):
                try:
                    tmpl, ctx, notes = build_physics_od_instance(
                        cfg=cfg,
                        root=ROOT,
                        od_id=od_id,
                        path_rows=path_rows,
                        E_truck_init=e_init,
                        refrigeration_on=True,
                        weather_id="cool",
                        with_chargers=True,
                        energy_quantum_kwh=10,
                        terrain_mode="dem",
                        objective_mode="enroute_incremental_cost",
                        vehicle_yaml=vpath,
                        road_cost_per_km=ROAD_CENTS,
                        gcm_kg=gcm,
                        fridge_yaml=FRIDGE,
                        charger_power_kw=350.0,
                        max_alternatives_for_union=2,
                    )
                except Exception as exc:  # noqa: BLE001
                    rows.append(
                        {
                            "cell_id": cell["id"],
                            "vehicle_key": vkey,
                            "od_id": od_id,
                            "status": "BUILD_ERROR",
                            "error": str(exc),
                            "soc_init": cell["soc"],
                            "cargo_payload_kg": cell["payload"],
                        }
                    )
                    continue
                if not ctx.dem_complete:
                    rows.append(
                        {
                            "cell_id": cell["id"],
                            "vehicle_key": vkey,
                            "od_id": od_id,
                            "status": "dem_incomplete",
                            "soc_init": cell["soc"],
                            "cargo_payload_kg": cell["payload"],
                        }
                    )
                    continue
                short = shortest_path_allowed_arc_ids(ctx, path_rows, od_id)
                all_ids = frozenset(str(a.arc_id) for a in tmpl.arcs if a.arc_id)
                active = {"settat_ca", "benguerir_ca"} & set(tmpl.stations)
                for bid, mask, method in (
                    ("B", short, "mrls_fixed_shortest"),
                    ("C", all_ids, "mrls_multi_route"),
                ):
                    inst = clone_physics_instance_for_subset(
                        tmpl, active_stations=set(active), allowed_arc_ids=mask
                    )
                    res = solve_mrls(inst, max_seconds=90.0, max_expansions=800_000)
                    rows.append(
                        {
                            "cell_id": cell["id"],
                            "baseline_id": bid,
                            "method": method,
                            "vehicle_key": vkey,
                            "od_id": od_id,
                            "soc_init": cell["soc"],
                            "cargo_payload_kg": cell["payload"],
                            "gcm_realized_kg": gcm,
                            "install_set": "settat_benguerir",
                            "mrls_status": res.status.value,
                            "objective": res.objective,
                            "nesting_class": (
                                "positive"
                                if bid == "C"
                                else "restricted"
                            ),
                            "claim_scope": "task08_matched_routing",
                            "station_notes": ";".join(notes),
                        }
                    )
                    print(
                        f"{cell['id']}|{bid}|{vkey}|{od_id}: {res.status.value} "
                        f"obj={res.objective}",
                        flush=True,
                    )
                # annotate nesting vs B
                b = rows[-2]
                c = rows[-1]
                if b["mrls_status"] == "OPTIMAL":
                    nest_ok = (
                        c["mrls_status"] == "OPTIMAL"
                        and c["objective"] is not None
                        and b["objective"] is not None
                        and float(c["objective"]) <= float(b["objective"]) + 1e-9
                    )
                    c["nesting_ok_vs_B"] = nest_ok
                    c["nesting_class"] = (
                        "positive_feasible_restricted"
                        if nest_ok
                        else "nesting_fail"
                    )
                    if (
                        nest_ok
                        and c["objective"] is not None
                        and b["objective"] is not None
                        and float(c["objective"]) < float(b["objective"]) - 1e-9
                    ):
                        c["nesting_class"] = "positive_strict_cheaper"
                elif c["mrls_status"] == "OPTIMAL":
                    c["nesting_ok_vs_B"] = True
                    c["nesting_class"] = "feasibility_gain_restricted_IF"
                else:
                    c["nesting_ok_vs_B"] = True
                    c["nesting_class"] = "vacuous_both_IF"
    return rows


def run_economics(place_rows: list[dict]) -> list[dict]:
    """CAPEX ratio sensitivity on equal illustrative site costs (no fake MAD)."""
    cfg = load_multiroute_placement_config(CFG08, root=ROOT)
    rows: list[dict] = []
    # Use S50 eActros + Volvo as echo; re-run Ball/B1/B2 with scaled CAPEX via raw mutate of equal scenario
    base_capex = dict(cfg.capex_scenarios["equal"])
    for mult, label in ((0.5, "low"), (1.0, "medium"), (2.0, "high")):
        cfg.capex_scenarios["equal"] = {
            k: float(v) * mult for k, v in base_capex.items()
        }
        for vkey in ("eactros_600", "volvo_475"):
            context = prepare_multiroute_placement_context(
                cfg,
                root=ROOT,
                demand_name="S50_dem_p5300_soc05",
                energy_quantum_kwh=10,
                objective_mode="enroute_incremental_cost",
                vehicle_yaml=VEHICLES[vkey],
                road_cost_per_km=ROAD_CENTS,
                fridge_yaml=FRIDGE,
                charger_power_kw=350.0,
                max_alternatives_for_union=2,
            )
            for bname in ("B1", "B2", "Ball"):
                enum_rows, best, context = run_multiroute_enumeration(
                    cfg,
                    root=ROOT,
                    demand_name="S50_dem_p5300_soc05",
                    capex_name="equal",
                    budget_name=bname,
                    context=context,
                )
                bb, context = run_multiroute_branch_and_bound(
                    cfg,
                    root=ROOT,
                    demand_name="S50_dem_p5300_soc05",
                    capex_name="equal",
                    budget_name=bname,
                    context=context,
                )
                inc = bb.incumbent
                rows.append(
                    {
                        "capex_ratio": mult,
                        "capex_label": label,
                        "vehicle_key": vkey,
                        "budget_name": bname,
                        "coverage_serviceable": (
                            None if inc is None else inc.coverage_serviceable
                        ),
                        "best_sites_bb": (
                            ",".join(sorted(inc.site_ids)) if inc else ""
                        ),
                        "secondary_cost": None if inc is None else inc.secondary_cost,
                        "site_capex_each": 100.0 * mult,
                        "energy_price_note": "uniform_research_cents_not_onee_quote",
                        "capex_note": "illustrative_ratio_not_moroccan_construction_quote",
                        "claim_scope": "task08_economics",
                    }
                )
                print(
                    f"econ {label}× {vkey} {bname}: "
                    f"sites={rows[-1]['best_sites_bb'] or 'NONE'} "
                    f"cov={rows[-1]['coverage_serviceable']}",
                    flush=True,
                )
    cfg.capex_scenarios["equal"] = base_capex
    return rows


def build_shared_road_problem() -> tuple[list[PlacementSite], dict[str, float], list[dict], dict[str, RoutingInstance]]:
    """
    Synthetic shared-trunk multi-route placement (8 sites).

    Shared short trunk O -> Hub -> Si -> D (needs charge at Si for low SOC).
    Shared long alternative O -> Alt -> D (feasible without charge, higher road cost).
    Sites S00–S05 cheap; S06–S07 expensive prune fodder.
    """
    sites = [
        PlacementSite(f"s{i:02d}", "synth", f"S{i:02d}", f"synth_{i}") for i in range(8)
    ]
    capex = {s.id: (100.0 if i < 6 else 220.0) for i, s in enumerate(sites)}
    arcs: list[ArcData] = [
        ArcData("O", "Hub", 1, 35, 0, road_cost=5, arc_id="o_hub"),
        ArcData("O", "Alt", 1, 25, 0, road_cost=40, arc_id="o_alt"),
        ArcData("Alt", "D", 1, 25, 0, road_cost=40, arc_id="alt_d"),
    ]
    for i in range(8):
        sid = f"S{i:02d}"
        arcs.append(ArcData("Hub", sid, 1, 5, 0, road_cost=1, arc_id=f"hub_{sid}"))
        arcs.append(ArcData(sid, "D", 1, 40, 0, road_cost=1, arc_id=f"{sid}_d"))
    stations = {
        f"S{i:02d}": StationData(f"S{i:02d}", 350.0, 1.0, 10, True) for i in range(8)
    }
    nodes = ["O", "Hub", "Alt", "D"] + [f"S{i:02d}" for i in range(8)]

    def make_inst(name: str, e_init: int) -> RoutingInstance:
        return RoutingInstance(
            name=name,
            nodes=nodes,
            arcs=list(arcs),
            origin="O",
            destination="D",
            deadline_steps=30,
            E_truck_cap=120,
            E_truck_min=0,
            E_truck_init=e_init,
            E_trailer_cap=None,
            E_trailer_min=None,
            E_trailer_init=None,
            stations=dict(stations),
            active_stations=set(),
            power_source="A",
            refrigeration_on=False,
            energy_quantum_kwh=1,
            time_step_min=5,
            wait_max_steps=0,
            notes="synthetic_shared_road_task08",
        )

    # Low SOC: short trunk needs a charger; Alt still works without charge (coverage vs cost).
    missions = [
        {"id": "M_low_a", "weight": 2.0, "e_init": 40},
        {"id": "M_low_b", "weight": 2.0, "e_init": 42},
        {"id": "M_mid", "weight": 1.5, "e_init": 55},
        {"id": "M_high", "weight": 1.0, "e_init": 100},
    ]
    templates = {m["id"]: make_inst(m["id"], int(m["e_init"])) for m in missions}
    return sites, capex, missions, templates


def run_shared_road_benchmark() -> list[dict]:
    sites, capex, missions, templates = build_shared_road_problem()
    crf = capital_recovery_factor(0.08, 15)
    cents = 0.01
    weight = {m["id"]: float(m["weight"]) for m in missions}
    wtot = sum(weight.values())
    rows: list[dict] = []

    def evaluate_fn(installed: set[str]) -> SubsetEvaluation:
        active = {
            sites[i].station_key
            for i, s in enumerate(sites)
            if s.id in installed
        }
        # serviceability probe uses all sites — for evaluate just solve each
        results = []
        served_w = 0.0
        var = 0.0
        for m in missions:
            mid = m["id"]
            inst = clone_physics_instance_for_subset(
                templates[mid], active_stations=active
            )
            # ensure allowed_arc_ids copies
            r = solve_mrls(inst, max_seconds=5.0, max_expansions=50_000)
            ok = r.status == SolverStatus.OPTIMAL
            if ok:
                served_w += weight[mid]
                var += weight[mid] * float(r.objective or 0) * cents
            results.append(ok)
        infra = subset_capex(installed, capex)
        infra_ann = annualized_infra_cost(installed, capex, crf)
        return SubsetEvaluation(
            site_ids=frozenset(installed),
            budget_ok=True,
            certified=True,
            coverage_total=served_w,
            coverage_serviceable=served_w,
            weight_total=wtot,
            weight_serviceable=wtot,
            infra_capex=infra,
            infra_annual=infra_ann,
            variable_cost=var,
            secondary_cost=infra_ann + var,
            missions=[],
        )

    # Serviceability under all sites
    all_ids = {s.id for s in sites}
    all_eval = evaluate_fn(all_ids)
    serviceable = all_eval.coverage_serviceable >= wtot - 1e-9

    for bname, max_capex in (("B2", 200.0), ("B3", 300.0), ("Ball", None)):
        t0 = time.perf_counter()
        best_enum = None
        n_enum = 0
        for subset in all_subsets([s.id for s in sites]):
            if not budget_ok(subset, capex, max_capex):
                continue
            n_enum += 1
            ev = evaluate_fn(subset)
            if best_enum is None:
                best_enum = ev
            else:
                better = ev.coverage_serviceable > best_enum.coverage_serviceable + 1e-9
                tie = (
                    abs(ev.coverage_serviceable - best_enum.coverage_serviceable)
                    <= 1e-9
                    and ev.secondary_cost < best_enum.secondary_cost - 1e-9
                )
                if better or tie:
                    best_enum = ev
        enum_s = time.perf_counter() - t0

        t1 = time.perf_counter()
        bb = run_branch_and_bound_core(
            site_ids=[s.id for s in sites],
            capex=capex,
            max_capex=max_capex,
            crf=crf,
            evaluate_fn=evaluate_fn,
            time_limit_sec=60.0,
            node_limit=None,
        )
        bb_s = time.perf_counter() - t1
        inc = bb.incumbent
        agree = False
        if best_enum is not None and inc is not None:
            agree = (
                abs(best_enum.coverage_serviceable - inc.coverage_serviceable) <= 1e-9
                and abs(best_enum.secondary_cost - inc.secondary_cost) <= 1e-6
            )
        elif best_enum is None and inc is None:
            agree = True
        stats = bb.stats
        rows.append(
            {
                "benchmark": "shared_road_8site_synthetic",
                "n_sites": 8,
                "n_missions": len(missions),
                "budget_name": bname,
                "max_capex": max_capex,
                "enum_subsets_evaluated": n_enum,
                "enum_best_sites": (
                    ",".join(sorted(best_enum.site_ids)) if best_enum else ""
                ),
                "enum_coverage": (
                    None if best_enum is None else best_enum.coverage_serviceable
                ),
                "enum_secondary_cost": (
                    None if best_enum is None else best_enum.secondary_cost
                ),
                "enum_sec": enum_s,
                "bb_best_sites": (
                    ",".join(sorted(inc.site_ids)) if inc else ""
                ),
                "bb_coverage": None if inc is None else inc.coverage_serviceable,
                "bb_secondary_cost": None if inc is None else inc.secondary_cost,
                "bb_sec": bb_s,
                "objective_agreement": agree,
                "optimality_status": bb.optimality_status.value,
                "bb_nodes_visited": stats.nodes_visited,
                "bb_leaves_evaluated": stats.leaves_evaluated,
                "bb_prunes_budget": stats.prune_budget,
                "bb_prunes_coverage": stats.prune_coverage,
                "bb_prunes_secondary": stats.prune_secondary,
                "bb_mrls_calls": stats.mrls_calls,
                "bb_mrls_cache_hits": stats.mrls_cache_hits,
                "claim_scope": "task08_algorithm_synthetic_shared_road",
                "note": "synthetic_not_moroccan_traffic",
            }
        )
        print(
            f"BB {bname}: agree={agree} enum={rows[-1]['enum_best_sites']} "
            f"bb={rows[-1]['bb_best_sites']} enum_t={enum_s:.2f}s bb_t={bb_s:.2f}s",
            flush=True,
        )
    return rows


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--stages",
        default="all",
        help="placement,routing,economics,benchmark,all",
    )
    args = p.parse_args()
    stages = {s.strip() for s in args.stages.split(",") if s.strip()}
    if "all" in stages:
        stages = {"placement", "routing", "economics", "benchmark"}

    place_rows: list[dict] = []
    if "placement" in stages:
        place_rows = run_placement()
        _write(ROOT / "results/task08_soc_payload_comparison.csv", place_rows)

    if "routing" in stages:
        route_cells = [c for c in CELLS if c["id"] in {"S50", "S80", "S100", "H50"}]
        rows = run_matched_routing(route_cells)
        # append to soc_payload file as routing rows or separate — plan says one comparison csv
        # Keep separate matched routing in same file with baseline_id column
        existing = ROOT / "results/task08_soc_payload_comparison.csv"
        if existing.exists() and place_rows:
            df = pd.concat(
                [pd.DataFrame(place_rows), pd.DataFrame(rows)], ignore_index=True
            )
            df.to_csv(existing, index=False)
            print(f"Updated {existing} with routing rows", flush=True)
        else:
            _write(ROOT / "results/task08_soc_payload_comparison.csv", place_rows + rows)

    if "economics" in stages:
        rows = run_economics(place_rows)
        _write(ROOT / "results/task08_placement_economics.csv", rows)

    if "benchmark" in stages:
        rows = run_shared_road_benchmark()
        _write(ROOT / "results/task08_algorithm_benchmarks.csv", rows)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
