#!/usr/bin/env python
"""Task 07A — cold-chain benchmark: clean demand, placement, refrigeration energy."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from morocco_etruck.energy.vehicle import (  # noqa: E402
    cargo_payload_kg,
    gcm_from_payload,
    load_vehicle,
    validate_gcm,
)
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
    all_optimal_site_sets,
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
CFG_07A = ROOT / "configs/optimization/multiroute_placement_07a.yaml"
ROAD_CENTS = 100.0
PAYLOAD_KG = 5300.0
PRIMARY_DEMAND = "cold_chain_baseline_07a"
EXPECTED_WEIGHT = 5.5


def run_placement(
    *,
    demand_name: str,
    quanta: list[int],
    objectives: list[str],
    vehicles: dict[str, Path] | None = None,
) -> list[dict]:
    cfg = load_multiroute_placement_config(CFG_07A, root=ROOT)
    missions = cfg.demand_scenarios[demand_name]
    wtot = sum(m.weight for m in missions)
    if abs(wtot - EXPECTED_WEIGHT) > 1e-9:
        raise SystemExit(
            f"Demand weight {wtot} != {EXPECTED_WEIGHT} for {demand_name}"
        )
    # Guard: primary must not contain ablation-off or mixed hot twins
    if demand_name == PRIMARY_DEMAND:
        if any(not m.refrigeration_on for m in missions):
            raise SystemExit("Primary portfolio contains refrigeration OFF mission")
        weathers = {m.weather_id for m in missions}
        if len(weathers) != 1:
            raise SystemExit(f"Primary portfolio mixed weathers: {weathers}")

    out: list[dict] = []
    veh = vehicles or VEHICLES
    for vkey, vpath in veh.items():
        for q in quanta:
            for mode in objectives:
                print(
                    f"\n=== place demand={demand_name} veh={vkey} q={q} mode={mode} ===",
                    flush=True,
                )
                t0 = time.perf_counter()
                context = prepare_multiroute_placement_context(
                    cfg,
                    root=ROOT,
                    demand_name=demand_name,
                    energy_quantum_kwh=q,
                    objective_mode=mode,
                    vehicle_yaml=vpath,
                    road_cost_per_km=ROAD_CENTS,
                )
                prep_s = time.perf_counter() - t0
                infeas_w = sum(
                    float(m.weight)
                    for m in missions
                    if context["serviceability"].get(m.id) == "unserved_all_candidates"
                )
                for bud in cfg.budgets:
                    bname = str(bud["name"])
                    enum_rows, best, context = run_multiroute_enumeration(
                        cfg,
                        root=ROOT,
                        demand_name=demand_name,
                        capex_name="equal",
                        budget_name=bname,
                        context=context,
                    )
                    bb, context = run_multiroute_branch_and_bound(
                        cfg,
                        root=ROOT,
                        demand_name=demand_name,
                        capex_name="equal",
                        budget_name=bname,
                        context=context,
                    )
                    inc = bb.incumbent
                    opt_sets = all_optimal_site_sets(enum_rows)
                    obj_agree = False
                    site_equal = False
                    if best is not None and inc is not None:
                        obj_agree = (
                            abs(best.coverage_serviceable - inc.coverage_serviceable)
                            <= 1e-9
                            and abs(best.secondary_cost - inc.secondary_cost) <= 1e-6
                        )
                        site_equal = set(best.site_ids) == set(inc.site_ids)
                    elif best is None and inc is None:
                        obj_agree = True
                        site_equal = True
                    out.append(
                        {
                            "demand_name": demand_name,
                            "vehicle_key": vkey,
                            "energy_quantum_kwh": q,
                            "objective_mode": mode,
                            "budget_name": bname,
                            "weight_total_demand": context["weight_total_demand"],
                            "coverage_serviceable": (
                                None if inc is None else inc.coverage_serviceable
                            ),
                            "infeasible_under_candidates_weight": infeas_w,
                            "unresolved_weight": context["unresolved_weight"],
                            "unresolved_ids": ",".join(
                                sorted(context.get("unresolved_ids") or [])
                            ),
                            "best_sites_bb": (
                                ",".join(sorted(inc.site_ids)) if inc else ""
                            ),
                            "best_sites_enum": (
                                ",".join(sorted(best.site_ids)) if best else ""
                            ),
                            "secondary_cost": (
                                None if inc is None else inc.secondary_cost
                            ),
                            "objective_agreement": obj_agree,
                            "selected_site_set_equal": site_equal,
                            "all_optimal_site_sets": "|".join(opt_sets),
                            "n_optimal_site_sets": len(opt_sets),
                            "optimality_status": bb.optimality_status.value,
                            "certified_full_portfolio": (
                                bb.optimality_status
                                == OptimalityStatus.CERTIFIED_OPTIMAL
                            ),
                            "serviceability_json": json.dumps(
                                context.get("serviceability") or {}
                            ),
                            "cargo_payload_kg": PAYLOAD_KG,
                            "road_cost_per_km_cents": ROAD_CENTS,
                            "prep_sec": prep_s,
                            "claim_scope": "task07a_cold_chain_benchmark",
                            "site_evidence_class": "hypothetical_future_truck_site",
                        }
                    )
                    print(
                        f"  {bname}: bb={out[-1]['best_sites_bb'] or 'NONE'} "
                        f"opts={opt_sets} obj_agree={obj_agree} "
                        f"cov={out[-1]['coverage_serviceable']} "
                        f"status={bb.optimality_status.value}",
                        flush=True,
                    )
    return out


def run_routing_ablation(*, quanta: list[int]) -> list[dict]:
    """Paired ON/OFF refrigeration routing with energy breakdown (fixed payload)."""
    cfg = load_multiroute_pilot_config(
        ROOT / "configs/optimization/multiroute_pilot.yaml", root=ROOT
    )
    path_rows = pd.read_csv(cfg.path_alternatives_csv).to_dict(orient="records")
    rows: list[dict] = []
    missions = [
        ("casa_marrakech", "cool"),
        ("casa_agadir", "cool"),
        ("casa_marrakech", "hot"),
        ("marrakech_agadir", "cool"),
    ]
    for vkey, vpath in VEHICLES.items():
        vehicle = load_vehicle(vpath)
        gcm = gcm_from_payload(PAYLOAD_KG, vehicle)
        validate_gcm(gcm, vehicle)
        for q in quanta:
            for od_id, weather in missions:
                for soc_frac in (0.5, 1.0):
                    for refrig in (True, False):
                        for install_name, with_chg, active in (
                            ("none", False, None),
                            ("all_compatible", True, None),
                        ):
                            # Bound: full install fan-out only for cool casa_agadir SOC0.5
                            if weather == "hot" and od_id != "casa_marrakech":
                                continue
                            if soc_frac == 1.0 and od_id == "marrakech_agadir":
                                continue
                            mid = (
                                f"{vkey}|q{q}|payload{int(PAYLOAD_KG)}|soc{soc_frac}|"
                                f"{od_id}|{weather}|refrig{int(refrig)}|{install_name}"
                            )
                            e_init = int(round(soc_frac * float(vehicle.usable_kwh)))
                            t0 = time.perf_counter()
                            try:
                                assert abs(cfg.gcm_kg - 25000.0) < 1e-6
                                inst, ctx, notes = build_physics_od_instance(
                                    cfg=cfg,
                                    root=ROOT,
                                    od_id=od_id,
                                    path_rows=path_rows,
                                    E_truck_init=e_init,
                                    refrigeration_on=refrig,
                                    weather_id=weather,
                                    with_chargers=bool(with_chg),
                                    energy_quantum_kwh=q,
                                    terrain_mode="flat",
                                    objective_mode="enroute_incremental_cost",
                                    vehicle_yaml=vpath,
                                    road_cost_per_km=ROAD_CENTS,
                                    active_station_keys=active,
                                    gcm_kg=gcm,
                                )
                            except Exception as exc:  # noqa: BLE001
                                rows.append(
                                    {
                                        "experiment_key": mid,
                                        "status": "BUILD_ERROR",
                                        "error": str(exc),
                                        "vehicle_key": vkey,
                                    }
                                )
                                print(f"{mid}: BUILD_ERROR {exc}", flush=True)
                                continue
                            prep = time.perf_counter() - t0
                            res = solve_mrls(
                                inst,
                                max_seconds=90.0,
                                max_expansions=800_000,
                            )
                            disc_ok = cont_ok = False
                            cont_reason = None
                            extras = None
                            if (
                                res.status == SolverStatus.OPTIMAL
                                and res.final_label is not None
                            ):
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
                            usable = float(vehicle.usable_kwh)
                            row = {
                                "experiment_key": mid,
                                "vehicle_key": vkey,
                                "vehicle_id": vehicle.vehicle_id,
                                "usable_kwh": usable,
                                "energy_quantum_kwh": q,
                                "comparison_design": "fixed_payload",
                                "cargo_payload_kg": PAYLOAD_KG,
                                "gcm_realized_kg": gcm,
                                "payload_implied": cargo_payload_kg(gcm, vehicle),
                                "od_id": od_id,
                                "weather_id": weather,
                                "refrigeration_on": refrig,
                                "power_source": "A",
                                "refrig_note": "config_A_declared_assumption",
                                "init_policy": f"equal_soc_{soc_frac}",
                                "soc_init": soc_frac,
                                "E_truck_init": inst.E_truck_init,
                                "E_truck_cap": inst.E_truck_cap,
                                "E_truck_min": inst.E_truck_min,
                                "install_set": install_name,
                                "mrls_status": res.status.value,
                                "objective": res.objective,
                                "final_E_truck": (
                                    res.final_label.E_truck if res.final_label else None
                                ),
                                "discrete_replay_ok": disc_ok,
                                "continuous_replay_ok": cont_ok,
                                "continuous_replay_reason": cont_reason,
                                "E_traction_kwh": (
                                    None if extras is None else extras.E_traction_kwh
                                ),
                                "E_aux_drive_kwh": (
                                    None if extras is None else extras.E_aux_drive_kwh
                                ),
                                "E_refrig_drive_kwh": (
                                    None if extras is None else extras.E_refrig_drive_kwh
                                ),
                                "E_regen_credit_kwh": (
                                    None if extras is None else extras.E_regen_credit_kwh
                                ),
                                "E_aux_stationary_kwh": (
                                    None
                                    if extras is None
                                    else extras.E_aux_stationary_kwh
                                ),
                                "E_refrig_stationary_kwh": (
                                    None
                                    if extras is None
                                    else extras.E_refrig_stationary_kwh
                                ),
                                "E_refrig_total_kwh": (
                                    None
                                    if extras is None
                                    else extras.E_refrig_drive_kwh
                                    + extras.E_refrig_stationary_kwh
                                ),
                                "charge_kwh_total": (
                                    None if extras is None else extras.charge_kwh_total
                                ),
                                "charge_duration_s": (
                                    None if extras is None else extras.charge_duration_s
                                ),
                                "min_soc": None if extras is None else extras.min_soc,
                                "road_distance_m": (
                                    None if extras is None else extras.length_m
                                ),
                                "prep_sec": prep,
                                "station_notes": ";".join(notes),
                                "cfg_gcm_unchanged": cfg.gcm_kg,
                                "claim_scope": "task07a_refrigeration_ablation",
                            }
                            rows.append(row)
                            print(
                                f"{mid}: {res.status.value} obj={res.objective} "
                                f"E_ref={row['E_refrig_total_kwh']} cont={cont_ok}",
                                flush=True,
                            )
    return rows


def run_sensitivity_subset() -> list[dict]:
    """Targeted uncertainty: hypothetical charger installed power 350 vs 150 kW."""
    cfg = load_multiroute_pilot_config(
        ROOT / "configs/optimization/multiroute_pilot.yaml", root=ROOT
    )
    path_rows = pd.read_csv(cfg.path_alternatives_csv).to_dict(orient="records")
    rows: list[dict] = []
    ch = cfg.raw.setdefault("charger", {})
    base_p = float(ch.get("power_kw", 350.0))
    for vkey, vpath in (("volvo_475", VEHICLES["volvo_475"]), ("eactros_600", VEHICLES["eactros_600"])):
        vehicle = load_vehicle(vpath)
        gcm = gcm_from_payload(PAYLOAD_KG, vehicle)
        for p_kw in (350.0, 150.0):
            mid = f"sens|{vkey}|charger{int(p_kw)}|casa_agadir|soc0.5|refrig1|all"
            ch["power_kw"] = float(p_kw)
            e_init = int(round(0.5 * vehicle.usable_kwh))
            inst, ctx, notes = build_physics_od_instance(
                cfg=cfg,
                root=ROOT,
                od_id="casa_agadir",
                path_rows=path_rows,
                E_truck_init=e_init,
                refrigeration_on=True,
                weather_id="cool",
                with_chargers=True,
                energy_quantum_kwh=10,
                terrain_mode="flat",
                objective_mode="enroute_incremental_cost",
                vehicle_yaml=vpath,
                road_cost_per_km=ROAD_CENTS,
                gcm_kg=gcm,
            )
            res = solve_mrls(inst, max_seconds=90.0, max_expansions=800_000)
            rows.append(
                {
                    "sensitivity_axis": "charger_power_kw",
                    "sensitivity_value": p_kw,
                    "vehicle_key": vkey,
                    "od_id": "casa_agadir",
                    "soc_init": 0.5,
                    "refrigeration_on": True,
                    "mrls_status": res.status.value,
                    "objective": res.objective,
                    "experiment_key": mid,
                    "notes": ";".join(notes),
                    "site_evidence_class": "hypothetical_future_truck_site",
                }
            )
            print(f"{mid}: {res.status.value} obj={res.objective}", flush=True)
    ch["power_kw"] = base_p
    return rows


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--skip-routing", action="store_true")
    p.add_argument("--skip-placement", action="store_true")
    p.add_argument("--skip-sensitivity", action="store_true")
    p.add_argument("--placement-q5", action="store_true", default=True)
    args = p.parse_args()

    if not args.skip_routing:
        # q=10 full ablation pairs; q=5 on cool casa_agadir/casa_marrakech only via filter in runner
        rows = run_routing_ablation(quanta=[10, 5])
        # Keep q=5 rows only for cool CM/CA to bound size — filter after
        df = pd.DataFrame(rows)
        if not df.empty and "energy_quantum_kwh" in df.columns:
            keep = (df.energy_quantum_kwh == 10) | (
                (df.energy_quantum_kwh == 5)
                & (df.od_id.isin(["casa_marrakech", "casa_agadir"]))
                & (df.weather_id == "cool")
            )
            df = df[keep]
        out = ROOT / "results/task07a_refrigerated_routing.csv"
        out.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(out, index=False)
        print(f"Wrote {out} ({len(df)} rows)", flush=True)

    place_rows: list[dict] = []
    if not args.skip_placement:
        # Primary q=10 both modes
        place_rows += run_placement(
            demand_name=PRIMARY_DEMAND,
            quanta=[10],
            objectives=["enroute_incremental_cost", "energy_replenishment_cost"],
        )
        # Ablation + hot at q=10 enroute
        place_rows += run_placement(
            demand_name="cold_chain_no_refrigeration_ablation_07a",
            quanta=[10],
            objectives=["enroute_incremental_cost"],
        )
        place_rows += run_placement(
            demand_name="cold_chain_hot_07a",
            quanta=[10],
            objectives=["enroute_incremental_cost"],
        )
        # q=5 50% SOC charging-constrained (primary, enroute)
        if args.placement_q5:
            try:
                place_rows += run_placement(
                    demand_name=PRIMARY_DEMAND,
                    quanta=[5],
                    objectives=["enroute_incremental_cost"],
                )
            except Exception as exc:  # noqa: BLE001
                place_rows.append(
                    {
                        "demand_name": PRIMARY_DEMAND,
                        "energy_quantum_kwh": 5,
                        "status": "COMPUTATIONAL_BLOCKER",
                        "error": str(exc),
                        "claim_scope": "task07a_q5_blocker",
                    }
                )
                print(f"q=5 placement blocker: {exc}", flush=True)
        outp = ROOT / "results/task07a_placement.csv"
        pd.DataFrame(place_rows).to_csv(outp, index=False)
        print(f"Wrote {outp} ({len(place_rows)} rows)", flush=True)

    if not args.skip_sensitivity:
        sens = run_sensitivity_subset()
        outs = ROOT / "results/task07a_sensitivity.csv"
        pd.DataFrame(sens).to_csv(outs, index=False)
        print(f"Wrote {outs} ({len(sens)} rows)", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
