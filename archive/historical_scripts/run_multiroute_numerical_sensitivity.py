#!/usr/bin/env python
"""Task 06A — energy/time-grid sensitivity + discrete vs continuous feasibility audit."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from morocco_etruck.optimization.arc_preprocessing import simulate_drive_from_soc  # noqa: E402
from morocco_etruck.optimization.label_setting import SolverStatus, solve_mrls  # noqa: E402
from morocco_etruck.optimization.multiroute_adapter import (  # noqa: E402
    build_physics_od_instance,
    load_multiroute_pilot_config,
)
from morocco_etruck.optimization.multiroute_replay import continuous_replay_multiroute  # noqa: E402
from morocco_etruck.optimization.replay import replay_solution  # noqa: E402


def _classify_continuous_paths(ctx, inst) -> dict:
    """Evaluate continuous physics on each macro chain from O without quantization."""
    # Walk every simple DRIVE-only path on the decision graph via DFS of macros.
    succ: dict[str, list] = {}
    for aid, m in ctx.macros_by_arc_id.items():
        succ.setdefault(m.u, []).append((m.v, aid, m))
    best = {
        "continuous_any_ok": False,
        "continuous_best_reason": "no_path",
        "continuous_min_final_soc": None,
        "classification": "unresolved_inputs",
    }
    usable = float(ctx.vehicle.usable_kwh)
    paths_ok = 0
    paths_fail = 0
    peak = 0
    soc_fail = 0
    min_final = None

    def dfs(node: str, soc: float, trailers, visited: set[str]):
        nonlocal paths_ok, paths_fail, peak, soc_fail, min_final
        if node == inst.destination:
            paths_ok += 1
            min_final = soc if min_final is None else min(min_final, soc)
            return
        for v, aid, macro in succ.get(node, []):
            if aid in visited:
                continue
            if ctx.terrain_mode == "dem" and macro.meta.get("dem_ok") is False:
                continue
            ok, _dt, soc2, tr2, reason, _e = simulate_drive_from_soc(
                macro.micro_edges,
                macro.terrain,
                soc0=soc,
                trailer_soc0=trailers,
                vehicle=ctx.vehicle,
                weather=ctx.weather,
                fridge_cfg=ctx.fridge,
                gcm_kg=ctx.gcm_kg,
                refrigeration_on=ctx.refrigeration_on,
                power_source=ctx.power_source,
            )
            if not ok:
                paths_fail += 1
                if reason and "peak_motor" in reason:
                    peak += 1
                else:
                    soc_fail += 1
                continue
            if soc2 < ctx.vehicle.soc_min - 1e-9:
                paths_fail += 1
                soc_fail += 1
                continue
            dfs(v, soc2, tr2, visited | {aid})

    trailer = None
    if inst.E_trailer_init is not None:
        trailer = inst.E_trailer_init / float(ctx.fridge.trailer_usable_kwh)
    dfs(inst.origin, inst.E_truck_init / usable, trailer, set())
    if paths_ok > 0:
        best["continuous_any_ok"] = True
        best["continuous_min_final_soc"] = min_final
        best["continuous_best_reason"] = "ok"
        best["classification"] = "pending_discrete"  # filled by caller
    elif peak > 0 and soc_fail == 0:
        best["classification"] = "peak_motor"
        best["continuous_best_reason"] = "peak_motor"
    elif paths_fail > 0:
        best["classification"] = "physically_infeasible"
        best["continuous_best_reason"] = "soc_or_drive_fail"
    else:
        best["classification"] = "unresolved_inputs"
    best["continuous_paths_ok"] = paths_ok
    best["continuous_paths_fail"] = paths_fail
    return best


def _mission_specs(cfg) -> list[dict]:
    return [
        {
            "mission_id": "casa_marrakech_full_flat_nochg",
            "od_id": "casa_marrakech",
            "E_truck_init": 600,
            "with_chargers": False,
            "refrigeration_on": False,
            "terrain_mode": "flat",
        },
        {
            "mission_id": "casa_marrakech_low_flat_chg",
            "od_id": "casa_marrakech",
            "E_truck_init": 200,
            "with_chargers": True,
            "refrigeration_on": False,
            "terrain_mode": "flat",
        },
        {
            "mission_id": "casa_agadir_full_flat_nochg",
            "od_id": "casa_agadir",
            "E_truck_init": 600,
            "with_chargers": False,
            "refrigeration_on": False,
            "terrain_mode": "flat",
        },
        {
            "mission_id": "casa_agadir_low_flat_chg",
            "od_id": "casa_agadir",
            "E_truck_init": 200,
            "with_chargers": True,
            "refrigeration_on": False,
            "terrain_mode": "flat",
        },
        {
            "mission_id": "casa_marrakech_full_dem_nochg",
            "od_id": "casa_marrakech",
            "E_truck_init": 600,
            "with_chargers": False,
            "refrigeration_on": False,
            "terrain_mode": "dem",
        },
        {
            "mission_id": "casa_marrakech_heavy_refrig_flat",
            "od_id": "casa_marrakech",
            "E_truck_init": 600,
            "with_chargers": False,
            "refrigeration_on": True,
            "terrain_mode": "flat",
            "gcm": "heavy",
        },
    ]


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--config",
        type=Path,
        default=ROOT / "configs/optimization/multiroute_pilot.yaml",
    )
    p.add_argument(
        "--out",
        type=Path,
        default=ROOT / "results/multiroute_numerical_sensitivity.csv",
    )
    args = p.parse_args()
    cfg = load_multiroute_pilot_config(args.config, root=ROOT)
    path_rows = pd.read_csv(cfg.path_alternatives_csv).to_dict(orient="records")

    quantums = [10, 5, 2]
    # Attempt 1 kWh only on Casa→Marrakech full flat
    try_q1_mission = "casa_marrakech_full_flat_nochg"
    rows: list[dict] = []

    for mission in _mission_specs(cfg):
        qs = list(quantums)
        if mission["mission_id"] == try_q1_mission:
            qs.append(1)
        # One time-grid contrast on Casa→Marrakech
        time_steps = [cfg.time_step_min]
        if mission["mission_id"] == "casa_marrakech_full_flat_nochg":
            time_steps = [cfg.time_step_min, 1]

        for q in qs:
            for dt_min in time_steps:
                if dt_min != cfg.time_step_min and q != 10:
                    continue  # keep time contrast small
                gcm_kg = float(
                    cfg.raw.get("physics", {}).get("gcm_heavy_kg", 40000.0)
                    if mission.get("gcm") == "heavy"
                    else cfg.gcm_kg
                )
                prev = cfg.gcm_kg
                prev_dt = cfg.time_step_min
                cfg.gcm_kg = gcm_kg
                cfg.time_step_min = int(dt_min)
                t_prep = time.perf_counter()
                try:
                    inst, ctx, notes = build_physics_od_instance(
                        cfg=cfg,
                        root=ROOT,
                        od_id=mission["od_id"],
                        path_rows=path_rows,
                        E_truck_init=int(mission["E_truck_init"]),
                        E_truck_cap=(
                            None
                            if cfg.raw.get("E_truck_cap") is None
                            else int(cfg.raw.get("E_truck_cap"))
                        ),
                        E_truck_min=(
                            None
                            if cfg.raw.get("E_truck_min") is None
                            else int(cfg.raw.get("E_truck_min"))
                        ),
                        refrigeration_on=bool(mission["refrigeration_on"]),
                        with_chargers=bool(mission["with_chargers"]),
                        energy_quantum_kwh=q,
                        terrain_mode=str(mission["terrain_mode"]),
                    )
                    prep_s = time.perf_counter() - t_prep
                except Exception as exc:  # noqa: BLE001
                    cfg.gcm_kg = prev
                    cfg.time_step_min = prev_dt
                    rows.append(
                        {
                            "mission_id": mission["mission_id"],
                            "od_id": mission["od_id"],
                            "energy_quantum_kwh": q,
                            "time_step_min": dt_min,
                            "mrls_status": "BUILD_ERROR",
                            "error": str(exc),
                            "classification": "unresolved_inputs",
                        }
                    )
                    print(f"{mission['mission_id']} q={q} dt={dt_min}: BUILD_ERROR {exc}", flush=True)
                    continue

                cont_class = _classify_continuous_paths(ctx, inst)
                t0 = time.perf_counter()
                result = solve_mrls(
                    inst,
                    use_dominance=True,
                    max_seconds=float(cfg.raw.get("solver", {}).get("max_seconds", 90)),
                    max_expansions=int(cfg.raw.get("solver", {}).get("max_expansions", 800000)),
                )
                solve_s = time.perf_counter() - t0

                disc_ok = False
                cont_ok = False
                cont_reason = ""
                length_m = None
                charges = []
                final_e = None
                min_soc = None
                if result.status == SolverStatus.OPTIMAL:
                    disc_ok = bool(
                        replay_solution(inst, result.actions, expected_cost=result.objective).ok
                    )
                    crep, extras = continuous_replay_multiroute(
                        ctx,
                        inst,
                        result.actions,
                        discrete_cost=result.objective,
                        discrete_t=result.final_label.t if result.final_label else None,
                        discrete_E_truck=result.final_label.E_truck if result.final_label else None,
                    )
                    cont_ok = bool(crep.ok)
                    cont_reason = crep.reason or ""
                    length_m = extras.length_m
                    charges = extras.charge_events
                    final_e = crep.continuous_E_truck_kwh
                    min_soc = crep.min_soc

                # Classify discrete vs continuous.
                # continuous_any_path_ok is DRIVE-only (no charge); for charger
                # missions it only rules out no-charge physical feasibility.
                classification = cont_class["classification"]
                if result.status == SolverStatus.OPTIMAL and cont_ok:
                    classification = "feasible_discrete_and_continuous"
                elif result.status == SolverStatus.LIMIT_REACHED:
                    classification = "limit_reached"
                elif result.status == SolverStatus.INFEASIBLE:
                    if cont_class["continuous_any_ok"]:
                        classification = "discrete_only_infeasible"
                    elif mission["with_chargers"]:
                        classification = "discrete_or_charge_dependent_infeasible"
                    else:
                        classification = cont_class["classification"]

                row = {
                    "mission_id": mission["mission_id"],
                    "od_id": mission["od_id"],
                    "energy_quantum_kwh": q,
                    "time_step_min": dt_min,
                    "E_truck_init": mission["E_truck_init"],
                    "with_chargers": mission["with_chargers"],
                    "terrain_mode": mission["terrain_mode"],
                    "refrigeration_on": mission["refrigeration_on"],
                    "gcm_kg": gcm_kg,
                    "n_arcs": len(inst.arcs),
                    "mrls_status": result.status.value,
                    "mrls_objective": result.objective,
                    "path": "->".join(result.path_nodes),
                    "road_distance_m": length_m,
                    "charge_events_json": json.dumps(charges),
                    "final_E_truck_kwh": final_e,
                    "min_soc": min_soc,
                    "discrete_replay_ok": disc_ok,
                    "continuous_replay_ok": cont_ok,
                    "continuous_replay_reason": cont_reason,
                    "continuous_any_path_ok": cont_class["continuous_any_ok"],
                    "continuous_paths_ok": cont_class.get("continuous_paths_ok"),
                    "continuous_paths_fail": cont_class.get("continuous_paths_fail"),
                    "classification": classification,
                    "labels_expanded": getattr(result.stats, "expanded", None)
                    if result.stats
                    else None,
                    "prep_sec": prep_s,
                    "solve_sec": solve_s,
                    "station_notes": ";".join(notes),
                    "dem_complete": ctx.dem_complete,
                    "claim_scope": "path_union_numerical_sensitivity_06a",
                }
                rows.append(row)
                print(
                    f"{mission['mission_id']} q={q} dt={dt_min}: "
                    f"{result.status.value} class={classification} "
                    f"prep={prep_s:.1f}s solve={solve_s:.2f}s",
                    flush=True,
                )
                cfg.gcm_kg = prev
                cfg.time_step_min = prev_dt

                # Bail on 1 kWh if too slow
                if q == 1 and (prep_s + solve_s) > 600:
                    print("Stopping further 1 kWh experiments (wall-time limit).", flush=True)
                    break

    args.out.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(args.out, index=False)
    print(f"Wrote {args.out} ({len(rows)} rows)", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
