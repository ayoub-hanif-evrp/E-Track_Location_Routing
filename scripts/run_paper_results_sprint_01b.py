#!/usr/bin/env python
"""PAPER_RESULTS_SPRINT_01b — close prioritized gaps from sprint 01.

1. Reserve-SOC policy 10/15/20% on northbound Benguerir @ SOC0.8
2. Baseline C: fixed-shortest + deterministic min-charge (H1 + northbound cells)
3. H1 failure diagnosis (energy / charger access / route choice)
4. Metric hygiene: detour, input hashes, enum↔B&B agreement

Does not overwrite manuscript or FINAL_RESEARCH_FREEZE.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import math
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from morocco_etruck.energy.vehicle import (  # noqa: E402
    gcm_from_payload,
    load_vehicle,
    validate_gcm,
)
from morocco_etruck.optimization import multiroute_placement_evaluation as mpe  # noqa: E402
from morocco_etruck.optimization.arc_preprocessing import simulate_drive_from_soc  # noqa: E402
from morocco_etruck.optimization.label_setting import solve_mrls  # noqa: E402
from morocco_etruck.optimization.multiroute_adapter import (  # noqa: E402
    build_physics_od_instance,
    clone_physics_instance_for_subset,
    load_multiroute_pilot_config,
    shortest_path_allowed_arc_ids,
    shortest_path_edge_set,
)
from morocco_etruck.optimization.multiroute_placement import (  # noqa: E402
    load_multiroute_placement_config,
)
from morocco_etruck.optimization.multiroute_placement_evaluation import (  # noqa: E402
    all_optimal_site_sets,
    evaluate_multiroute_mission,
    prepare_multiroute_placement_context,
    run_multiroute_branch_and_bound,
    run_multiroute_enumeration,
)
from morocco_etruck.optimization.multiroute_replay import continuous_replay_multiroute  # noqa: E402
from morocco_etruck.optimization.operational_schedule import (  # noqa: E402
    validate_operational_schedule,
)
from morocco_etruck.optimization.quantization_audit import audit_solved_actions_exact  # noqa: E402
from morocco_etruck.optimization.replay import replay_solution  # noqa: E402
from morocco_etruck.optimization.resource_transitions import Label, apply_drive  # noqa: E402

# Reuse Task07C deterministic min-charge baseline C
_spec = importlib.util.spec_from_file_location(
    "task07c_freeze", ROOT / "scripts/run_task07c_final_freeze.py"
)
_t07 = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(_t07)
solve_deterministic_min_charge = _t07.solve_deterministic_min_charge
_shortest_node_path = _t07._shortest_node_path
_arc_between = _t07._arc_between

VEHICLES = {
    "eactros_600": ROOT / "configs/vehicles/eactros_600.yaml",
    "volvo_475": ROOT / "configs/vehicles/volvo_fh_electric_4x2_540kwh.yaml",
}
CFG_PASS2A = ROOT / "configs/optimization/multiroute_placement_pass2a.yaml"
FRIDGE = ROOT / "configs/energy/pass2_tomato_firm_ripe.yaml"
FRIDGE_07 = ROOT / "configs/energy/task07b_thermal_nominal.yaml"
OUT_BASELINES = ROOT / "results/paper_results_matched_baselines.csv"
OUT_RESERVE = ROOT / "results/paper_results_reserve_soc.csv"
OUT_DIAG = ROOT / "results/paper_results_h1_failure_diagnosis.csv"
OUT_HYGIENE = ROOT / "results/paper_results_metric_hygiene.csv"
OUT_MD = ROOT / "reports/PAPER_RESULTS_SPRINT_01.md"
OUT_MD_B = ROOT / "reports/PAPER_RESULTS_SPRINT_01b.md"

PAYLOAD = 5300.0
ROAD_CENTS = 100.0
DT_MIN = 5


def _git_sha() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip()
    except Exception:  # noqa: BLE001
        return "unknown"


def _file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:16]


def _hours_to_steps(h: float) -> int:
    return int(round(h * 60.0 / DT_MIN))


def _patch_peak_speed_policy(*, adapt_peak: bool = True, adapt_cont: bool = False):
    orig = mpe.load_multiroute_pilot_config

    def wrapped(path, *, root):
        c = orig(path, root=root)
        sp = dict(c.speed_policy)
        sp["adapt_speed_to_peak_power"] = bool(adapt_peak)
        sp["adapt_speed_to_continuous_power"] = bool(adapt_cont)
        sp["min_adapt_speed_mps"] = 1.0 / 3.6
        c.speed_policy = sp
        return c

    mpe.load_multiroute_pilot_config = wrapped
    return orig


def _policy_vehicle_yaml(base: Path, reserve_soc: float, tmpdir: Path) -> Path:
    raw = yaml.safe_load(base.read_text(encoding="utf-8"))
    raw = dict(raw)
    soc = dict(raw.get("soc") or {})
    soc["soc_min"] = float(reserve_soc)
    soc["soc_min_note"] = (
        f"POLICY scenario reserve SOC {reserve_soc:.0%}; "
        "not a manufacturer warranty or legal requirement"
    )
    raw["soc"] = soc
    out = tmpdir / f"{base.stem}_reserve{int(round(reserve_soc * 100)):02d}.yaml"
    out.write_text(yaml.safe_dump(raw, sort_keys=False), encoding="utf-8")
    return out


def _enrich(inst, ctx, vehicle, actions, objective, final_E, final_t, status: str) -> dict:
    disc_ok = cont_ok = audit_ok = False
    cont_reason = audit_reason = None
    extras = None
    sched = None
    if status == "OPTIMAL" and actions:
        disc = replay_solution(inst, actions, expected_cost=objective)
        disc_ok = disc.ok
        crep, extras = continuous_replay_multiroute(
            ctx,
            inst,
            actions,
            discrete_cost=objective,
            discrete_t=int(final_t) if final_t is not None else None,
            discrete_E_truck=int(final_E) if final_E is not None else None,
        )
        cont_ok = crep.ok
        cont_reason = crep.reason
        audit = audit_solved_actions_exact(
            inst,
            actions,
            prep_ctx=ctx,
            simulate_drive_fn=simulate_drive_from_soc,
            expected_final_E_disc=int(final_E) if final_E is not None else None,
        )
        audit_ok = audit.ok
        audit_reason = audit.failure_reason
        sched = validate_operational_schedule(actions, time_step_min=inst.time_step_min)
    return {
        "discrete_replay_ok": disc_ok,
        "continuous_replay_ok": cont_ok,
        "continuous_replay_reason": cont_reason,
        "audit_ok": audit_ok,
        "audit_reason": audit_reason,
        "charge_kwh_total": None if extras is None else extras.charge_kwh_total,
        "charge_duration_s": None if extras is None else extras.charge_duration_s,
        "min_soc": None if extras is None else extras.min_soc,
        "road_distance_m": None if extras is None else extras.length_m,
        "terminal_soc": None
        if final_E is None
        else float(final_E) / float(vehicle.usable_kwh),
        "driving_min": None if sched is None else sched.driving_min,
        "charging_min": None if sched is None else sched.charging_min,
        "charge_rest_overlap_min": None
        if sched is None
        else sched.charging_rest_overlap_min,
        "extra_rest_min": None if sched is None else sched.extra_rest_beyond_charge_min,
        "total_realistic_journey_min": None
        if sched is None
        else sched.total_realistic_journey_min,
        "schedule_ok": None if sched is None else sched.ok,
        "schedule_violation": None if sched is None else sched.violation,
    }


def _shortest_length_m(path_rows, od_id: str) -> float | None:
    rows = [r for r in path_rows if str(r.get("od_id")) == od_id]
    short = next((r for r in rows if str(r.get("method")) == "shortest_distance"), None)
    if short is None:
        return None
    if short.get("length_m") is not None:
        return float(short["length_m"])
    if short.get("distance_m") is not None:
        return float(short["distance_m"])
    return None


def _build_od(*, od_id, vpath, q, soc_frac, deadline_h, charger_kw, fridge, max_alts=2):
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
        refrigeration_on=True,
        weather_id="cool",
        with_chargers=True,
        energy_quantum_kwh=q,
        terrain_mode="dem",
        objective_mode="enroute_incremental_cost",
        vehicle_yaml=vpath,
        road_cost_per_km=ROAD_CENTS,
        gcm_kg=gcm,
        deadline_steps=_hours_to_steps(deadline_h),
        fridge_yaml=fridge,
        charger_power_kw=charger_kw,
        max_alternatives_for_union=max_alts,
    )
    return cfg, path_rows, inst, ctx, notes, vehicle


def run_reserve_soc(*, q: int = 5) -> list[dict[str, Any]]:
    """Policy reserve SOC on northbound + Benguerir (and none / settat / both)."""
    cfg = load_multiroute_placement_config(CFG_PASS2A, root=ROOT)
    demand = "A_nb_tomato_p5300_soc08"
    rows: list[dict[str, Any]] = []
    orig = _patch_peak_speed_policy()
    try:
        with tempfile.TemporaryDirectory() as td:
            tdir = Path(td)
            for reserve in (0.10, 0.15, 0.20):
                vpath = _policy_vehicle_yaml(VEHICLES["eactros_600"], reserve, tdir)
                t0 = time.perf_counter()
                context = prepare_multiroute_placement_context(
                    cfg,
                    root=ROOT,
                    demand_name=demand,
                    energy_quantum_kwh=q,
                    objective_mode="enroute_incremental_cost",
                    vehicle_yaml=vpath,
                    road_cost_per_km=ROAD_CENTS,
                    fridge_yaml=FRIDGE,
                    charger_power_kw=350.0,
                    max_alternatives_for_union=4,
                )
                prep = next(iter(context["prepared"].values()))
                for name, installed in [
                    ("none", set()),
                    ("benguerir", {"y_benguerir_ac"}),
                    ("settat", {"y_settat_ac"}),
                    ("both", {s.id for s in cfg.sites}),
                ]:
                    ev = evaluate_multiroute_mission(
                        prep,
                        installed=installed,
                        sites=cfg.sites,
                        max_seconds=cfg.solver_max_seconds,
                        max_expansions=cfg.solver_max_expansions,
                    )
                    # recover actions for metrics when served
                    extras = {}
                    if ev.served:
                        from morocco_etruck.optimization.multiroute_placement_evaluation import (
                            active_keys_for_installed,
                        )

                        active = active_keys_for_installed(
                            cfg.sites, installed, prep.template
                        )
                        inst = clone_physics_instance_for_subset(
                            prep.template, active_stations=active, name=f"rs|{reserve}|{name}"
                        )
                        res = solve_mrls(
                            inst,
                            max_seconds=cfg.solver_max_seconds,
                            max_expansions=cfg.solver_max_expansions,
                        )
                        if res.status.value == "OPTIMAL":
                            extras = _enrich(
                                inst,
                                prep.ctx,
                                prep.ctx.vehicle,
                                res.actions or [],
                                res.objective,
                                res.final_label.E_truck if res.final_label else None,
                                res.final_label.t if res.final_label else None,
                                res.status.value,
                            )
                    row = {
                        "experiment": "reserve_soc_policy",
                        "policy_label": f"reserve_soc_{int(round(reserve*100))}pct",
                        "reserve_soc_frac": reserve,
                        "reserve_is_policy_not_legal": True,
                        "demand": demand,
                        "od_id": "agadir_casa",
                        "direction": "northbound",
                        "vehicle_key": "eactros_600",
                        "payload_kg": PAYLOAD,
                        "soc_frac": 0.8,
                        "q": q,
                        "install_set": name,
                        "installed": ",".join(sorted(installed)),
                        "E_truck_min": prep.template.E_truck_min,
                        "E_truck_init": prep.template.E_truck_init,
                        "served": bool(ev.served),
                        "status": ev.status,
                        "disc_ok": ev.discrete_replay_ok,
                        "cont_ok": ev.continuous_replay_ok,
                        "charge_kwh": ev.charge_kwh,
                        "objective_cents": ev.objective_cents,
                        "path": ev.path,
                        "vehicle_yaml_sha16": _file_hash(vpath),
                        "fridge_sha16": _file_hash(FRIDGE),
                        "cfg_sha16": _file_hash(CFG_PASS2A),
                        "git_sha": _git_sha(),
                        "elapsed_sec": time.perf_counter() - t0,
                        **extras,
                    }
                    rows.append(row)
                    print(
                        f"Reserve {reserve:.0%} / {name}: served={ev.served} "
                        f"status={ev.status} min_soc={extras.get('min_soc')}",
                        flush=True,
                    )
                # enum Ball for this reserve
                enum_rows, best, _ = run_multiroute_enumeration(
                    cfg,
                    root=ROOT,
                    demand_name=demand,
                    capex_name="equal",
                    budget_name="Ball",
                    context=context,
                )
                opt = all_optimal_site_sets(enum_rows)
                rows.append(
                    {
                        "experiment": "reserve_soc_policy",
                        "policy_label": f"reserve_soc_{int(round(reserve*100))}pct",
                        "reserve_soc_frac": reserve,
                        "reserve_is_policy_not_legal": True,
                        "demand": demand,
                        "od_id": "agadir_casa",
                        "q": q,
                        "install_set": "enum_Ball",
                        "best_sites": ""
                        if best is None
                        else ",".join(sorted(best.site_ids)),
                        "all_optimal_site_sets": json.dumps(opt),
                        "coverage": None if best is None else best.coverage_serviceable,
                        "served": None
                        if best is None
                        else best.coverage_serviceable > 0.5,
                        "git_sha": _git_sha(),
                        "vehicle_yaml_sha16": _file_hash(vpath),
                    }
                )
    finally:
        mpe.load_multiroute_pilot_config = orig
    OUT_RESERVE.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(OUT_RESERVE, index=False)
    print(f"Wrote {OUT_RESERVE} ({len(rows)} rows)", flush=True)
    return rows


def diagnose_fixed_failure(inst, ctx) -> dict[str, Any]:
    """Walk shortest masked path until first infeasible DRIVE; classify cause."""
    path = _shortest_node_path(inst)
    out: dict[str, Any] = {
        "shortest_n_nodes": None if path is None else len(path),
        "fail_at_index": None,
        "fail_u": None,
        "fail_v": None,
        "fail_arc_id": None,
        "fail_reason": None,
        "stations_on_shortest": None,
        "active_on_shortest": None,
        "diagnosis_class": None,
    }
    if not path:
        out["fail_reason"] = "no_masked_path"
        out["diagnosis_class"] = "no_path"
        return out
    stations_on = [n for n in path if n in inst.stations]
    active_on = [n for n in path if n in inst.active_stations]
    out["stations_on_shortest"] = ",".join(stations_on)
    out["active_on_shortest"] = ",".join(active_on)
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
    for i in range(len(path) - 1):
        # optional charge if at active station and cannot continue far — diagnosis only
        arc = _arc_between(inst, path[i], path[i + 1])
        if arc is None:
            out.update(
                fail_at_index=i,
                fail_u=path[i],
                fail_v=path[i + 1],
                fail_reason="missing_arc_on_shortest",
                diagnosis_class="graph_mask",
            )
            return out
        # If at charger, try greedy full charge once if next drive fails without it
        r = apply_drive(inst, lab, arc, i + 1)
        if not r.ok or r.label is None:
            reason = r.reason or "drive_fail"
            # Can charging at current node recover?
            recovered = False
            if path[i] in inst.active_stations and path[i] in inst.stations:
                q = max(1, int(inst.energy_quantum_kwh))
                head = inst.E_truck_cap - lab.E_truck
                from morocco_etruck.optimization.resource_transitions import apply_charge

                for de in range(q, head + 1, q):
                    cr = apply_charge(inst, lab, de, 9000 + de)
                    if not cr.ok or cr.label is None:
                        continue
                    r2 = apply_drive(inst, cr.label, arc, i + 1)
                    if r2.ok and r2.label is not None:
                        recovered = True
                        lab = r2.label
                        break
            if recovered:
                continue
            cls = "energy_soc_floor"
            if reason and "deadline" in reason:
                cls = "deadline"
            elif reason and "peak" in reason:
                cls = "power"
            elif reason and "drive_table" in reason:
                cls = "energy_or_power_table"
            elif not active_on:
                cls = "no_charger_on_shortest"
            elif path[i] not in inst.active_stations and reason in (
                "tractor_soc_floor",
                "drive_table_missing",
            ):
                cls = "energy_before_reaching_charger"
            out.update(
                fail_at_index=i,
                fail_u=path[i],
                fail_v=path[i + 1],
                fail_arc_id=arc.arc_id,
                fail_reason=reason,
                diagnosis_class=cls,
                E_at_fail=lab.E_truck,
            )
            return out
        lab = r.label
    out["fail_reason"] = None
    out["diagnosis_class"] = "path_drivable_without_extra_route"
    out["E_at_dest_no_opt_charge"] = lab.E_truck
    return out


def run_h1_diagnosis_and_baseline_c(*, quanta=(5, 2)) -> tuple[list[dict], list[dict]]:
    cases = [
        ("casa_marrakech", "eactros_600", "settat_benguerir"),
        ("casa_marrakech", "volvo_475", "settat_benguerir"),
        ("casa_agadir", "volvo_475", "settat_benguerir"),
    ]
    install_map = {
        "none": set(),
        "settat_benguerir": {"settat_ca", "benguerir_ca"},
    }
    diag_rows: list[dict] = []
    base_rows: list[dict] = []
    for q in quanta:
        for od_id, vkey, iname in cases:
            for install_name in ("none", iname):
                _cfg, path_rows, template, ctx, notes, vehicle = _build_od(
                    od_id=od_id,
                    vpath=VEHICLES[vkey],
                    q=q,
                    soc_frac=0.5,
                    deadline_h=20.0,
                    charger_kw=350.0,
                    fridge=FRIDGE_07,
                )
                active = set(install_map[install_name]) & set(template.stations)
                short_mask = shortest_path_allowed_arc_ids(ctx, path_rows, od_id)
                all_mask = frozenset(str(a.arc_id) for a in template.arcs if a.arc_id)
                short_len = _shortest_length_m(path_rows, od_id)

                inst_b = clone_physics_instance_for_subset(
                    template,
                    active_stations=set(active),
                    allowed_arc_ids=short_mask,
                    name=f"diagB|{od_id}|{install_name}|q{q}",
                )
                diag = diagnose_fixed_failure(inst_b, ctx)
                # MRLS fixed + multi for charger/route attribution
                t1 = time.perf_counter()
                res_b = solve_mrls(inst_b, max_seconds=90.0, max_expansions=800_000)
                solve_b = time.perf_counter() - t1
                inst_d = clone_physics_instance_for_subset(
                    template,
                    active_stations=set(active),
                    allowed_arc_ids=all_mask,
                    name=f"diagD|{od_id}|{install_name}|q{q}",
                )
                t1 = time.perf_counter()
                res_d = solve_mrls(inst_d, max_seconds=120.0, max_expansions=1_000_000)
                solve_d = time.perf_counter() - t1

                # Baseline C: deterministic min-charge on fixed shortest
                t1 = time.perf_counter()
                det = solve_deterministic_min_charge(inst_b)
                solve_c = time.perf_counter() - t1

                multi_uses_nonshort = None
                multi_charge_nodes = None
                short_charge_nodes = None
                if res_d.status.value == "OPTIMAL" and res_d.actions:
                    drive_arcs = {
                        str(a.get("arc_id"))
                        for a in res_d.actions
                        if a.get("type") == "DRIVE" and a.get("arc_id")
                    }
                    multi_uses_nonshort = bool(drive_arcs - set(short_mask))
                    multi_charge_nodes = ",".join(
                        sorted(
                            {
                                str(a.get("node"))
                                for a in res_d.actions
                                if a.get("type") == "CHARGE"
                            }
                        )
                    )
                if res_b.status.value == "OPTIMAL" and res_b.actions:
                    short_charge_nodes = ",".join(
                        sorted(
                            {
                                str(a.get("node"))
                                for a in res_b.actions
                                if a.get("type") == "CHARGE"
                            }
                        )
                    )

                # Refine diagnosis when multi works and fixed fails
                if (
                    res_b.status.value != "OPTIMAL"
                    and res_d.status.value == "OPTIMAL"
                ):
                    if not diag.get("active_on_shortest"):
                        gain_mech = "multi_reaches_off_shortest_chargers_or_energy"
                    elif multi_uses_nonshort:
                        gain_mech = "route_choice_different_roads"
                    elif multi_charge_nodes and multi_charge_nodes != (
                        short_charge_nodes or ""
                    ):
                        gain_mech = "different_charge_schedule_or_access"
                    else:
                        gain_mech = "energy_feasibility_via_alternate_arcs"
                else:
                    gain_mech = "no_h1_gain"

                drow = {
                    "experiment": "h1_failure_diagnosis",
                    "od_id": od_id,
                    "vehicle_key": vkey,
                    "q": q,
                    "install_set": install_name,
                    "active_stations": ",".join(sorted(active)),
                    "fixed_status": res_b.status.value,
                    "multi_status": res_d.status.value,
                    "det_min_charge_status": det.get("status"),
                    "det_min_charge_reason": det.get("reason"),
                    "multi_uses_nonshortest_arcs": multi_uses_nonshort,
                    "multi_charge_nodes": multi_charge_nodes,
                    "fixed_charge_nodes": short_charge_nodes,
                    "gain_mechanism": gain_mech,
                    "shortest_length_m": short_len,
                    "input_vehicle_sha16": _file_hash(VEHICLES[vkey]),
                    "input_fridge_sha16": _file_hash(FRIDGE_07),
                    "git_sha": _git_sha(),
                    **diag,
                }
                # enrich multi road length / detour
                if res_d.status.value == "OPTIMAL":
                    en = _enrich(
                        inst_d,
                        ctx,
                        vehicle,
                        res_d.actions or [],
                        res_d.objective,
                        res_d.final_label.E_truck if res_d.final_label else None,
                        res_d.final_label.t if res_d.final_label else None,
                        res_d.status.value,
                    )
                    drow["multi_road_m"] = en.get("road_distance_m")
                    drow["multi_min_soc"] = en.get("min_soc")
                    drow["multi_audit_ok"] = en.get("audit_ok")
                    drow["multi_cont_ok"] = en.get("continuous_replay_ok")
                    if short_len and en.get("road_distance_m"):
                        drow["detour_ratio"] = float(en["road_distance_m"]) / float(
                            short_len
                        )
                diag_rows.append(drow)
                print(
                    f"DIAG {od_id}|{vkey}|{install_name}|q{q}: "
                    f"fixed={res_b.status.value} multi={res_d.status.value} "
                    f"class={diag.get('diagnosis_class')} mech={gain_mech}",
                    flush=True,
                )

                # Append baseline C (+ optionally refresh B) into matched baselines schema
                for bid, method, res_like, mask_name, solve_s in [
                    (
                        "C",
                        "deterministic_min_charge_fixed_shortest",
                        {
                            "status": det.get("status"),
                            "objective": det.get("objective"),
                            "actions": det.get("actions") or [],
                            "final_E": det.get("final_E"),
                            "final_t": det.get("final_t"),
                        },
                        "shortest",
                        solve_c,
                    ),
                ]:
                    row = {
                        "experiment": "h1_matched",
                        "baseline_id": bid,
                        "method": method,
                        "od_id": od_id,
                        "direction": "southbound_corridor",
                        "vehicle_key": vkey,
                        "payload_kg": PAYLOAD,
                        "soc_frac": 0.5,
                        "q": q,
                        "install_set": install_name,
                        "active_stations": ",".join(sorted(active)),
                        "route_mask": mask_name,
                        "n_arcs_physical": len(template.arcs),
                        "n_arcs_allowed": len(short_mask),
                        "graph_rebuild": False,
                        "status": res_like["status"],
                        "objective": res_like["objective"],
                        "final_E_truck": res_like["final_E"],
                        "final_t_steps": res_like["final_t"],
                        "solve_sec": solve_s,
                        "fixed_fail_reason": det.get("reason")
                        if bid == "C"
                        else None,
                        "diagnosis_class": diag.get("diagnosis_class"),
                        "gain_mechanism": gain_mech,
                        "shortest_length_m": short_len,
                        "input_vehicle_sha16": _file_hash(VEHICLES[vkey]),
                        "input_fridge_sha16": _file_hash(FRIDGE_07),
                        "git_sha": _git_sha(),
                        "sprint": "01b",
                    }
                    if res_like["status"] == "OPTIMAL":
                        row.update(
                            _enrich(
                                inst_b,
                                ctx,
                                vehicle,
                                res_like["actions"],
                                res_like["objective"],
                                res_like["final_E"],
                                res_like["final_t"],
                                res_like["status"],
                            )
                        )
                        if short_len and row.get("road_distance_m"):
                            row["detour_ratio"] = float(row["road_distance_m"]) / float(
                                short_len
                            )
                    base_rows.append(row)
                    print(
                        f"C {vkey}|{od_id}|{install_name}|q{q}: {res_like['status']}",
                        flush=True,
                    )
                # also store B timing hygiene already known; skip re-append B/D
                _ = (solve_b, solve_d, notes)
    return diag_rows, base_rows


def run_northbound_baseline_c(*, q: int = 5) -> list[dict]:
    cfg = load_multiroute_placement_config(CFG_PASS2A, root=ROOT)
    rows: list[dict] = []
    orig = _patch_peak_speed_policy()
    try:
        for demand, soc in [
            ("A_nb_tomato_p5300_soc08", 0.8),
            ("A_nb_tomato_p5300_soc10", 1.0),
        ]:
            context = prepare_multiroute_placement_context(
                cfg,
                root=ROOT,
                demand_name=demand,
                energy_quantum_kwh=q,
                objective_mode="enroute_incremental_cost",
                vehicle_yaml=VEHICLES["eactros_600"],
                road_cost_per_km=ROAD_CENTS,
                fridge_yaml=FRIDGE,
                charger_power_kw=350.0,
                max_alternatives_for_union=4,
            )
            prep = next(iter(context["prepared"].values()))
            path_rows = pd.read_csv(
                load_multiroute_pilot_config(
                    ROOT / "configs/optimization/multiroute_pilot.yaml", root=ROOT
                ).path_alternatives_csv
            ).to_dict(orient="records")
            short_mask = shortest_path_allowed_arc_ids(
                prep.ctx, path_rows, "agadir_casa"
            )
            short_len = _shortest_length_m(path_rows, "agadir_casa")
            key_of = {s.id: s.station_key for s in cfg.sites}
            for iname, site_ids in [
                ("A_none", set()),
                ("B_benguerir", {"y_benguerir_ac"}),
                ("Ball_both", {s.id for s in cfg.sites}),
            ]:
                present = {key_of[i] for i in site_ids if i in key_of} & set(
                    prep.template.stations
                )
                inst = clone_physics_instance_for_subset(
                    prep.template,
                    active_stations=present,
                    allowed_arc_ids=short_mask,
                    name=f"NBC|{demand}|{iname}",
                )
                det = solve_deterministic_min_charge(inst)
                row = {
                    "experiment": "northbound_matched",
                    "baseline_id": "C",
                    "method": "deterministic_min_charge_fixed_shortest",
                    "mission_id": "M_agadir_casa",
                    "od_id": "agadir_casa",
                    "direction": "northbound",
                    "vehicle_key": "eactros_600",
                    "payload_kg": PAYLOAD,
                    "soc_frac": soc,
                    "demand": demand,
                    "q": q,
                    "install_set": iname,
                    "installed_site_ids": ",".join(sorted(site_ids)),
                    "active_stations": ",".join(sorted(present)),
                    "route_mask": "shortest",
                    "status": det.get("status"),
                    "objective": det.get("objective"),
                    "final_E_truck": det.get("final_E"),
                    "final_t_steps": det.get("final_t"),
                    "fixed_fail_reason": det.get("reason"),
                    "shortest_length_m": short_len,
                    "input_vehicle_sha16": _file_hash(VEHICLES["eactros_600"]),
                    "input_fridge_sha16": _file_hash(FRIDGE),
                    "cfg_sha16": _file_hash(CFG_PASS2A),
                    "git_sha": _git_sha(),
                    "sprint": "01b",
                }
                if det.get("status") == "OPTIMAL":
                    row.update(
                        _enrich(
                            inst,
                            prep.ctx,
                            prep.ctx.vehicle,
                            det.get("actions") or [],
                            det.get("objective"),
                            det.get("final_E"),
                            det.get("final_t"),
                            det["status"],
                        )
                    )
                    if short_len and row.get("road_distance_m"):
                        row["detour_ratio"] = float(row["road_distance_m"]) / float(
                            short_len
                        )
                rows.append(row)
                print(f"NB-C {demand}|{iname}: {det.get('status')}", flush=True)
    finally:
        mpe.load_multiroute_pilot_config = orig
    return rows


def run_enum_bb_hygiene(*, q: int = 5) -> list[dict]:
    cfg = load_multiroute_placement_config(CFG_PASS2A, root=ROOT)
    rows: list[dict] = []
    orig = _patch_peak_speed_policy()
    try:
        for demand in (
            "A_nb_tomato_p5300_soc08",
            "A_nb_tomato_p5300_soc10",
        ):
            context = prepare_multiroute_placement_context(
                cfg,
                root=ROOT,
                demand_name=demand,
                energy_quantum_kwh=q,
                objective_mode="enroute_incremental_cost",
                vehicle_yaml=VEHICLES["eactros_600"],
                road_cost_per_km=ROAD_CENTS,
                fridge_yaml=FRIDGE,
                charger_power_kw=350.0,
                max_alternatives_for_union=4,
            )
            for budget in ("B1", "Ball"):
                enum_rows, best_e, _ = run_multiroute_enumeration(
                    cfg,
                    root=ROOT,
                    demand_name=demand,
                    capex_name="equal",
                    budget_name=budget,
                    context=context,
                )
                bb_core, _ = run_multiroute_branch_and_bound(
                    cfg,
                    root=ROOT,
                    demand_name=demand,
                    capex_name="equal",
                    budget_name=budget,
                    context=context,
                )
                best_b = getattr(bb_core, "incumbent", None)
                e_sites = "" if best_e is None else ",".join(sorted(best_e.site_ids))
                if best_b is None:
                    b_sites = ""
                else:
                    site_ids = getattr(best_b, "site_ids", None)
                    if site_ids is None and isinstance(best_b, (set, frozenset)):
                        site_ids = best_b
                    b_sites = ",".join(sorted(site_ids)) if site_ids is not None else ""
                opt = all_optimal_site_sets(enum_rows)
                rows.append(
                    {
                        "experiment": "enum_bb_hygiene",
                        "demand": demand,
                        "q": q,
                        "budget": budget,
                        "enum_best_sites": e_sites,
                        "bb_best_sites": b_sites,
                        "enum_bb_agree": e_sites == b_sites,
                        "all_optimal_site_sets": json.dumps(opt),
                        "enum_coverage": None
                        if best_e is None
                        else best_e.coverage_serviceable,
                        "bb_coverage": None
                        if best_b is None
                        else getattr(best_b, "coverage_serviceable", None),
                        "bb_certified": None
                        if best_b is None
                        else getattr(best_b, "certified", None),
                        "bb_optimality_status": str(
                            getattr(bb_core, "optimality_status", "")
                        ),
                        "input_vehicle_sha16": _file_hash(VEHICLES["eactros_600"]),
                        "input_fridge_sha16": _file_hash(FRIDGE),
                        "cfg_sha16": _file_hash(CFG_PASS2A),
                        "git_sha": _git_sha(),
                    }
                )
                print(
                    f"HYGIENE {demand}|{budget}: enum={e_sites} bb={b_sites} "
                    f"agree={e_sites == b_sites}",
                    flush=True,
                )
    finally:
        mpe.load_multiroute_pilot_config = orig
    OUT_HYGIENE.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(OUT_HYGIENE, index=False)
    print(f"Wrote {OUT_HYGIENE}", flush=True)
    return rows


def _merge_baselines(new_rows: list[dict]) -> None:
    new_df = pd.DataFrame(new_rows)
    if OUT_BASELINES.exists():
        old = pd.read_csv(OUT_BASELINES)
        if "baseline_id" in old.columns and "experiment" in new_df.columns:
            exps = set(new_df["experiment"].dropna().unique())
            # Replace only C-rows for experiments present in this batch.
            mask = (old["baseline_id"] == "C") & (old["experiment"].isin(exps))
            old = old[~mask]
        merged = pd.concat([old, new_df], ignore_index=True)
    else:
        merged = new_df
    merged.to_csv(OUT_BASELINES, index=False)
    print(f"Merged baselines -> {OUT_BASELINES} ({len(merged)} rows)", flush=True)


def write_reports(
    reserve_rows: list[dict],
    diag_rows: list[dict],
    hygiene_rows: list[dict],
) -> None:
    # compact 01b report
    lines = [
        "# PAPER_RESULTS_SPRINT_01b\n\n",
        f"Git SHA (base): `{_git_sha()}`  \n",
        "Closes prioritized gaps from sprint 01. Not publication-ready.\n\n",
        "## 1. Reserve-SOC policy (northbound, Benguerir cell family)\n\n",
        "Policy scenarios only — **not** manufacturer/legal requirements. "
        "Vehicle `soc_min` rebuilt per reserve so discrete + continuous floors match.\n\n",
        "| Reserve | none | Benguerir | Settat | both | Ball opt sets |\n",
        "|---:|---|---|---|---|---|\n",
    ]
    for rsv in (0.10, 0.15, 0.20):
        def _s(name):
            hits = [
                x
                for x in reserve_rows
                if x.get("reserve_soc_frac") == rsv and x.get("install_set") == name
            ]
            if not hits:
                return "?"
            return "served" if hits[0].get("served") else "unserved"

        enum = next(
            (
                x
                for x in reserve_rows
                if x.get("reserve_soc_frac") == rsv and x.get("install_set") == "enum_Ball"
            ),
            {},
        )
        lines.append(
            f"| {rsv:.0%} | {_s('none')} | {_s('benguerir')} | {_s('settat')} | "
            f"{_s('both')} | `{enum.get('all_optimal_site_sets')}` |\n"
        )

    lines.append("\n## 2. Baseline C (fixed shortest + deterministic min-charge)\n\n")
    lines.append(
        "Added as `baseline_id=C` in `paper_results_matched_baselines.csv` for H1 "
        "and northbound cells. Completes A/B/C/D/E-style comparison set "
        "(B=MRLS fixed, C=det min-charge, D=multi, E=joint enum).\n\n"
    )

    lines.append("## 3. H1 failure diagnosis\n\n")
    lines.append(
        "| OD | Truck | q | Fixed fail class | Gain mechanism | Detour |\n"
        "|---|---|---:|---|---|---:|\n"
    )
    for r in diag_rows:
        if r.get("install_set") == "none":
            continue
        det = r.get("detour_ratio")
        det_s = "" if det is None or (isinstance(det, float) and math.isnan(det)) else f"{det:.4f}"
        lines.append(
            f"| {r.get('od_id')} | {r.get('vehicle_key')} | {r.get('q')} | "
            f"{r.get('diagnosis_class')} | {r.get('gain_mechanism')} | {det_s} |\n"
        )

    lines.append("\n## 4. Enum ↔ B&B hygiene\n\n")
    lines.append("| Demand | Budget | Enum | B&B | Agree |\n|---|---|---|---|---|\n")
    for r in hygiene_rows:
        lines.append(
            f"| {r.get('demand')} | {r.get('budget')} | `{r.get('enum_best_sites')}` | "
            f"`{r.get('bb_best_sites')}` | {r.get('enum_bb_agree')} |\n"
        )

    lines.append(
        "\n## Artifacts\n\n"
        f"- `{OUT_RESERVE.relative_to(ROOT)}`\n"
        f"- `{OUT_DIAG.relative_to(ROOT)}`\n"
        f"- `{OUT_HYGIENE.relative_to(ROOT)}`\n"
        f"- `{OUT_BASELINES.relative_to(ROOT)}` (updated with baseline C)\n"
        f"- `{OUT_MD_B.relative_to(ROOT)}`\n"
    )
    OUT_MD_B.write_text("".join(lines), encoding="utf-8")
    print(f"Wrote {OUT_MD_B}", flush=True)

    # Append brief pointer into sprint 01 report
    if OUT_MD.exists():
        t = OUT_MD.read_text(encoding="utf-8")
        pointer = (
            "\n## Sprint 01b completion\n\n"
            "Prioritized gaps closed in `reports/PAPER_RESULTS_SPRINT_01b.md`: "
            "reserve-SOC 10/15/20%, baseline C, H1 failure diagnosis, enum↔B&B hygiene.\n"
        )
        if "Sprint 01b completion" not in t:
            OUT_MD.write_text(t.rstrip() + "\n" + pointer, encoding="utf-8")


def main() -> int:
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--phase",
        choices=["all", "reserve", "h1", "northbound_c", "hygiene", "report"],
        default="all",
    )
    args = ap.parse_args()

    reserve_rows: list[dict] = []
    diag_rows: list[dict] = []
    h1_c: list[dict] = []
    nb_c: list[dict] = []
    hygiene_rows: list[dict] = []

    if args.phase in ("all", "reserve"):
        print("=== 01b reserve SOC ===", flush=True)
        reserve_rows = run_reserve_soc(q=5)
    if args.phase in ("all", "h1"):
        print("=== 01b H1 diagnosis + baseline C ===", flush=True)
        diag_rows, h1_c = run_h1_diagnosis_and_baseline_c(quanta=(5, 2))
        pd.DataFrame(diag_rows).to_csv(OUT_DIAG, index=False)
        print(f"Wrote {OUT_DIAG} ({len(diag_rows)} rows)", flush=True)
    if args.phase in ("all", "northbound_c"):
        print("=== 01b northbound baseline C ===", flush=True)
        nb_c = run_northbound_baseline_c(q=5)
    if args.phase in ("all", "hygiene"):
        print("=== 01b enum/B&B hygiene ===", flush=True)
        hygiene_rows = run_enum_bb_hygiene(q=5)
    if h1_c or nb_c:
        _merge_baselines(h1_c + nb_c)
    if args.phase in ("all", "report", "hygiene"):
        if not reserve_rows and OUT_RESERVE.exists():
            reserve_rows = pd.read_csv(OUT_RESERVE).to_dict(orient="records")
        if not diag_rows and OUT_DIAG.exists():
            diag_rows = pd.read_csv(OUT_DIAG).to_dict(orient="records")
        if not hygiene_rows and OUT_HYGIENE.exists():
            hygiene_rows = pd.read_csv(OUT_HYGIENE).to_dict(orient="records")
        write_reports(reserve_rows, diag_rows, hygiene_rows)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
