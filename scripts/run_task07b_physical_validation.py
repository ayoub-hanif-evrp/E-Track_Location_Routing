#!/usr/bin/env python
"""Task 07B — physical realism: DEM, thermal ladder, deadlines, q-grid, baselines."""

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

from morocco_etruck.energy.transitions import EnergyState, apply_drive  # noqa: E402
from morocco_etruck.energy.vehicle import (  # noqa: E402
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
CFG_07B = ROOT / "configs/optimization/multiroute_placement_07b.yaml"
ROAD_CENTS = 100.0
PAYLOAD_KG = 5300.0
EXPECTED_WEIGHT = 5.5
DT_MIN = 5

THERMAL = {
    "thermal_low": ROOT / "configs/energy/task07b_thermal_low.yaml",
    "thermal_nominal": ROOT / "configs/energy/task07b_thermal_nominal.yaml",
    "thermal_high": ROOT / "configs/energy/task07b_thermal_high.yaml",
    "thermal_summer": ROOT / "configs/energy/task07b_thermal_summer.yaml",
    "thermal_infiltration_assumed": ROOT
    / "configs/energy/task07b_thermal_infiltration_assumed.yaml",
    "thermal_off": None,  # refrigeration_on=False; fridge YAML unused
}

PLACEMENT_PANEL = [
    {
        "cell": "P0",
        "demand": "cold_chain_baseline_07b_flat",
        "terrain": "flat",
        "thermal": "thermal_nominal",
        "q": 10,
        "deadline_h": 20.0,
        "charger_kw": 350.0,
    },
    {
        "cell": "P1",
        "demand": "cold_chain_baseline_07b_dem",
        "terrain": "dem",
        "thermal": "thermal_nominal",
        "q": 10,
        "deadline_h": 20.0,
        "charger_kw": 350.0,
    },
    {
        "cell": "P2",
        "demand": "cold_chain_baseline_07b_dem",
        "terrain": "dem",
        "thermal": "thermal_high",
        "q": 10,
        "deadline_h": 20.0,
        "charger_kw": 350.0,
    },
    {
        "cell": "P3",
        "demand": "cold_chain_baseline_07b_dem",
        "terrain": "dem",
        "thermal": "thermal_nominal",
        "q": 5,
        "deadline_h": 20.0,
        "charger_kw": 350.0,
    },
    {
        "cell": "P4",
        "demand": "cold_chain_baseline_07b_dem",
        "terrain": "dem",
        "thermal": "thermal_nominal",
        "q": 10,
        "deadline_h": 12.0,
        "charger_kw": 350.0,
    },
    {
        "cell": "P5",
        "demand": "cold_chain_baseline_07b_dem",
        "terrain": "dem",
        "thermal": "thermal_nominal",
        "q": 10,
        "deadline_h": 12.0,
        "charger_kw": 150.0,
    },
]


def _hours_to_steps(hours: float) -> int:
    return int(round(hours * 60.0 / DT_MIN))


def _assert_dem_meta() -> dict[str, Any]:
    meta_path = ROOT / "data/processed/multiroute/elevation/dem_sampling_meta.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    arcs = meta.get("arcs") or {}
    blockers = meta.get("blockers") or []
    bad = [
        k
        for k, v in arcs.items()
        if str(v.get("quality")) != "valid" or str(v.get("source")) != "copdem_glo30"
    ]
    if blockers or bad:
        raise SystemExit(
            f"DEM incomplete: blockers={blockers} bad_arcs={bad[:5]}"
        )
    ods = {"casa_marrakech", "casa_agadir", "marrakech_agadir"}
    covered = {str(v.get("od_id")) for v in arcs.values()}
    if not ods.issubset(covered):
        raise SystemExit(f"DEM missing ODs: {ods - covered}")
    return meta


def _shortest_node_path(inst) -> list[str] | None:
    """Dijkstra on road_cost (cents) over decision arcs; prefer arc length via road_cost."""
    from collections import defaultdict
    import heapq

    graph: dict[str, list[tuple[str, int, Any]]] = defaultdict(list)
    for a in inst.arcs:
        graph[a.u].append((a.v, int(a.road_cost), a))
    origin, dest = inst.origin, inst.destination
    pq = [(0, origin, [origin], [])]
    seen: dict[str, int] = {}
    while pq:
        cost, node, path, arcs = heapq.heappop(pq)
        if node in seen and seen[node] <= cost:
            continue
        seen[node] = cost
        if node == dest:
            return path
        for v, rc, arc in graph[node]:
            heapq.heappush(pq, (cost + rc, v, path + [v], arcs + [arc]))
    return None


def _continuous_shortest_feasibility(
    *,
    inst,
    ctx,
    soc_init: float,
) -> dict[str, Any]:
    """Continuous physics along shortest road-cost path — independent of MRLS grid."""
    if ctx.terrain_mode == "dem" and not ctx.dem_complete:
        return {
            "continuous_feasible": None,
            "classification_hint": "dem_incomplete",
            "reason": "dem_incomplete",
            "terminal_soc": None,
            "drive_time_s": None,
            "length_m": None,
        }
    path = _shortest_node_path(inst)
    if not path or len(path) < 2:
        return {
            "continuous_feasible": False,
            "classification_hint": "unresolved",
            "reason": "no_shortest_path",
            "terminal_soc": None,
            "drive_time_s": None,
            "length_m": None,
        }
    # Map consecutive nodes to a macro (prefer matching arc_id on instance arcs)
    node_arcs = {(a.u, a.v): a for a in inst.arcs}
    state = EnergyState(soc=float(soc_init), trailer_soc=None)
    t_s = 0.0
    length = 0.0
    e_trac = e_aux = e_ref = e_regen = 0.0
    for u, v in zip(path[:-1], path[1:]):
        arc = node_arcs.get((u, v))
        if arc is None or not arc.arc_id:
            return {
                "continuous_feasible": None,
                "classification_hint": "unresolved",
                "reason": f"missing_arc:{u}->{v}",
                "terminal_soc": state.soc,
                "drive_time_s": t_s,
                "length_m": length,
            }
        macro = ctx.macros_by_arc_id.get(str(arc.arc_id))
        if macro is None:
            return {
                "continuous_feasible": None,
                "classification_hint": "unresolved",
                "reason": f"missing_macro:{arc.arc_id}",
                "terminal_soc": state.soc,
                "drive_time_s": t_s,
                "length_m": length,
            }
        if ctx.terrain_mode == "dem" and macro.meta.get("dem_ok") is False:
            return {
                "continuous_feasible": None,
                "classification_hint": "dem_incomplete",
                "reason": "dem_incomplete_macro",
                "terminal_soc": state.soc,
                "drive_time_s": t_s,
                "length_m": length,
            }
        s_cursor = 0.0
        for edge in macro.micro_edges:
            tr = apply_drive(
                state,
                edge,
                vehicle=ctx.vehicle,
                weather=ctx.weather,
                fridge_cfg=ctx.fridge,
                gcm_kg=ctx.gcm_kg,
                refrigeration_on=ctx.refrigeration_on,
                power_source=ctx.power_source,
                terrain=macro.terrain,
                s_cursor_m=s_cursor,
                speed_mps=edge.speed_mps if getattr(edge, "speed_mps", None) else None,
            )
            t_s += tr.dt_s
            length += tr.length_m
            s_cursor += edge.length_m
            e_trac += tr.E_traction_j / 3.6e6
            e_aux += tr.E_aux_j / 3.6e6
            e_ref += tr.E_refrig_j / 3.6e6
            if tr.E_traction_j < 0:
                e_regen += abs(tr.E_traction_j) / 3.6e6
            if tr.violation_reason == "peak_motor_power_exceeded":
                return {
                    "continuous_feasible": False,
                    "classification_hint": "peak_motor",
                    "reason": tr.violation_reason,
                    "terminal_soc": tr.next_state.soc,
                    "drive_time_s": t_s,
                    "length_m": length,
                    "E_traction_kwh": e_trac,
                    "E_aux_drive_kwh": e_aux,
                    "E_refrig_drive_kwh": e_ref,
                    "E_regen_credit_kwh": e_regen,
                }
            if not tr.soc_feasible:
                return {
                    "continuous_feasible": False,
                    "classification_hint": "physical_infeasible",
                    "reason": tr.violation_reason or "tractor_soc_floor",
                    "terminal_soc": tr.next_state.soc,
                    "drive_time_s": t_s,
                    "length_m": length,
                    "E_traction_kwh": e_trac,
                    "E_aux_drive_kwh": e_aux,
                    "E_refrig_drive_kwh": e_ref,
                    "E_regen_credit_kwh": e_regen,
                }
            state = tr.next_state
    return {
        "continuous_feasible": True,
        "classification_hint": "continuous_ok",
        "reason": None,
        "terminal_soc": state.soc,
        "drive_time_s": t_s,
        "length_m": length,
        "E_traction_kwh": e_trac,
        "E_aux_drive_kwh": e_aux,
        "E_refrig_drive_kwh": e_ref,
        "E_regen_credit_kwh": e_regen,
    }


def _classify_discrete_vs_continuous(
    *,
    continuous_ok: bool | None,
    cont_hint: str,
    mrls_status: str,
    discrete_ok: bool,
) -> str:
    if cont_hint in {"dem_incomplete", "unresolved"}:
        return cont_hint
    if continuous_ok is False and cont_hint == "peak_motor":
        return "peak_motor"
    if continuous_ok is False:
        return "physical_infeasible"
    # continuous OK
    if mrls_status == "OPTIMAL" and discrete_ok:
        return "discrete_feasible"
    if mrls_status in {"INFEASIBLE", "OPTIMAL"} and not discrete_ok:
        # OPTIMAL but replay fail, or INFEASIBLE while continuous OK
        if mrls_status == "INFEASIBLE":
            return "discrete_grid_reject"
        return "quantization_capacity_loss"
    if mrls_status == "LIMIT_REACHED":
        return "unresolved"
    return "unresolved"


def _run_one_routing(
    *,
    cfg,
    path_rows: list[dict],
    vkey: str,
    vpath: Path,
    od_id: str,
    terrain_mode: str,
    thermal_id: str,
    weather_id: str,
    refrigeration_on: bool,
    q: int,
    soc_frac: float,
    install_name: str,
    with_chg: bool,
    active: set[str] | None,
    deadline_h: float,
    charger_kw: float,
    max_alts: int | None,
    experiment_tag: str,
) -> dict[str, Any]:
    vehicle = load_vehicle(vpath)
    gcm = gcm_from_payload(PAYLOAD_KG, vehicle)
    validate_gcm(gcm, vehicle)
    e_init = int(round(soc_frac * float(vehicle.usable_kwh)))
    fridge = THERMAL[thermal_id]
    dl = _hours_to_steps(deadline_h)
    mid = (
        f"{experiment_tag}|{vkey}|q{q}|{od_id}|{terrain_mode}|{thermal_id}|"
        f"soc{soc_frac}|dl{deadline_h:g}h|chg{int(charger_kw)}|{install_name}"
    )
    t0 = time.perf_counter()
    try:
        assert abs(cfg.gcm_kg - 25000.0) < 1e-6
        inst, ctx, notes = build_physics_od_instance(
            cfg=cfg,
            root=ROOT,
            od_id=od_id,
            path_rows=path_rows,
            E_truck_init=e_init,
            refrigeration_on=refrigeration_on,
            weather_id=weather_id,
            with_chargers=bool(with_chg),
            energy_quantum_kwh=q,
            terrain_mode=terrain_mode,
            objective_mode="enroute_incremental_cost",
            vehicle_yaml=vpath,
            road_cost_per_km=ROAD_CENTS,
            active_station_keys=active,
            gcm_kg=gcm,
            deadline_steps=dl,
            fridge_yaml=fridge,
            charger_power_kw=charger_kw,
            max_alternatives_for_union=max_alts,
        )
    except Exception as exc:  # noqa: BLE001
        return {
            "experiment_key": mid,
            "status": "BUILD_ERROR",
            "error": str(exc),
            "vehicle_key": vkey,
            "od_id": od_id,
            "terrain_mode": terrain_mode,
            "thermal_id": thermal_id,
        }
    if terrain_mode == "dem" and not ctx.dem_complete:
        return {
            "experiment_key": mid,
            "status": "dem_incomplete",
            "vehicle_key": vkey,
            "od_id": od_id,
            "terrain_mode": terrain_mode,
            "thermal_id": thermal_id,
            "dem_complete": False,
            "station_notes": ";".join(notes),
        }
    cont = _continuous_shortest_feasibility(inst=inst, ctx=ctx, soc_init=soc_frac)
    res = solve_mrls(inst, max_seconds=90.0, max_expansions=800_000)
    disc_ok = cont_ok = False
    cont_reason = None
    extras = None
    drive_time_s = charge_dur_s = stopped_s = journey_s = arrival_margin_s = None
    terminal_soc = None
    if res.status == SolverStatus.OPTIMAL and res.final_label is not None:
        disc = replay_solution(inst, res.actions, expected_cost=res.objective)
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
        if extras is not None:
            charge_dur_s = extras.charge_duration_s
            drive_time_s = float(res.final_label.t) * DT_MIN * 60.0 - float(
                charge_dur_s or 0.0
            )
            # Approximate: discrete time is total journey; charge is stopped charging
            journey_s = float(res.final_label.t) * DT_MIN * 60.0
            stopped_s = float(charge_dur_s or 0.0)
            drive_time_s = max(0.0, journey_s - stopped_s)
            arrival_margin_s = float(dl) * DT_MIN * 60.0 - journey_s
            terminal_soc = float(res.final_label.E_truck) / float(vehicle.usable_kwh)
    row = {
        "experiment_key": mid,
        "experiment_tag": experiment_tag,
        "vehicle_key": vkey,
        "usable_kwh": float(vehicle.usable_kwh),
        "energy_quantum_kwh": q,
        "cargo_payload_kg": PAYLOAD_KG,
        "gcm_realized_kg": gcm,
        "od_id": od_id,
        "terrain_mode": terrain_mode,
        "dem_complete": ctx.dem_complete,
        "thermal_id": thermal_id,
        "weather_id": weather_id,
        "refrigeration_on": refrigeration_on,
        "soc_init": soc_frac,
        "deadline_hours": deadline_h,
        "deadline_steps": dl,
        "charger_power_kw": charger_kw,
        "max_alternatives_for_union": max_alts,
        "install_set": install_name,
        "mrls_status": res.status.value,
        "objective": res.objective,
        "final_E_truck": res.final_label.E_truck if res.final_label else None,
        "final_t_steps": res.final_label.t if res.final_label else None,
        "discrete_replay_ok": disc_ok,
        "continuous_replay_ok": cont_ok,
        "continuous_replay_reason": cont_reason,
        "shortest_continuous_feasible": cont.get("continuous_feasible"),
        "shortest_continuous_reason": cont.get("reason"),
        "shortest_continuous_hint": cont.get("classification_hint"),
        "shortest_terminal_soc": cont.get("terminal_soc"),
        "shortest_drive_time_s": cont.get("drive_time_s"),
        "shortest_length_m": cont.get("length_m"),
        "E_traction_kwh": None if extras is None else extras.E_traction_kwh,
        "E_aux_drive_kwh": None if extras is None else extras.E_aux_drive_kwh,
        "E_refrig_drive_kwh": None if extras is None else extras.E_refrig_drive_kwh,
        "E_regen_credit_kwh": None if extras is None else extras.E_regen_credit_kwh,
        "E_aux_stationary_kwh": None if extras is None else extras.E_aux_stationary_kwh,
        "E_refrig_stationary_kwh": (
            None if extras is None else extras.E_refrig_stationary_kwh
        ),
        "E_refrig_total_kwh": (
            None
            if extras is None
            else extras.E_refrig_drive_kwh + extras.E_refrig_stationary_kwh
        ),
        "charge_kwh_total": None if extras is None else extras.charge_kwh_total,
        "charge_duration_s": charge_dur_s,
        "drive_time_s": drive_time_s,
        "stopped_time_s": stopped_s,
        "total_journey_time_s": journey_s,
        "arrival_margin_s": arrival_margin_s,
        "terminal_soc": terminal_soc,
        "min_soc": None if extras is None else extras.min_soc,
        "road_distance_m": None if extras is None else extras.length_m,
        "prep_sec": time.perf_counter() - t0,
        "station_notes": ";".join(notes),
        "cfg_gcm_unchanged": cfg.gcm_kg,
        "claim_scope": "task07b_physical_validation",
    }
    # Fill traction from continuous shortest when no MRLS solution
    if extras is None and cont.get("E_traction_kwh") is not None:
        row["E_traction_kwh"] = cont.get("E_traction_kwh")
        row["E_aux_drive_kwh"] = cont.get("E_aux_drive_kwh")
        row["E_refrig_drive_kwh"] = cont.get("E_refrig_drive_kwh")
        row["E_regen_credit_kwh"] = cont.get("E_regen_credit_kwh")
        row["road_distance_m"] = cont.get("length_m")
    print(
        f"{mid}: {res.status.value} obj={res.objective} "
        f"cont_short={cont.get('continuous_feasible')} "
        f"E_ref={row.get('E_refrig_total_kwh')}",
        flush=True,
    )
    return row


def run_physical_sensitivity() -> list[dict]:
    """Stages 2–3: matched Flat vs DEM + thermal ladder energy breakdown."""
    _assert_dem_meta()
    cfg = load_multiroute_pilot_config(
        ROOT / "configs/optimization/multiroute_pilot.yaml", root=ROOT
    )
    path_rows = pd.read_csv(cfg.path_alternatives_csv).to_dict(orient="records")
    rows: list[dict] = []
    ods = ["casa_marrakech", "casa_agadir", "marrakech_agadir"]
    for vkey in ("eactros_600", "volvo_475"):
        for terrain in ("flat", "dem"):
            for thermal_id, fridge in THERMAL.items():
                weather = "hot" if thermal_id == "thermal_summer" else "cool"
                refrig = thermal_id != "thermal_off"
                for od_id in ods:
                    for install_name, with_chg, active in (
                        ("none", False, None),
                        ("all_compatible", True, None),
                    ):
                        # Bound: infiltration + summer only on CM/CA, none+all
                        if thermal_id in {
                            "thermal_infiltration_assumed",
                            "thermal_summer",
                            "thermal_low",
                        } and od_id == "marrakech_agadir":
                            continue
                        rows.append(
                            _run_one_routing(
                                cfg=cfg,
                                path_rows=path_rows,
                                vkey=vkey,
                                vpath=VEHICLES[vkey],
                                od_id=od_id,
                                terrain_mode=terrain,
                                thermal_id=thermal_id,
                                weather_id=weather,
                                refrigeration_on=refrig,
                                q=10,
                                soc_frac=0.5,
                                install_name=install_name,
                                with_chg=with_chg,
                                active=active,
                                deadline_h=20.0,
                                charger_kw=350.0,
                                max_alts=None,
                                experiment_tag="phys_sens",
                            )
                        )
    return rows


def run_charging_duration() -> list[dict]:
    """Stage 4: 150 vs 350 kW durations + deadline ladder after min-journey check."""
    cfg = load_multiroute_pilot_config(
        ROOT / "configs/optimization/multiroute_pilot.yaml", root=ROOT
    )
    path_rows = pd.read_csv(cfg.path_alternatives_csv).to_dict(orient="records")
    rows: list[dict] = []
    for vkey in ("eactros_600", "volvo_475"):
        for terrain in ("flat", "dem"):
            for p_kw in (350.0, 150.0):
                # Loose deadline first to measure physical journey
                base = _run_one_routing(
                    cfg=cfg,
                    path_rows=path_rows,
                    vkey=vkey,
                    vpath=VEHICLES[vkey],
                    od_id="casa_agadir",
                    terrain_mode=terrain,
                    thermal_id="thermal_nominal",
                    weather_id="cool",
                    refrigeration_on=True,
                    q=10,
                    soc_frac=0.5,
                    install_name="all_compatible",
                    with_chg=True,
                    active=None,
                    deadline_h=20.0,
                    charger_kw=p_kw,
                    max_alts=None,
                    experiment_tag="charge_dur",
                )
                rows.append(base)
                journey_h = None
                if base.get("total_journey_time_s") is not None:
                    journey_h = float(base["total_journey_time_s"]) / 3600.0
                elif base.get("shortest_drive_time_s") is not None:
                    # No charge solution — use continuous drive + battery-side charge estimate
                    usable = float(load_vehicle(VEHICLES[vkey]).usable_kwh)
                    need = max(0.0, 0.5 * usable)  # rough: half pack refill upper bound
                    charge_h = need / (p_kw * 0.95) if p_kw > 0 else 999.0
                    journey_h = float(base["shortest_drive_time_s"]) / 3600.0 + charge_h
                for dl_h in (8.0, 10.0, 12.0, 20.0):
                    if dl_h >= 20.0 and p_kw == 350.0:
                        continue  # already have 20h@350 from base for both powers
                    if journey_h is not None and dl_h + 1e-9 < journey_h:
                        rows.append(
                            {
                                "experiment_key": (
                                    f"charge_dur|{vkey}|q10|casa_agadir|{terrain}|"
                                    f"thermal_nominal|soc0.5|dl{dl_h:g}h|"
                                    f"chg{int(p_kw)}|all_compatible"
                                ),
                                "experiment_tag": "charge_dur",
                                "vehicle_key": vkey,
                                "od_id": "casa_agadir",
                                "terrain_mode": terrain,
                                "thermal_id": "thermal_nominal",
                                "deadline_hours": dl_h,
                                "charger_power_kw": p_kw,
                                "status": "deadline_physically_impossible",
                                "min_physical_journey_h": journey_h,
                                "mrls_status": "SKIPPED",
                                "claim_scope": "task07b_deadline_physics_gate",
                            }
                        )
                        print(
                            f"deadline_physically_impossible dl={dl_h}h "
                            f"< journey~{journey_h:.2f}h p={p_kw}",
                            flush=True,
                        )
                        continue
                    if dl_h == 20.0 and abs(p_kw - float(base.get("charger_power_kw") or 0)) < 1e-6:
                        continue
                    rows.append(
                        _run_one_routing(
                            cfg=cfg,
                            path_rows=path_rows,
                            vkey=vkey,
                            vpath=VEHICLES[vkey],
                            od_id="casa_agadir",
                            terrain_mode=terrain,
                            thermal_id="thermal_nominal",
                            weather_id="cool",
                            refrigeration_on=True,
                            q=10,
                            soc_frac=0.5,
                            install_name="all_compatible",
                            with_chg=True,
                            active=None,
                            deadline_h=dl_h,
                            charger_kw=p_kw,
                            max_alts=None,
                            experiment_tag="charge_dur",
                        )
                    )
    return rows


def run_discretization_diagnostics() -> list[dict]:
    """Stage 5: eActros CM SOC0.5 no-charger q=10/5/2 vs continuous."""
    cfg = load_multiroute_pilot_config(
        ROOT / "configs/optimization/multiroute_pilot.yaml", root=ROOT
    )
    path_rows = pd.read_csv(cfg.path_alternatives_csv).to_dict(orient="records")
    rows: list[dict] = []
    for terrain in ("flat", "dem"):
        for q in (10, 5, 2):
            row = _run_one_routing(
                cfg=cfg,
                path_rows=path_rows,
                vkey="eactros_600",
                vpath=VEHICLES["eactros_600"],
                od_id="casa_marrakech",
                terrain_mode=terrain,
                thermal_id="thermal_nominal",
                weather_id="cool",
                refrigeration_on=True,
                q=q,
                soc_frac=0.5,
                install_name="none",
                with_chg=False,
                active=None,
                deadline_h=20.0,
                charger_kw=350.0,
                max_alts=None,
                experiment_tag="disc_diag",
            )
            row["discrete_vs_continuous_class"] = _classify_discrete_vs_continuous(
                continuous_ok=row.get("shortest_continuous_feasible"),
                cont_hint=str(row.get("shortest_continuous_hint") or "unresolved"),
                mrls_status=str(row.get("mrls_status") or ""),
                discrete_ok=bool(row.get("discrete_replay_ok")),
            )
            rows.append(row)
    return rows


def run_routing_baselines() -> list[dict]:
    """Stage 6: comparable baselines A–E under DEM+nominal (fallback flat)."""
    cfg = load_multiroute_pilot_config(
        ROOT / "configs/optimization/multiroute_pilot.yaml", root=ROOT
    )
    path_rows = pd.read_csv(cfg.path_alternatives_csv).to_dict(orient="records")
    terrain = "dem"
    # Probe DEM build once
    probe = _run_one_routing(
        cfg=cfg,
        path_rows=path_rows,
        vkey="eactros_600",
        vpath=VEHICLES["eactros_600"],
        od_id="casa_agadir",
        terrain_mode="dem",
        thermal_id="thermal_nominal",
        weather_id="cool",
        refrigeration_on=True,
        q=10,
        soc_frac=0.5,
        install_name="none",
        with_chg=False,
        active=None,
        deadline_h=20.0,
        charger_kw=350.0,
        max_alts=1,
        experiment_tag="baseline_probe",
    )
    if probe.get("status") == "dem_incomplete" or probe.get("dem_complete") is False:
        terrain = "flat"
    rows: list[dict] = []
    installs = {
        "A": ("none", False, None, 1),  # shortest, no chargers
        "B": ("settat_benguerir", True, {"settat_ca", "benguerir_ca"}, 1),
        "C": ("settat_benguerir", True, {"settat_ca", "benguerir_ca"}, 1),  # fixed-route MRLS
        "D_none": ("none", False, None, None),
        "D_settat": ("settat_only", True, {"settat_ca"}, None),
        "D_benguerir": ("benguerir_only", True, {"benguerir_ca"}, None),
        "D_both": ("settat_benguerir", True, {"settat_ca", "benguerir_ca"}, None),
    }
    for vkey in ("eactros_600", "volvo_475"):
        for od_id in ("casa_marrakech", "casa_agadir", "marrakech_agadir"):
            for bid, (iname, with_chg, active, max_alts) in installs.items():
                row = _run_one_routing(
                    cfg=cfg,
                    path_rows=path_rows,
                    vkey=vkey,
                    vpath=VEHICLES[vkey],
                    od_id=od_id,
                    terrain_mode=terrain,
                    thermal_id="thermal_nominal",
                    weather_id="cool",
                    refrigeration_on=True,
                    q=10,
                    soc_frac=0.5,
                    install_name=iname,
                    with_chg=with_chg,
                    active=active,
                    deadline_h=20.0,
                    charger_kw=350.0,
                    max_alts=max_alts,
                    experiment_tag=f"baseline_{bid[0] if bid[0] in 'ABCDE' else bid}",
                )
                row["baseline_id"] = bid.split("_")[0] if bid.startswith("D_") else bid
                row["baseline_detail"] = bid
                row["panel_terrain"] = terrain
                rows.append(row)
    return rows


def run_placement_panel(
    *,
    cells: list[str] | None = None,
    vehicles: list[str] | None = None,
) -> list[dict]:
    """Stages 2/7 placement robustness matrix P0–P5."""
    _assert_dem_meta()
    cfg = load_multiroute_placement_config(CFG_07B, root=ROOT)
    out: list[dict] = []
    veh = vehicles or ["eactros_600", "volvo_475"]
    for panel in PLACEMENT_PANEL:
        if cells and panel["cell"] not in cells:
            continue
        demand = panel["demand"]
        missions = cfg.demand_scenarios[demand]
        wtot = sum(m.weight for m in missions)
        if abs(wtot - EXPECTED_WEIGHT) > 1e-9:
            raise SystemExit(f"Demand weight {wtot} != {EXPECTED_WEIGHT}")
        fridge = THERMAL[panel["thermal"]]
        dl = _hours_to_steps(float(panel["deadline_h"]))
        for vkey in veh:
            vpath = VEHICLES[vkey]
            print(
                f"\n=== place {panel['cell']} veh={vkey} q={panel['q']} "
                f"terrain={panel['terrain']} thermal={panel['thermal']} "
                f"dl={panel['deadline_h']}h p={panel['charger_kw']} ===",
                flush=True,
            )
            t0 = time.perf_counter()
            try:
                context = prepare_multiroute_placement_context(
                    cfg,
                    root=ROOT,
                    demand_name=demand,
                    energy_quantum_kwh=int(panel["q"]),
                    objective_mode="enroute_incremental_cost",
                    vehicle_yaml=vpath,
                    road_cost_per_km=ROAD_CENTS,
                    deadline_steps=dl,
                    fridge_yaml=fridge,
                    charger_power_kw=float(panel["charger_kw"]),
                )
            except Exception as exc:  # noqa: BLE001
                out.append(
                    {
                        "panel_cell": panel["cell"],
                        "vehicle_key": vkey,
                        "status": "BUILD_ERROR",
                        "error": str(exc),
                        "demand_name": demand,
                    }
                )
                print(f"BUILD_ERROR: {exc}", flush=True)
                continue
            # DEM gate: any prepared mission incomplete → unresolved
            dem_bad = []
            for mid, prep in context["prepared"].items():
                if (
                    str(prep.mission.terrain_mode) == "dem"
                    and not prep.ctx.dem_complete
                ):
                    dem_bad.append(mid)
            if dem_bad:
                out.append(
                    {
                        "panel_cell": panel["cell"],
                        "vehicle_key": vkey,
                        "status": "dem_incomplete",
                        "unresolved_ids": ",".join(dem_bad),
                        "demand_name": demand,
                        "claim_scope": "task07b_dem_gate",
                    }
                )
                print(f"dem_incomplete missions={dem_bad}", flush=True)
                continue
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
                    demand_name=demand,
                    capex_name="equal",
                    budget_name=bname,
                    context=context,
                )
                bb, context = run_multiroute_branch_and_bound(
                    cfg,
                    root=ROOT,
                    demand_name=demand,
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
                        "panel_cell": panel["cell"],
                        "demand_name": demand,
                        "vehicle_key": vkey,
                        "terrain_mode": panel["terrain"],
                        "thermal_id": panel["thermal"],
                        "energy_quantum_kwh": panel["q"],
                        "deadline_hours": panel["deadline_h"],
                        "charger_power_kw": panel["charger_kw"],
                        "objective_mode": "enroute_incremental_cost",
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
                        "secondary_cost": None if inc is None else inc.secondary_cost,
                        "objective_agreement": obj_agree,
                        "selected_site_set_equal": site_equal,
                        "all_optimal_site_sets": "|".join(opt_sets),
                        "n_optimal_site_sets": len(opt_sets),
                        "optimality_status": bb.optimality_status.value,
                        "certified_full_portfolio": (
                            bb.optimality_status == OptimalityStatus.CERTIFIED_OPTIMAL
                        ),
                        "serviceability_json": json.dumps(
                            context.get("serviceability") or {}
                        ),
                        "cargo_payload_kg": PAYLOAD_KG,
                        "road_cost_per_km_cents": ROAD_CENTS,
                        "prep_sec": prep_s,
                        "claim_scope": "task07b_placement_robustness",
                        "site_evidence_class": "hypothetical_future_truck_site",
                    }
                )
                print(
                    f"  {bname}: bb={out[-1]['best_sites_bb'] or 'NONE'} "
                    f"opts={opt_sets} agree={obj_agree} "
                    f"cov={out[-1]['coverage_serviceable']} "
                    f"status={bb.optimality_status.value}",
                    flush=True,
                )
    # Claim-critical Volvo460 only if Volvo475 B1 coverage differs from eActros pattern
    return out


def _write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(path, index=False)
    print(f"Wrote {path} ({len(rows)} rows)", flush=True)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--stages",
        default="all",
        help="Comma list: sens,charge,disc,baselines,placement,all",
    )
    p.add_argument("--placement-cells", default="", help="e.g. P0,P1,P2")
    p.add_argument("--placement-vehicles", default="eactros_600,volvo_475")
    args = p.parse_args()
    stages = {s.strip() for s in args.stages.split(",") if s.strip()}
    if "all" in stages:
        stages = {"sens", "charge", "disc", "baselines", "placement"}

    if "sens" in stages:
        rows = run_physical_sensitivity()
        _write_csv(ROOT / "results/task07b_physical_sensitivity.csv", rows)

    if "charge" in stages:
        rows = run_charging_duration()
        _write_csv(ROOT / "results/task07b_charging_duration.csv", rows)

    if "disc" in stages:
        rows = run_discretization_diagnostics()
        _write_csv(ROOT / "results/task07b_discretization_diagnostics.csv", rows)

    if "baselines" in stages:
        rows = run_routing_baselines()
        _write_csv(ROOT / "results/task07b_routing_baselines.csv", rows)

    if "placement" in stages:
        cells = [c.strip() for c in args.placement_cells.split(",") if c.strip()] or None
        vehs = [v.strip() for v in args.placement_vehicles.split(",") if v.strip()]
        rows = run_placement_panel(cells=cells, vehicles=vehs)
        _write_csv(ROOT / "results/task07b_placement_robustness.csv", rows)
        # Also alias claim CSV name from plan
        _write_csv(ROOT / "results/task07b_placement_robustness.csv", rows)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
