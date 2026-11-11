#!/usr/bin/env python
"""Task 07C — matched nesting baselines + bounded final freeze (post nesting gate)."""

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
    gcm_from_payload,
    load_vehicle,
    validate_gcm,
)
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
from morocco_etruck.optimization.multiroute_replay import continuous_replay_multiroute  # noqa: E402
from morocco_etruck.optimization.placement_certification import OptimalityStatus  # noqa: E402
from morocco_etruck.optimization.replay import replay_solution  # noqa: E402
from morocco_etruck.optimization.resource_transitions import (  # noqa: E402
    Label,
    apply_charge,
    apply_drive,
)

VEHICLES = {
    "eactros_600": ROOT / "configs/vehicles/eactros_600.yaml",
    "volvo_475": ROOT / "configs/vehicles/volvo_fh_electric_4x2_540kwh.yaml",
    "volvo_460": ROOT / "configs/vehicles/volvo_fh_electric_4x2_540kwh_usable460.yaml",
}
CFG_07B = ROOT / "configs/optimization/multiroute_placement_07b.yaml"
ROAD_CENTS = 100.0
PAYLOAD = 5300.0
DT_MIN = 5
FRIDGE_NOM = ROOT / "configs/energy/task07b_thermal_nominal.yaml"
FRIDGE_HIGH = ROOT / "configs/energy/task07b_thermal_high.yaml"


def _hours_to_steps(h: float) -> int:
    return int(round(h * 60.0 / DT_MIN))


def _build_full(
    *,
    od_id: str,
    vpath: Path,
    terrain_mode: str,
    q: int,
    soc_frac: float,
    deadline_h: float,
    charger_kw: float,
    fridge: Path,
    weather_id: str = "cool",
    refrigeration_on: bool = True,
):
    cfg = load_multiroute_pilot_config(
        ROOT / "configs/optimization/multiroute_pilot.yaml", root=ROOT
    )
    path_rows = pd.read_csv(cfg.path_alternatives_csv).to_dict(orient="records")
    vehicle = load_vehicle(vpath)
    gcm = gcm_from_payload(PAYLOAD, vehicle)
    validate_gcm(gcm, vehicle)
    e_init = int(round(soc_frac * float(vehicle.usable_kwh)))
    inst, ctx, notes = build_physics_od_instance(
        cfg=cfg,
        root=ROOT,
        od_id=od_id,
        path_rows=path_rows,
        E_truck_init=e_init,
        refrigeration_on=refrigeration_on,
        weather_id=weather_id,
        with_chargers=True,
        energy_quantum_kwh=q,
        terrain_mode=terrain_mode,
        objective_mode="enroute_incremental_cost",
        vehicle_yaml=vpath,
        road_cost_per_km=ROAD_CENTS,
        gcm_kg=gcm,
        deadline_steps=_hours_to_steps(deadline_h),
        fridge_yaml=fridge,
        charger_power_kw=charger_kw,
        # Scientific pilot union (shortest + top Jaccard alt). Not max_alts=1 rebuilds.
        # Unlimited CSV alts can introduce macros without DEM coverage.
        max_alternatives_for_union=2,
    )
    return cfg, path_rows, inst, ctx, notes, vehicle


def _shortest_node_path(inst) -> list[str] | None:
    import heapq
    from collections import defaultdict

    g: dict[str, list[tuple[str, int]]] = defaultdict(list)
    for n in set(inst.nodes):
        for a in inst.outgoing(n):
            g[a.u].append((a.v, int(a.road_cost)))
    pq = [(0, inst.origin, [inst.origin])]
    seen: dict[str, int] = {}
    while pq:
        cost, node, path = heapq.heappop(pq)
        if node in seen and seen[node] <= cost:
            continue
        seen[node] = cost
        if node == inst.destination:
            return path
        for v, rc in g.get(node, []):
            heapq.heappush(pq, (cost + rc, v, path + [v]))
    return None


def _arc_between(inst, u: str, v: str):
    cands = [a for a in inst.outgoing(u) if a.v == v]
    if not cands:
        return None
    return min(cands, key=lambda a: a.road_cost)


def _can_drive_segment(inst, E: int, t: int, nodes: list[str], start_i: int, end_i: int):
    """Try DRIVE along nodes[start_i:end_i] inclusive end. Return (ok, E, t, actions, reason)."""
    lab = Label(
        node=nodes[start_i],
        t=t,
        E_truck=E,
        E_trailer=None,
        cost=0,
        pred_id=None,
        action={"type": "START"},
        label_id=0,
        can_charge=True,
    )
    actions: list[dict] = []
    nid = 1
    for i in range(start_i, end_i):
        arc = _arc_between(inst, nodes[i], nodes[i + 1])
        if arc is None:
            return False, lab.E_truck, lab.t, actions, f"missing_arc:{nodes[i]}->{nodes[i+1]}"
        r = apply_drive(inst, lab, arc, nid)
        if not r.ok or r.label is None:
            return False, lab.E_truck, lab.t, actions, r.reason or "drive_fail"
        lab = r.label
        actions.append(lab.action)
        nid += 1
    return True, lab.E_truck, lab.t, actions, None


def solve_deterministic_min_charge(inst) -> dict[str, Any]:
    """
    Baseline A: fixed shortest (mask already on inst), min charge at each active
    station to reach the next station or destination. Not MRLS.
    """
    path = _shortest_node_path(inst)
    if not path:
        return {
            "status": "INFEASIBLE",
            "reason": "no_masked_path",
            "objective": None,
            "actions": [],
            "final_E": None,
            "final_t": None,
        }
    station_idx = [
        i
        for i, n in enumerate(path)
        if n in inst.active_stations and n in inst.stations
    ]
    checkpoints = station_idx + ([len(path) - 1] if (len(path) - 1) not in station_idx else [])
    # Ensure destination is last checkpoint
    if checkpoints[-1] != len(path) - 1:
        checkpoints.append(len(path) - 1)

    E = int(inst.E_truck_init)
    t = 0
    cost = 0
    actions: list[dict] = []
    q = max(1, int(inst.energy_quantum_kwh))
    lid = 1
    i_pos = 0
    for cp in checkpoints:
        if i_pos == cp:
            continue
        # If current node is an active station and we cannot reach cp, charge min
        if path[i_pos] in inst.active_stations and path[i_pos] in inst.stations:
            ok, _, _, _, _ = _can_drive_segment(inst, E, t, path, i_pos, cp)
            if not ok:
                headroom = inst.E_truck_cap - E
                charged = False
                for de in range(q, headroom + 1, q):
                    lab = Label(
                        node=path[i_pos],
                        t=t,
                        E_truck=E,
                        E_trailer=None,
                        cost=cost,
                        pred_id=None,
                        action={"type": "START"},
                        label_id=0,
                        can_charge=True,
                    )
                    cr = apply_charge(inst, lab, de, lid)
                    if not cr.ok or cr.label is None:
                        continue
                    E2, t2 = cr.label.E_truck, cr.label.t
                    ok2, _, _, _, _ = _can_drive_segment(inst, E2, t2, path, i_pos, cp)
                    if ok2:
                        actions.append(cr.label.action)
                        cost = cr.label.cost
                        E, t = E2, t2
                        lid += 1
                        charged = True
                        break
                if not charged:
                    return {
                        "status": "INFEASIBLE",
                        "reason": f"min_charge_fail_at_{path[i_pos]}_to_{path[cp]}",
                        "objective": None,
                        "actions": actions,
                        "final_E": E,
                        "final_t": t,
                    }
        ok, E, t, drive_acts, reason = _can_drive_segment(inst, E, t, path, i_pos, cp)
        if not ok:
            return {
                "status": "INFEASIBLE",
                "reason": reason,
                "objective": None,
                "actions": actions,
                "final_E": E,
                "final_t": t,
            }
        # Accumulate road cost from drive actions
        for a in drive_acts:
            actions.append(a)
            # cost is in action via replay; recompute from arcs
        # Recompute cost by replaying drives for road component only via apply_drive chain
        i_pos = cp

    # Recompute objective via discrete replay semantics
    from morocco_etruck.optimization.problem import total_objective_cents

    # Rebuild cost from a fresh simulate
    lab = Label(
        node=path[0],
        t=0,
        E_truck=int(inst.E_truck_init),
        E_trailer=None,
        cost=0,
        pred_id=None,
        action={"type": "START"},
        label_id=0,
        can_charge=True,
    )
    sim_actions: list[dict] = []
    # Interpret recorded actions
    for act in actions:
        typ = act.get("type")
        if typ == "CHARGE":
            de = int(
                act.get("delta_e_kwh")
                or act.get("delta_e_truck")
                or act.get("delta_e")
                or 0
            )
            r = apply_charge(inst, lab, de if de > 0 else q, len(sim_actions) + 1)
            if not r.ok or r.label is None:
                # Fall back: use stored action energy if present
                return {
                    "status": "INFEASIBLE",
                    "reason": f"replay_charge_fail:{r.reason}",
                    "objective": None,
                    "actions": actions,
                    "final_E": lab.E_truck,
                    "final_t": lab.t,
                }
            lab = r.label
            sim_actions.append(lab.action)
        elif typ == "DRIVE":
            arc = _arc_between(inst, str(act["u"]), str(act["v"]))
            if arc is None and act.get("arc_id"):
                cands = [
                    a
                    for a in inst.arcs
                    if a.arc_id and str(a.arc_id) == str(act["arc_id"])
                ]
                arc = cands[0] if cands else None
            if arc is None:
                return {
                    "status": "INFEASIBLE",
                    "reason": "replay_missing_arc",
                    "objective": None,
                    "actions": actions,
                    "final_E": lab.E_truck,
                    "final_t": lab.t,
                }
            # Mask check
            if (
                inst.allowed_arc_ids is not None
                and arc.arc_id
                and str(arc.arc_id) not in inst.allowed_arc_ids
            ):
                return {
                    "status": "INFEASIBLE",
                    "reason": "replay_masked_arc",
                    "objective": None,
                    "actions": actions,
                    "final_E": lab.E_truck,
                    "final_t": lab.t,
                }
            r = apply_drive(inst, lab, arc, len(sim_actions) + 1)
            if not r.ok or r.label is None:
                return {
                    "status": "INFEASIBLE",
                    "reason": f"replay_drive_fail:{r.reason}",
                    "objective": None,
                    "actions": actions,
                    "final_E": lab.E_truck,
                    "final_t": lab.t,
                }
            lab = r.label
            sim_actions.append(lab.action)

    if lab.node != inst.destination:
        return {
            "status": "INFEASIBLE",
            "reason": f"not_at_dest:{lab.node}",
            "objective": None,
            "actions": sim_actions,
            "final_E": lab.E_truck,
            "final_t": lab.t,
        }
    obj = total_objective_cents(inst, lab.cost, lab.E_truck, lab.E_trailer)
    return {
        "status": "OPTIMAL",
        "reason": None,
        "objective": obj,
        "actions": sim_actions,
        "final_E": lab.E_truck,
        "final_t": lab.t,
        "path_nodes": path,
    }


def _pack_result(
    *,
    baseline_id: str,
    method: str,
    vkey: str,
    od_id: str,
    terrain: str,
    q: int,
    deadline_h: float,
    charger_kw: float,
    thermal: str,
    install: str,
    active: set[str],
    mask_mode: str,
    inst,
    ctx,
    vehicle,
    status: str,
    objective,
    actions,
    final_E,
    final_t,
    notes: list[str],
    prep_s: float,
    solve_s: float,
    extra: dict | None = None,
) -> dict[str, Any]:
    disc_ok = cont_ok = False
    cont_reason = None
    extras = None
    if status == "OPTIMAL" and actions is not None and final_E is not None and final_t is not None:
        disc = replay_solution(inst, actions, expected_cost=objective)
        disc_ok = disc.ok
        crep, extras = continuous_replay_multiroute(
            ctx,
            inst,
            actions,
            discrete_cost=objective,
            discrete_t=int(final_t),
            discrete_E_truck=int(final_E),
        )
        cont_ok = crep.ok
        cont_reason = crep.reason
    row = {
        "baseline_id": baseline_id,
        "method": method,
        "vehicle_key": vkey,
        "od_id": od_id,
        "terrain_mode": terrain,
        "dem_complete": ctx.dem_complete,
        "energy_quantum_kwh": q,
        "deadline_hours": deadline_h,
        "charger_power_kw": charger_kw,
        "thermal_id": thermal,
        "install_set": install,
        "active_stations": ",".join(sorted(active)),
        "route_mask": mask_mode,
        "n_arcs_physical": len(inst.arcs),
        "n_arcs_allowed": (
            len(inst.arcs)
            if inst.allowed_arc_ids is None
            else len(inst.allowed_arc_ids)
        ),
        "mrls_status": status,
        "objective": objective,
        "final_E_truck": final_E,
        "final_t_steps": final_t,
        "discrete_replay_ok": disc_ok,
        "continuous_replay_ok": cont_ok,
        "continuous_replay_reason": cont_reason,
        "charge_kwh_total": None if extras is None else extras.charge_kwh_total,
        "charge_duration_s": None if extras is None else extras.charge_duration_s,
        "E_traction_kwh": None if extras is None else extras.E_traction_kwh,
        "E_regen_credit_kwh": None if extras is None else extras.E_regen_credit_kwh,
        "E_aux_drive_kwh": None if extras is None else extras.E_aux_drive_kwh,
        "E_refrig_drive_kwh": None if extras is None else extras.E_refrig_drive_kwh,
        "E_refrig_stationary_kwh": (
            None if extras is None else extras.E_refrig_stationary_kwh
        ),
        "min_soc": None if extras is None else extras.min_soc,
        "road_distance_m": None if extras is None else extras.length_m,
        "terminal_soc": (
            None
            if final_E is None
            else float(final_E) / float(vehicle.usable_kwh)
        ),
        "prep_sec": prep_s,
        "solve_sec": solve_s,
        "station_notes": ";".join(notes),
        "claim_scope": "task07c_matched_baselines",
        "graph_rebuild": False,
    }
    if extra:
        row.update(extra)
    return row


def run_matched_baselines(
    *,
    terrain: str = "dem",
    vehicles: list[str] | None = None,
) -> list[dict]:
    vehs = vehicles or ["eactros_600", "volvo_475"]
    ods = ["casa_marrakech", "casa_agadir", "marrakech_agadir"]
    installs = {
        "none": set(),
        "settat_benguerir": {"settat_ca", "benguerir_ca"},
    }
    rows: list[dict] = []
    for vkey in vehs:
        vpath = VEHICLES[vkey]
        for od_id in ods:
            t0 = time.perf_counter()
            try:
                _cfg, path_rows, template, ctx, notes, vehicle = _build_full(
                    od_id=od_id,
                    vpath=vpath,
                    terrain_mode=terrain,
                    q=10,
                    soc_frac=0.5,
                    deadline_h=20.0,
                    charger_kw=350.0,
                    fridge=FRIDGE_NOM,
                )
            except Exception as exc:  # noqa: BLE001
                rows.append(
                    {
                        "baseline_id": "BUILD",
                        "vehicle_key": vkey,
                        "od_id": od_id,
                        "status": "BUILD_ERROR",
                        "error": str(exc),
                        "terrain_mode": terrain,
                    }
                )
                continue
            if terrain == "dem" and not ctx.dem_complete:
                rows.append(
                    {
                        "baseline_id": "BUILD",
                        "vehicle_key": vkey,
                        "od_id": od_id,
                        "status": "dem_incomplete",
                        "terrain_mode": terrain,
                    }
                )
                continue
            prep = time.perf_counter() - t0
            short_mask = shortest_path_allowed_arc_ids(ctx, path_rows, od_id)
            all_mask = frozenset(str(a.arc_id) for a in template.arcs if a.arc_id)
            for iname, active in installs.items():
                # Skip settat_benguerir on MA if neither station on graph
                if iname != "none" and not (set(active) & set(template.stations)):
                    continue
                # A — deterministic min-charge on shortest mask
                inst_a = clone_physics_instance_for_subset(
                    template,
                    active_stations=set(active),
                    allowed_arc_ids=short_mask,
                    name=f"A|{od_id}|{iname}",
                )
                t1 = time.perf_counter()
                det = solve_deterministic_min_charge(inst_a)
                rows.append(
                    _pack_result(
                        baseline_id="A",
                        method="deterministic_min_charge_fixed_shortest",
                        vkey=vkey,
                        od_id=od_id,
                        terrain=terrain,
                        q=10,
                        deadline_h=20.0,
                        charger_kw=350.0,
                        thermal="thermal_nominal",
                        install=iname,
                        active=set(active),
                        mask_mode="shortest",
                        inst=inst_a,
                        ctx=ctx,
                        vehicle=vehicle,
                        status=det["status"],
                        objective=det.get("objective"),
                        actions=det.get("actions") or [],
                        final_E=det.get("final_E"),
                        final_t=det.get("final_t"),
                        notes=notes,
                        prep_s=prep,
                        solve_s=time.perf_counter() - t1,
                        extra={"det_reason": det.get("reason")},
                    )
                )
                print(
                    f"A|{vkey}|{od_id}|{iname}: {det['status']} obj={det.get('objective')}",
                    flush=True,
                )
                # B — MRLS fixed shortest
                inst_b = clone_physics_instance_for_subset(
                    template,
                    active_stations=set(active),
                    allowed_arc_ids=short_mask,
                    name=f"B|{od_id}|{iname}",
                )
                t1 = time.perf_counter()
                res_b = solve_mrls(inst_b, max_seconds=90.0, max_expansions=800_000)
                rows.append(
                    _pack_result(
                        baseline_id="B",
                        method="mrls_fixed_shortest",
                        vkey=vkey,
                        od_id=od_id,
                        terrain=terrain,
                        q=10,
                        deadline_h=20.0,
                        charger_kw=350.0,
                        thermal="thermal_nominal",
                        install=iname,
                        active=set(active),
                        mask_mode="shortest",
                        inst=inst_b,
                        ctx=ctx,
                        vehicle=vehicle,
                        status=res_b.status.value,
                        objective=res_b.objective,
                        actions=res_b.actions,
                        final_E=(
                            res_b.final_label.E_truck if res_b.final_label else None
                        ),
                        final_t=res_b.final_label.t if res_b.final_label else None,
                        notes=notes,
                        prep_s=prep,
                        solve_s=time.perf_counter() - t1,
                    )
                )
                print(
                    f"B|{vkey}|{od_id}|{iname}: {res_b.status.value} obj={res_b.objective}",
                    flush=True,
                )
                # C — MRLS multi-route (all arcs)
                inst_c = clone_physics_instance_for_subset(
                    template,
                    active_stations=set(active),
                    allowed_arc_ids=all_mask,
                    name=f"C|{od_id}|{iname}",
                )
                t1 = time.perf_counter()
                res_c = solve_mrls(inst_c, max_seconds=90.0, max_expansions=800_000)
                rows.append(
                    _pack_result(
                        baseline_id="C",
                        method="mrls_multi_route",
                        vkey=vkey,
                        od_id=od_id,
                        terrain=terrain,
                        q=10,
                        deadline_h=20.0,
                        charger_kw=350.0,
                        thermal="thermal_nominal",
                        install=iname,
                        active=set(active),
                        mask_mode="all",
                        inst=inst_c,
                        ctx=ctx,
                        vehicle=vehicle,
                        status=res_c.status.value,
                        objective=res_c.objective,
                        actions=res_c.actions,
                        final_E=(
                            res_c.final_label.E_truck if res_c.final_label else None
                        ),
                        final_t=res_c.final_label.t if res_c.final_label else None,
                        notes=notes,
                        prep_s=prep,
                        solve_s=time.perf_counter() - t1,
                        extra={
                            "route_choice_gain_vs_B": (
                                None
                                if res_b.objective is None or res_c.objective is None
                                else float(res_b.objective) - float(res_c.objective)
                            )
                        },
                    )
                )
                print(
                    f"C|{vkey}|{od_id}|{iname}: {res_c.status.value} obj={res_c.objective} "
                    f"gain_vs_B={rows[-1].get('route_choice_gain_vs_B')}",
                    flush=True,
                )
                # Nesting check row
                if res_b.status == SolverStatus.OPTIMAL:
                    nest_ok = (
                        res_c.status == SolverStatus.OPTIMAL
                        and res_c.objective is not None
                        and res_b.objective is not None
                        and float(res_c.objective) <= float(res_b.objective) + 1e-9
                    )
                else:
                    nest_ok = True
                rows[-1]["nesting_ok_vs_B"] = nest_ok
                if not nest_ok:
                    print(f"NESTING_FAIL {vkey} {od_id} {iname}", flush=True)
    return rows


def run_placement_panel(
    *,
    cells: list[dict],
) -> list[dict]:
    cfg = load_multiroute_placement_config(CFG_07B, root=ROOT)
    out: list[dict] = []
    for cell in cells:
        demand = cell["demand"]
        fridge = Path(cell["fridge"])
        for vkey in cell["vehicles"]:
            vpath = VEHICLES[vkey]
            print(
                f"\n=== place {cell['id']} veh={vkey} q={cell['q']} "
                f"dl={cell['deadline_h']}h p={cell['charger_kw']} ===",
                flush=True,
            )
            t0 = time.perf_counter()
            try:
                context = prepare_multiroute_placement_context(
                    cfg,
                    root=ROOT,
                    demand_name=demand,
                    energy_quantum_kwh=int(cell["q"]),
                    objective_mode="enroute_incremental_cost",
                    vehicle_yaml=vpath,
                    road_cost_per_km=ROAD_CENTS,
                    deadline_steps=_hours_to_steps(float(cell["deadline_h"])),
                    fridge_yaml=fridge,
                    charger_power_kw=float(cell["charger_kw"]),
                    max_alternatives_for_union=2,
                )
            except Exception as exc:  # noqa: BLE001
                out.append(
                    {
                        "panel_cell": cell["id"],
                        "vehicle_key": vkey,
                        "status": "BUILD_ERROR",
                        "error": str(exc),
                    }
                )
                continue
            dem_bad = [
                mid
                for mid, prep in context["prepared"].items()
                if str(prep.mission.terrain_mode) == "dem" and not prep.ctx.dem_complete
            ]
            if dem_bad:
                out.append(
                    {
                        "panel_cell": cell["id"],
                        "vehicle_key": vkey,
                        "status": "dem_incomplete",
                        "unresolved_ids": ",".join(dem_bad),
                    }
                )
                continue
            prep_s = time.perf_counter() - t0
            missions = cfg.demand_scenarios[demand]
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
                if best is not None and inc is not None:
                    obj_agree = (
                        abs(best.coverage_serviceable - inc.coverage_serviceable)
                        <= 1e-9
                        and abs(best.secondary_cost - inc.secondary_cost) <= 1e-6
                    )
                elif best is None and inc is None:
                    obj_agree = True
                out.append(
                    {
                        "panel_cell": cell["id"],
                        "baseline_id": "D_E",
                        "method": "bb_and_enumeration",
                        "demand_name": demand,
                        "vehicle_key": vkey,
                        "terrain_mode": cell.get("terrain"),
                        "thermal_id": cell.get("thermal"),
                        "energy_quantum_kwh": cell["q"],
                        "deadline_hours": cell["deadline_h"],
                        "charger_power_kw": cell["charger_kw"],
                        "budget_name": bname,
                        "weight_total_demand": context["weight_total_demand"],
                        "coverage_serviceable": (
                            None if inc is None else inc.coverage_serviceable
                        ),
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
                        "claim_scope": "task07c_final_placement",
                    }
                )
                print(
                    f"  {bname}: bb={out[-1]['best_sites_bb'] or 'NONE'} "
                    f"cov={out[-1]['coverage_serviceable']} agree={obj_agree}",
                    flush=True,
                )
    return out


def run_sensitivity() -> list[dict]:
    """Bounded sensitivity: thermal high, 150 vs 350 @12h, q=5 diagnostic."""
    rows: list[dict] = []
    # CA eActros/Volvo: 150 vs 350 under 12h on full multi-route + both chargers
    for vkey in ("eactros_600", "volvo_475"):
        for p_kw in (350.0, 150.0):
            t0 = time.perf_counter()
            _cfg, path_rows, template, ctx, notes, vehicle = _build_full(
                od_id="casa_agadir",
                vpath=VEHICLES[vkey],
                terrain_mode="dem",
                q=10,
                soc_frac=0.5,
                deadline_h=12.0,
                charger_kw=p_kw,
                fridge=FRIDGE_NOM,
            )
            if not ctx.dem_complete:
                rows.append(
                    {
                        "sensitivity": "charger_deadline",
                        "status": "dem_incomplete",
                        "vehicle_key": vkey,
                    }
                )
                continue
            all_mask = frozenset(str(a.arc_id) for a in template.arcs if a.arc_id)
            inst = clone_physics_instance_for_subset(
                template,
                active_stations={"settat_ca", "benguerir_ca"},
                allowed_arc_ids=all_mask,
            )
            res = solve_mrls(inst, max_seconds=90.0, max_expansions=800_000)
            rows.append(
                _pack_result(
                    baseline_id="SENS",
                    method="mrls_multi_route",
                    vkey=vkey,
                    od_id="casa_agadir",
                    terrain="dem",
                    q=10,
                    deadline_h=12.0,
                    charger_kw=p_kw,
                    thermal="thermal_nominal",
                    install="settat_benguerir",
                    active={"settat_ca", "benguerir_ca"},
                    mask_mode="all",
                    inst=inst,
                    ctx=ctx,
                    vehicle=vehicle,
                    status=res.status.value,
                    objective=res.objective,
                    actions=res.actions,
                    final_E=res.final_label.E_truck if res.final_label else None,
                    final_t=res.final_label.t if res.final_label else None,
                    notes=notes,
                    prep_s=time.perf_counter() - t0,
                    solve_s=0.0,
                    extra={"sensitivity": "charger_power_12h"},
                )
            )
            print(
                f"SENS chg|{vkey}|p{p_kw}: {res.status.value} obj={res.objective}",
                flush=True,
            )
        # High thermal
        t0 = time.perf_counter()
        _cfg, path_rows, template, ctx, notes, vehicle = _build_full(
            od_id="casa_agadir",
            vpath=VEHICLES[vkey],
            terrain_mode="dem",
            q=10,
            soc_frac=0.5,
            deadline_h=20.0,
            charger_kw=350.0,
            fridge=FRIDGE_HIGH,
        )
        if ctx.dem_complete:
            all_mask = frozenset(str(a.arc_id) for a in template.arcs if a.arc_id)
            inst = clone_physics_instance_for_subset(
                template,
                active_stations={"settat_ca", "benguerir_ca"},
                allowed_arc_ids=all_mask,
            )
            res = solve_mrls(inst, max_seconds=90.0, max_expansions=800_000)
            rows.append(
                _pack_result(
                    baseline_id="SENS",
                    method="mrls_multi_route",
                    vkey=vkey,
                    od_id="casa_agadir",
                    terrain="dem",
                    q=10,
                    deadline_h=20.0,
                    charger_kw=350.0,
                    thermal="thermal_high",
                    install="settat_benguerir",
                    active={"settat_ca", "benguerir_ca"},
                    mask_mode="all",
                    inst=inst,
                    ctx=ctx,
                    vehicle=vehicle,
                    status=res.status.value,
                    objective=res.objective,
                    actions=res.actions,
                    final_E=res.final_label.E_truck if res.final_label else None,
                    final_t=res.final_label.t if res.final_label else None,
                    notes=notes,
                    prep_s=time.perf_counter() - t0,
                    solve_s=0.0,
                    extra={"sensitivity": "thermal_high"},
                )
            )
            print(
                f"SENS therm|{vkey}: {res.status.value} obj={res.objective}",
                flush=True,
            )
    return rows


def _write(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(path, index=False)
    print(f"Wrote {path} ({len(rows)} rows)", flush=True)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--stages",
        default="all",
        help="baselines,placement,sensitivity,all",
    )
    p.add_argument("--terrain", default="dem", choices=["dem", "flat"])
    args = p.parse_args()
    stages = {s.strip() for s in args.stages.split(",") if s.strip()}
    if "all" in stages:
        stages = {"baselines", "placement", "sensitivity"}

    if "baselines" in stages:
        rows = run_matched_baselines(terrain=args.terrain)
        _write(ROOT / "results/task07c_matched_routing_baselines.csv", rows)

    if "placement" in stages:
        cells = [
            {
                "id": "F0_dem_nominal_q10",
                "demand": "cold_chain_baseline_07b_dem",
                "terrain": "dem",
                "thermal": "thermal_nominal",
                "q": 10,
                "deadline_h": 20.0,
                "charger_kw": 350.0,
                "fridge": str(FRIDGE_NOM),
                "vehicles": ["eactros_600", "volvo_475"],
            },
            {
                "id": "F1_dem_nominal_q5",
                "demand": "cold_chain_baseline_07b_dem",
                "terrain": "dem",
                "thermal": "thermal_nominal",
                "q": 5,
                "deadline_h": 20.0,
                "charger_kw": 350.0,
                "fridge": str(FRIDGE_NOM),
                "vehicles": ["eactros_600", "volvo_475"],
            },
            {
                "id": "F2_dem_high_thermal",
                "demand": "cold_chain_baseline_07b_dem",
                "terrain": "dem",
                "thermal": "thermal_high",
                "q": 10,
                "deadline_h": 20.0,
                "charger_kw": 350.0,
                "fridge": str(FRIDGE_HIGH),
                "vehicles": ["eactros_600", "volvo_475"],
            },
            {
                "id": "F3_dem_12h_150kw",
                "demand": "cold_chain_baseline_07b_dem",
                "terrain": "dem",
                "thermal": "thermal_nominal",
                "q": 10,
                "deadline_h": 12.0,
                "charger_kw": 150.0,
                "fridge": str(FRIDGE_NOM),
                "vehicles": ["eactros_600", "volvo_475"],
            },
        ]
        rows = run_placement_panel(cells=cells)
        _write(ROOT / "results/task07c_final_placement.csv", rows)

    if "sensitivity" in stages:
        rows = run_sensitivity()
        _write(ROOT / "results/task07c_final_sensitivity.csv", rows)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
