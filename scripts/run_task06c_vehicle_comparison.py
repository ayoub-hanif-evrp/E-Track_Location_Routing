#!/usr/bin/env python
"""Task 06C — eActros vs Volvo FH Electric on identical Moroccan path-union missions."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from morocco_etruck.energy.vehicle import load_vehicle  # noqa: E402
from morocco_etruck.optimization.label_setting import SolverStatus, solve_mrls  # noqa: E402
from morocco_etruck.optimization.multiroute_adapter import (  # noqa: E402
    build_physics_od_instance,
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
from morocco_etruck.optimization.multiroute_replay import continuous_replay_multiroute  # noqa: E402
from morocco_etruck.optimization.placement_certification import OptimalityStatus  # noqa: E402
from morocco_etruck.optimization.replay import replay_solution  # noqa: E402

VEHICLES = {
    "eactros_600": ROOT / "configs/vehicles/eactros_600.yaml",
    "volvo_475": ROOT / "configs/vehicles/volvo_fh_electric_4x2_540kwh.yaml",
    "volvo_460": ROOT / "configs/vehicles/volvo_fh_electric_4x2_540kwh_usable460.yaml",
}

# Research cents/km (= 1 currency unit/km at cents_to_currency=0.01)
ROAD_CENTS_PER_KM = 100.0


def _mission_specs(cfg) -> list[dict]:
    return [
        {
            "mission_id": "casa_marrakech_full_nochg",
            "od_id": "casa_marrakech",
            "E_frac": 1.0,
            "with_chargers": False,
            "refrigeration_on": False,
            "gcm": "light",
            "terrain_mode": "flat",
        },
        {
            "mission_id": "casa_marrakech_low_chg",
            "od_id": "casa_marrakech",
            "E_frac": None,  # use absolute init below
            "E_init_kwh": 200,
            "with_chargers": True,
            "refrigeration_on": False,
            "gcm": "light",
            "terrain_mode": "flat",
        },
        {
            "mission_id": "casa_marrakech_refrig_chg",
            "od_id": "casa_marrakech",
            "E_init_kwh": 300,
            "with_chargers": True,
            "refrigeration_on": True,
            "gcm": "light",
            "terrain_mode": "flat",
        },
        {
            "mission_id": "casa_agadir_full_nochg",
            "od_id": "casa_agadir",
            "E_frac": 1.0,
            "with_chargers": False,
            "refrigeration_on": False,
            "gcm": "light",
            "terrain_mode": "flat",
        },
        {
            "mission_id": "casa_agadir_low_chg",
            "od_id": "casa_agadir",
            "E_init_kwh": 200,
            "with_chargers": True,
            "refrigeration_on": False,
            "gcm": "light",
            "terrain_mode": "flat",
        },
        {
            "mission_id": "marrakech_agadir_low_chg",
            "od_id": "marrakech_agadir",
            "E_init_kwh": 200,
            "with_chargers": True,
            "refrigeration_on": False,
            "gcm": "light",
            "terrain_mode": "flat",
        },
    ]


def run_routing_rows(*, quanta: list[int], objectives: list[str]) -> list[dict]:
    cfg = load_multiroute_pilot_config(
        ROOT / "configs/optimization/multiroute_pilot.yaml", root=ROOT
    )
    path_df = pd.read_csv(cfg.path_alternatives_csv)
    path_rows = path_df.to_dict(orient="records")
    rows: list[dict] = []

    for vkey, vpath in VEHICLES.items():
        vehicle = load_vehicle(vpath)
        for q in quanta:
            for mode in objectives:
                # Task 06D fix: freeze light/heavy from immutable physics YAML values.
                # NEVER mutate cfg.gcm_kg — that caused the Task 06C light←40t leak.
                _phys = cfg.raw.get("physics") or {}
                _gcm_light = float(_phys.get("gcm_kg", 25000.0))
                _gcm_heavy = float(_phys.get("gcm_heavy_kg", 40000.0))
                for gcm_label, gcm_kg in (
                    ("light", _gcm_light),
                    ("heavy", _gcm_heavy),
                ):
                    if gcm_kg > vehicle.gcm_limit_kg + 1e-6:
                        continue
                    for spec in _mission_specs(cfg):
                        if gcm_label == "heavy" and not spec["refrigeration_on"]:
                            # Keep heavy matrix small: only refrig / full-battery probes
                            if "full" not in spec["mission_id"]:
                                continue
                        init_kwh = spec.get("E_init_kwh")
                        if init_kwh is None and spec.get("E_frac") is not None:
                            init_kwh = float(spec["E_frac"]) * float(vehicle.usable_kwh)
                        # Install sets (bounded matrix)
                        if not spec["with_chargers"]:
                            install_modes = [("none", False, None)]
                        elif q == 10 and gcm_label == "light" and mode == "enroute_incremental_cost":
                            install_modes = [
                                ("none", False, set()),
                                ("settat_only", True, {"settat_ca"}),
                                ("settat_benguerir", True, {"settat_ca", "benguerir_ca"}),
                                ("all_compatible", True, None),
                            ]
                        else:
                            # Sensitivity cells: none vs all only
                            install_modes = [
                                ("none", False, set()),
                                ("all_compatible", True, None),
                            ]
                        # Skip heavy GCM except full-battery nochg / refrig on q=10 enroute
                        if gcm_label == "heavy":
                            if q != 10 or mode != "enroute_incremental_cost":
                                continue
                            if not (
                                "full" in spec["mission_id"] or spec["refrigeration_on"]
                            ):
                                continue
                        for install_name, with_chg, active_keys in install_modes:
                            mid = (
                                f"{vkey}|q{q}|{mode}|gcm{gcm_label}|"
                                f"{spec['mission_id']}|{install_name}"
                            )
                            t0 = time.perf_counter()
                            try:
                                inst, ctx, notes = build_physics_od_instance(
                                    cfg=cfg,
                                    root=ROOT,
                                    od_id=spec["od_id"],
                                    path_rows=path_rows,
                                    E_truck_init=int(round(float(init_kwh))),
                                    E_truck_cap=None,
                                    E_truck_min=None,
                                    refrigeration_on=bool(spec["refrigeration_on"]),
                                    weather_id="cool",
                                    with_chargers=bool(with_chg),
                                    energy_quantum_kwh=q,
                                    terrain_mode=str(spec["terrain_mode"]),
                                    objective_mode=mode,
                                    vehicle_yaml=vpath,
                                    road_cost_per_km=ROAD_CENTS_PER_KM,
                                    active_station_keys=active_keys,
                                    gcm_kg=float(gcm_kg),
                                )
                            except Exception as exc:  # noqa: BLE001
                                rows.append(
                                    {
                                        "row_id": mid,
                                        "vehicle_id": vehicle.vehicle_id,
                                        "vehicle_key": vkey,
                                        "usable_kwh": vehicle.usable_kwh,
                                        "energy_quantum_kwh": q,
                                        "objective_mode": mode,
                                        "gcm_label": gcm_label,
                                        "gcm_kg": gcm_kg,
                                        "mission_id": spec["mission_id"],
                                        "install_set": install_name,
                                        "status": "BUILD_ERROR",
                                        "error": str(exc),
                                        "prep_sec": time.perf_counter() - t0,
                                    }
                                )
                                print(f"{mid}: BUILD_ERROR {exc}", flush=True)
                                continue
                            if active_keys is not None and with_chg:
                                inst = clone_physics_instance_for_subset(
                                    inst,
                                    active_stations=set(active_keys) & set(inst.stations),
                                    name=mid,
                                )
                            prep_s = time.perf_counter() - t0
                            t1 = time.perf_counter()
                            res = solve_mrls(
                                inst,
                                max_seconds=float(cfg.raw.get("solver", {}).get("max_seconds", 90)),
                                max_expansions=int(
                                    cfg.raw.get("solver", {}).get("max_expansions", 800000)
                                ),
                            )
                            solve_s = time.perf_counter() - t1
                            disc_ok = cont_ok = False
                            cont_reason = None
                            charges = []
                            arc_ids = []
                            length_m = None
                            if res.status == SolverStatus.OPTIMAL and res.final_label is not None:
                                disc = replay_solution(
                                    inst, res.actions, expected_cost=res.objective
                                )
                                disc_ok = disc.ok
                                crep, extras = continuous_replay_multiroute(
                                    ctx,
                                    inst,
                                    res.actions,
                                    discrete_cost=res.objective,
                                    discrete_t=res.final_label.t,
                                    discrete_E_truck=res.final_label.E_truck,
                                )
                                cont_ok = crep.ok
                                cont_reason = crep.reason
                                length_m = extras.length_m
                                charges = [
                                    {"node": a["node"], "delta_e_kwh": a["delta_e_kwh"]}
                                    for a in res.actions
                                    if a.get("type") == "CHARGE"
                                ]
                                arc_ids = [
                                    a.get("arc_id")
                                    for a in res.actions
                                    if a.get("type") == "DRIVE"
                                ]
                            row = {
                                "row_id": mid,
                                "vehicle_id": vehicle.vehicle_id,
                                "vehicle_key": vkey,
                                "usable_kwh": vehicle.usable_kwh,
                                "installed_kwh": vehicle.installed_kwh,
                                "energy_quantum_kwh": q,
                                "objective_mode": mode,
                                "gcm_label": gcm_label,
                                "gcm_kg": gcm_kg,
                                "mission_id": spec["mission_id"],
                                "od_id": spec["od_id"],
                                "install_set": install_name,
                                "refrigeration_on": spec["refrigeration_on"],
                                "power_source": "A",
                                "refrig_note": "config_A_declared_assumption",
                                "E_truck_init": inst.E_truck_init,
                                "E_truck_min": inst.E_truck_min,
                                "E_truck_cap": inst.E_truck_cap,
                                "road_cost_per_km_cents": ROAD_CENTS_PER_KM,
                                "mrls_status": res.status.value,
                                "objective": res.objective,
                                "enroute_cost": (
                                    res.final_label.cost if res.final_label else None
                                ),
                                "final_E_truck": (
                                    res.final_label.E_truck if res.final_label else None
                                ),
                                "path": "->".join(res.path_nodes) if res.path_nodes else "",
                                "road_distance_m": length_m,
                                "charges_json": json.dumps(charges),
                                "arc_ids_json": json.dumps(arc_ids),
                                "discrete_replay_ok": disc_ok,
                                "continuous_replay_ok": cont_ok,
                                "continuous_replay_reason": cont_reason,
                                "labels_expanded": (
                                    res.stats.get("labels_expanded")
                                    if isinstance(res.stats, dict)
                                    else None
                                ),
                                "prep_sec": prep_s,
                                "solve_sec": solve_s,
                                "station_notes": ";".join(notes),
                                "claim_scope": (
                                    "prospective_vehicle_comparison_path_union_only"
                                ),
                            }
                            rows.append(row)
                            print(
                                f"{mid}: {res.status.value} obj={res.objective} "
                                f"cont={cont_ok}",
                                flush=True,
                            )
    return rows


def run_placement_rows() -> list[dict]:
    cfg = load_multiroute_placement_config(
        ROOT / "configs/optimization/multiroute_placement_pilot.yaml", root=ROOT
    )
    out: list[dict] = []
    for vkey, vpath in VEHICLES.items():
        for mode in ("enroute_incremental_cost", "energy_replenishment_cost"):
            print(f"\n=== placement vehicle={vkey} mode={mode} q=10 ===", flush=True)
            t0 = time.perf_counter()
            context = prepare_multiroute_placement_context(
                cfg,
                root=ROOT,
                demand_name="default",
                energy_quantum_kwh=10,
                objective_mode=mode,
                vehicle_yaml=vpath,
                road_cost_per_km=ROAD_CENTS_PER_KM,
            )
            prep_s = time.perf_counter() - t0
            for bud in cfg.budgets:
                bname = str(bud["name"])
                enum_rows, best, context = run_multiroute_enumeration(
                    cfg,
                    root=ROOT,
                    demand_name="default",
                    capex_name="equal",
                    budget_name=bname,
                    context=context,
                )
                bb, context = run_multiroute_branch_and_bound(
                    cfg,
                    root=ROOT,
                    demand_name="default",
                    capex_name="equal",
                    budget_name=bname,
                    context=context,
                )
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
                out.append(
                    {
                        "vehicle_key": vkey,
                        "vehicle_yaml": str(vpath),
                        "energy_quantum_kwh": 10,
                        "objective_mode": mode,
                        "road_cost_per_km_cents": ROAD_CENTS_PER_KM,
                        "budget_name": bname,
                        "best_sites": ",".join(sorted(inc.site_ids)) if inc else "",
                        "enum_best_sites": (
                            ",".join(sorted(best.site_ids)) if best else ""
                        ),
                        "coverage_serviceable": (
                            None if inc is None else inc.coverage_serviceable
                        ),
                        "weight_total_demand": context.get("weight_total_demand"),
                        "unresolved_weight": context.get("unresolved_weight"),
                        "unresolved_ids": ",".join(sorted(context.get("unresolved_ids") or [])),
                        "secondary_cost": None if inc is None else inc.secondary_cost,
                        "optimality_status": bb.optimality_status.value,
                        "certified_full_portfolio": (
                            bb.optimality_status == OptimalityStatus.CERTIFIED_OPTIMAL
                        ),
                        "enum_agreement": agree,
                        "serviceability_json": json.dumps(context.get("serviceability") or {}),
                        "prep_sec": prep_s,
                        "n_enum_rows": len(enum_rows),
                    }
                )
                print(
                    f"  {bname}: sites={out[-1]['best_sites'] or 'NONE'} "
                    f"status={bb.optimality_status.value} agree={agree}",
                    flush=True,
                )
    return out


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--quanta", default="10,5")
    p.add_argument(
        "--objectives",
        default="enroute_incremental_cost,energy_replenishment_cost",
    )
    p.add_argument("--skip-placement", action="store_true")
    args = p.parse_args()
    quanta = [int(x) for x in str(args.quanta).split(",") if x.strip()]
    objectives = [x.strip() for x in str(args.objectives).split(",") if x.strip()]

    rows = run_routing_rows(quanta=quanta, objectives=objectives)
    out_cmp = ROOT / "results/task06c_vehicle_comparison.csv"
    out_cmp.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(out_cmp, index=False)
    print(f"Wrote {out_cmp} ({len(rows)} rows)", flush=True)

    if not args.skip_placement:
        place = run_placement_rows()
        out_pl = ROOT / "results/task06c_vehicle_placement.csv"
        pd.DataFrame(place).to_csv(out_pl, index=False)
        print(f"Wrote {out_pl} ({len(place)} rows)", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
