#!/usr/bin/env python
"""Task 06D — fair multi-vehicle comparison with immutable GCM / payload / SOC policy."""

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

ROAD_CENTS_PER_KM = 100.0
# Fixed-payload research cargos (equal freight across trucks; GCM differs by curb).
PAYLOAD_LIGHT_KG = 5300.0
PAYLOAD_HEAVY_KG = 20000.0


def _frozen_gcm_levels(cfg) -> dict[str, float]:
    phys = cfg.raw.get("physics") or {}
    return {
        "light": float(phys.get("gcm_kg", 25000.0)),
        "heavy": float(phys.get("gcm_heavy_kg", 40000.0)),
    }


def _mission_specs() -> list[dict]:
    return [
        {
            "mission_id": "casa_marrakech_nochg",
            "od_id": "casa_marrakech",
            "with_chargers": False,
            "refrigeration_on": False,
            "terrain_mode": "flat",
            "weather_id": "cool",
        },
        {
            "mission_id": "casa_marrakech_chg",
            "od_id": "casa_marrakech",
            "with_chargers": True,
            "refrigeration_on": False,
            "terrain_mode": "flat",
            "weather_id": "cool",
        },
        {
            "mission_id": "casa_marrakech_refrig_chg",
            "od_id": "casa_marrakech",
            "with_chargers": True,
            "refrigeration_on": True,
            "terrain_mode": "flat",
            "weather_id": "cool",
        },
        {
            "mission_id": "casa_marrakech_refrig_hot_chg",
            "od_id": "casa_marrakech",
            "with_chargers": True,
            "refrigeration_on": True,
            "terrain_mode": "flat",
            "weather_id": "hot",
        },
        {
            "mission_id": "casa_agadir_nochg",
            "od_id": "casa_agadir",
            "with_chargers": False,
            "refrigeration_on": False,
            "terrain_mode": "flat",
            "weather_id": "cool",
        },
        {
            "mission_id": "casa_agadir_chg",
            "od_id": "casa_agadir",
            "with_chargers": True,
            "refrigeration_on": False,
            "terrain_mode": "flat",
            "weather_id": "cool",
        },
        {
            "mission_id": "casa_agadir_refrig_chg",
            "od_id": "casa_agadir",
            "with_chargers": True,
            "refrigeration_on": True,
            "terrain_mode": "flat",
            "weather_id": "cool",
        },
        {
            "mission_id": "marrakech_agadir_chg",
            "od_id": "marrakech_agadir",
            "with_chargers": True,
            "refrigeration_on": False,
            "terrain_mode": "flat",
            "weather_id": "cool",
        },
    ]


def _mass_scenarios(cfg, vehicle) -> list[dict]:
    levels = _frozen_gcm_levels(cfg)
    out = []
    for label, gcm in levels.items():
        try:
            validate_gcm(gcm, vehicle)
        except ValueError:
            continue
        out.append(
            {
                "comparison_design": "fixed_gcm",
                "gcm_label": label,
                "gcm_requested_kg": float(gcm),
                "cargo_payload_kg": cargo_payload_kg(gcm, vehicle),
            }
        )
    for label, payload in (("payload_light", PAYLOAD_LIGHT_KG), ("payload_heavy", PAYLOAD_HEAVY_KG)):
        gcm = gcm_from_payload(payload, vehicle)
        try:
            validate_gcm(gcm, vehicle)
        except ValueError:
            continue
        out.append(
            {
                "comparison_design": "fixed_payload",
                "gcm_label": label,
                "gcm_requested_kg": float(gcm),
                "cargo_payload_kg": float(payload),
            }
        )
    return out


def _init_policies(vehicle, *, include_equal_kwh: bool) -> list[dict]:
    policies = [
        {"init_policy": "equal_soc_1.0", "soc_frac": 1.0, "E_init_kwh": None},
        {"init_policy": "equal_soc_0.5", "soc_frac": 0.5, "E_init_kwh": None},
    ]
    if include_equal_kwh:
        policies.append(
            {"init_policy": "equal_kwh_200", "soc_frac": None, "E_init_kwh": 200.0}
        )
    resolved = []
    for p in policies:
        if p["E_init_kwh"] is not None:
            e_kwh = float(p["E_init_kwh"])
            soc = e_kwh / float(vehicle.usable_kwh)
        else:
            soc = float(p["soc_frac"])
            e_kwh = soc * float(vehicle.usable_kwh)
        resolved.append({**p, "E_init_kwh_requested": e_kwh, "soc_init_requested": soc})
    return resolved


def run_routing_rows(
    *,
    quanta: list[int],
    objectives: list[str],
    vehicle_order: list[str] | None = None,
) -> list[dict]:
    cfg = load_multiroute_pilot_config(
        ROOT / "configs/optimization/multiroute_pilot.yaml", root=ROOT
    )
    # Freeze base mass levels once — never mutate cfg.gcm_kg in the loop.
    frozen = _frozen_gcm_levels(cfg)
    assert frozen["light"] == 25000.0
    assert frozen["heavy"] == 40000.0
    path_df = pd.read_csv(cfg.path_alternatives_csv)
    path_rows = path_df.to_dict(orient="records")
    rows: list[dict] = []
    order = vehicle_order or list(VEHICLES.keys())

    for vkey in order:
        vpath = VEHICLES[vkey]
        vehicle = load_vehicle(vpath)
        for q in quanta:
            for mode in objectives:
                for mass in _mass_scenarios(cfg, vehicle):
                    # Bound heavy / payload_heavy: q=10 enroute only
                    if mass["gcm_label"] in {"heavy", "payload_heavy"}:
                        if q != 10 or mode != "enroute_incremental_cost":
                            continue
                    # q=5: only fixed_gcm light + equal_soc_1.0 + enroute
                    if q != 10:
                        if not (
                            mass["comparison_design"] == "fixed_gcm"
                            and mass["gcm_label"] == "light"
                            and mode == "enroute_incremental_cost"
                        ):
                            continue
                    # energy_replenishment: fixed_gcm light only (both SOC policies)
                    if mode == "energy_replenishment_cost":
                        if not (
                            mass["comparison_design"] == "fixed_gcm"
                            and mass["gcm_label"] == "light"
                        ):
                            continue
                    include_eq_kwh = (
                        q == 10
                        and mode == "enroute_incremental_cost"
                        and mass["comparison_design"] == "fixed_gcm"
                        and mass["gcm_label"] == "light"
                    )
                    for initp in _init_policies(vehicle, include_equal_kwh=include_eq_kwh):
                        if q != 10 and initp["init_policy"] != "equal_soc_1.0":
                            continue
                        # equal_kwh only on a subset of missions
                        for spec in _mission_specs():
                            if initp["init_policy"] == "equal_kwh_200" and spec[
                                "od_id"
                            ] not in {"casa_marrakech", "casa_agadir"}:
                                continue
                            if mass["gcm_label"] in {"heavy", "payload_heavy"}:
                                if not (
                                    spec["mission_id"].endswith("_nochg")
                                    or spec["refrigeration_on"]
                                ):
                                    continue
                            # Drop hot-weather cell except primary fixed_gcm light equal_soc
                            if spec["weather_id"] == "hot" and not (
                                mass["comparison_design"] == "fixed_gcm"
                                and mass["gcm_label"] == "light"
                                and initp["init_policy"] == "equal_soc_1.0"
                                and mode == "enroute_incremental_cost"
                                and q == 10
                            ):
                                continue
                            # Install fan-out
                            if not spec["with_chargers"]:
                                install_modes = [("none", False, None)]
                            elif (
                                q == 10
                                and mode == "enroute_incremental_cost"
                                and mass["comparison_design"] == "fixed_gcm"
                                and mass["gcm_label"] == "light"
                                and initp["init_policy"] == "equal_soc_1.0"
                            ):
                                install_modes = [
                                    ("none", False, set()),
                                    ("settat_only", True, {"settat_ca"}),
                                    (
                                        "settat_benguerir",
                                        True,
                                        {"settat_ca", "benguerir_ca"},
                                    ),
                                    ("all_compatible", True, None),
                                ]
                            else:
                                install_modes = [
                                    ("none", False, set()),
                                    ("all_compatible", True, None),
                                ]
                            for install_name, with_chg, active_keys in install_modes:
                                mid = (
                                    f"{vkey}|q{q}|{mode}|{mass['comparison_design']}|"
                                    f"{mass['gcm_label']}|{initp['init_policy']}|"
                                    f"{spec['mission_id']}|{install_name}"
                                )
                                t0 = time.perf_counter()
                                try:
                                    # CRITICAL: pass immutable gcm_kg; do not assign cfg.gcm_kg
                                    assert cfg.gcm_kg == frozen["light"], (
                                        f"cfg.gcm_kg leaked to {cfg.gcm_kg}"
                                    )
                                    inst, ctx, notes = build_physics_od_instance(
                                        cfg=cfg,
                                        root=ROOT,
                                        od_id=spec["od_id"],
                                        path_rows=path_rows,
                                        E_truck_init=int(
                                            round(initp["E_init_kwh_requested"])
                                        ),
                                        E_truck_cap=None,
                                        E_truck_min=None,
                                        refrigeration_on=bool(spec["refrigeration_on"]),
                                        weather_id=str(spec["weather_id"]),
                                        with_chargers=bool(with_chg),
                                        energy_quantum_kwh=q,
                                        terrain_mode=str(spec["terrain_mode"]),
                                        objective_mode=mode,
                                        vehicle_yaml=vpath,
                                        road_cost_per_km=ROAD_CENTS_PER_KM,
                                        active_station_keys=active_keys,
                                        gcm_kg=float(mass["gcm_requested_kg"]),
                                    )
                                except Exception as exc:  # noqa: BLE001
                                    rows.append(
                                        {
                                            "experiment_key": mid,
                                            "vehicle_key": vkey,
                                            "vehicle_id": vehicle.vehicle_id,
                                            "status": "BUILD_ERROR",
                                            "error": str(exc),
                                            "gcm_label": mass["gcm_label"],
                                            "gcm_requested_kg": mass["gcm_requested_kg"],
                                            "gcm_realized_kg": None,
                                            "comparison_design": mass[
                                                "comparison_design"
                                            ],
                                        }
                                    )
                                    print(f"{mid}: BUILD_ERROR {exc}", flush=True)
                                    continue
                                if active_keys is not None and with_chg:
                                    inst = clone_physics_instance_for_subset(
                                        inst,
                                        active_stations=set(active_keys)
                                        & set(inst.stations),
                                        name=mid,
                                    )
                                # Assert realized GCM matches request (from builder notes)
                                gcm_note = next(
                                    (
                                        n
                                        for n in notes
                                        if n.startswith("gcm_realized_kg=")
                                    ),
                                    None,
                                )
                                realized = (
                                    float(gcm_note.split("=", 1)[1])
                                    if gcm_note
                                    else float(mass["gcm_requested_kg"])
                                )
                                if abs(realized - float(mass["gcm_requested_kg"])) > 1e-6:
                                    raise AssertionError(
                                        f"GCM mismatch requested={mass['gcm_requested_kg']} "
                                        f"realized={realized}"
                                    )
                                if abs(cfg.gcm_kg - frozen["light"]) > 1e-6:
                                    raise AssertionError(
                                        "Shared cfg.gcm_kg was mutated during build"
                                    )
                                prep_s = time.perf_counter() - t0
                                t1 = time.perf_counter()
                                res = solve_mrls(
                                    inst,
                                    max_seconds=float(
                                        cfg.raw.get("solver", {}).get("max_seconds", 90)
                                    ),
                                    max_expansions=int(
                                        cfg.raw.get("solver", {}).get(
                                            "max_expansions", 800000
                                        )
                                    ),
                                )
                                solve_s = time.perf_counter() - t1
                                disc_ok = cont_ok = False
                                cont_reason = None
                                charges = []
                                length_m = None
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
                                    length_m = extras.length_m
                                    charges = [
                                        {
                                            "node": a["node"],
                                            "delta_e_kwh": a["delta_e_kwh"],
                                        }
                                        for a in res.actions
                                        if a.get("type") == "CHARGE"
                                    ]
                                usable = float(vehicle.usable_kwh)
                                e_final = (
                                    res.final_label.E_truck if res.final_label else None
                                )
                                row = {
                                    "experiment_key": mid,
                                    "vehicle_key": vkey,
                                    "vehicle_id": vehicle.vehicle_id,
                                    "usable_kwh": usable,
                                    "installed_kwh": vehicle.installed_kwh,
                                    "energy_quantum_kwh": q,
                                    "objective_mode": mode,
                                    "comparison_design": mass["comparison_design"],
                                    "gcm_label": mass["gcm_label"],
                                    "gcm_requested_kg": mass["gcm_requested_kg"],
                                    "gcm_realized_kg": realized,
                                    "cargo_payload_kg": mass["cargo_payload_kg"],
                                    "tractor_curb_kg": vehicle.unladen_tractor_kg,
                                    "trailer_curb_kg": vehicle.unladen_trailer_kg,
                                    "init_policy": initp["init_policy"],
                                    "soc_init_requested": initp["soc_init_requested"],
                                    "E_init_kwh_requested": initp[
                                        "E_init_kwh_requested"
                                    ],
                                    "E_truck_init": inst.E_truck_init,
                                    "E_truck_min": inst.E_truck_min,
                                    "E_truck_cap": inst.E_truck_cap,
                                    "soc_init_realized": inst.E_truck_init / usable,
                                    "soc_min": vehicle.soc_min,
                                    "discretization_loss_kwh": usable - inst.E_truck_cap,
                                    "mission_id": spec["mission_id"],
                                    "od_id": spec["od_id"],
                                    "install_set": install_name,
                                    "refrigeration_on": spec["refrigeration_on"],
                                    "weather_id": spec["weather_id"],
                                    "terrain_mode": spec["terrain_mode"],
                                    "power_source": "A",
                                    "refrig_note": "config_A_declared_assumption",
                                    "road_cost_per_km_cents": ROAD_CENTS_PER_KM,
                                    "mrls_status": res.status.value,
                                    "objective": res.objective,
                                    "final_E_truck": e_final,
                                    "soc_final": (
                                        None if e_final is None else e_final / usable
                                    ),
                                    "path": (
                                        "->".join(res.path_nodes)
                                        if res.path_nodes
                                        else ""
                                    ),
                                    "road_distance_m": length_m,
                                    "charges_json": json.dumps(charges),
                                    "charge_kwh_total": sum(
                                        float(c["delta_e_kwh"]) for c in charges
                                    ),
                                    "discrete_replay_ok": disc_ok,
                                    "continuous_replay_ok": cont_ok,
                                    "continuous_replay_reason": cont_reason,
                                    "prep_sec": prep_s,
                                    "solve_sec": solve_s,
                                    "station_notes": ";".join(notes),
                                    "claim_scope": "task06d_fair_vehicle_comparison",
                                    "cfg_gcm_kg_unchanged": cfg.gcm_kg,
                                }
                                rows.append(row)
                                print(
                                    f"{mid}: {res.status.value} obj={res.objective} "
                                    f"gcm={realized} cont={cont_ok}",
                                    flush=True,
                                )
    return rows


def run_placement_rows(
    *,
    demand_name: str = "refrigerated_06d",
    quanta: list[int] | None = None,
) -> list[dict]:
    cfg = load_multiroute_placement_config(
        ROOT / "configs/optimization/multiroute_placement_pilot.yaml", root=ROOT
    )
    quanta = quanta or [10]
    out: list[dict] = []
    for vkey, vpath in VEHICLES.items():
        for q in quanta:
            for mode in ("enroute_incremental_cost", "energy_replenishment_cost"):
                if q != 10 and mode != "enroute_incremental_cost":
                    continue
                if q != 10 and vkey == "volvo_460":
                    continue
                print(
                    f"\n=== placement demand={demand_name} vehicle={vkey} "
                    f"mode={mode} q={q} ===",
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
                    road_cost_per_km=ROAD_CENTS_PER_KM,
                )
                prep_s = time.perf_counter() - t0
                # Record realized GCM from prepared templates
                sample = next(iter(context["prepared"].values()))
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
                    agree = False
                    objective_tie = False
                    if best is not None and inc is not None:
                        objective_tie = (
                            abs(best.coverage_serviceable - inc.coverage_serviceable)
                            <= 1e-9
                            and abs(best.secondary_cost - inc.secondary_cost) <= 1e-6
                        )
                        agree = objective_tie and set(best.site_ids) == set(inc.site_ids)
                    elif best is None and inc is None:
                        agree = True
                        objective_tie = True
                    out.append(
                        {
                            "demand_name": demand_name,
                            "vehicle_key": vkey,
                            "vehicle_yaml": str(vpath),
                            "energy_quantum_kwh": q,
                            "objective_mode": mode,
                            "road_cost_per_km_cents": ROAD_CENTS_PER_KM,
                            "budget_name": bname,
                            "best_sites": (
                                ",".join(sorted(inc.site_ids)) if inc else ""
                            ),
                            "enum_best_sites": (
                                ",".join(sorted(best.site_ids)) if best else ""
                            ),
                            "coverage_serviceable": (
                                None if inc is None else inc.coverage_serviceable
                            ),
                            "weight_total_demand": context.get("weight_total_demand"),
                            "unresolved_weight": context.get("unresolved_weight"),
                            "unresolved_ids": ",".join(
                                sorted(context.get("unresolved_ids") or [])
                            ),
                            "secondary_cost": (
                                None if inc is None else inc.secondary_cost
                            ),
                            "optimality_status": bb.optimality_status.value,
                            "certified_full_portfolio": (
                                bb.optimality_status
                                == OptimalityStatus.CERTIFIED_OPTIMAL
                            ),
                            "enum_agreement": agree,
                            "enum_bb_objective_tie": objective_tie,
                            "n_enum_rows": len(enum_rows),
                            "serviceability_json": json.dumps(
                                context.get("serviceability") or {}
                            ),
                            "sample_gcm_note": ";".join(sample.station_notes),
                            "prep_sec": prep_s,
                            "claim_scope": "task06d_corrected_placement",
                        }
                    )
                    print(
                        f"  {bname}: sites={out[-1]['best_sites'] or 'NONE'} "
                        f"status={bb.optimality_status.value} agree={agree} "
                        f"cov={out[-1]['coverage_serviceable']}",
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
    p.add_argument("--skip-routing", action="store_true")
    p.add_argument("--demand", default="refrigerated_06d")
    p.add_argument("--vehicle-order", default="")
    args = p.parse_args()
    quanta = [int(x) for x in str(args.quanta).split(",") if x.strip()]
    objectives = [x.strip() for x in str(args.objectives).split(",") if x.strip()]
    vorder = [x.strip() for x in str(args.vehicle_order).split(",") if x.strip()] or None

    if not args.skip_routing:
        rows = run_routing_rows(
            quanta=quanta, objectives=objectives, vehicle_order=vorder
        )
        out_cmp = ROOT / "results/task06d_vehicle_comparison.csv"
        out_cmp.parent.mkdir(parents=True, exist_ok=True)
        pd.DataFrame(rows).to_csv(out_cmp, index=False)
        print(f"Wrote {out_cmp} ({len(rows)} rows)", flush=True)
        # Invariant: no light-labeled row with wrong mass for fixed_gcm
        df = pd.DataFrame(rows)
        if not df.empty and "gcm_label" in df.columns:
            bad = df[
                (df["comparison_design"] == "fixed_gcm")
                & (df["gcm_label"] == "light")
                & (df["gcm_realized_kg"] != 25000.0)
            ]
            if len(bad):
                raise SystemExit(f"GCM LEAK DETECTED in {len(bad)} rows")

    if not args.skip_placement:
        place = run_placement_rows(demand_name=args.demand, quanta=[10])
        # Also revalidate legacy default portfolio under immutable GCM
        place += run_placement_rows(demand_name="default", quanta=[10])
        out_pl = ROOT / "results/task06d_vehicle_placement.csv"
        pd.DataFrame(place).to_csv(out_pl, index=False)
        print(f"Wrote {out_pl} ({len(place)} rows)", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
