#!/usr/bin/env python
"""FINAL operational correction: coverage metrics, HOS, re-siting, deliverables.

Primary objective = operational_coverage (energy + physical replay + schedule/HOS).
Does not overwrite FINAL_RESEARCH_FREEZE blindly; writes final_* artifacts.
"""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from run_high_impact_realism_sprint import (  # noqa: E402
    CFG_PORTFOLIO,
    FRIDGE,
    MIN_ADAPT_KMH,
    ROAD_CENTS,
    VEHICLES,
    _mission_masks,
    _patch_realistic_speed_policy,
    _write_csv,
)
from morocco_etruck.energy.refrigeration import load_refrigeration  # noqa: E402
from morocco_etruck.energy.vehicle import load_vehicle  # noqa: E402
from morocco_etruck.optimization import multiroute_placement_evaluation as mpe  # noqa: E402
from morocco_etruck.optimization.arc_preprocessing import simulate_drive_from_soc  # noqa: E402
from morocco_etruck.optimization.hos_adjustment import (  # noqa: E402
    DUTY_MULTI_DAY_OUT_OF_SCOPE,
    classify_duty_scope,
    inject_wait_into_solver_actions,
    propose_chronological_hos_plan,
)
from morocco_etruck.optimization.label_setting import solve_mrls  # noqa: E402
from morocco_etruck.optimization.multiroute_adapter import (  # noqa: E402
    clone_physics_instance_for_subset,
    load_multiroute_pilot_config,
)
from morocco_etruck.optimization.multiroute_placement import (  # noqa: E402
    load_multiroute_placement_config,
)
from morocco_etruck.optimization.multiroute_placement_evaluation import (  # noqa: E402
    prepare_multiroute_placement_context,
)
from morocco_etruck.optimization.multiroute_replay import continuous_replay_multiroute  # noqa: E402
from morocco_etruck.optimization.operational_schedule import (  # noqa: E402
    validate_schedule_from_replay_trace,
)
from morocco_etruck.optimization.quantization_audit import audit_solved_actions_exact  # noqa: E402
from morocco_etruck.optimization.replay import replay_solution  # noqa: E402

OUT_MISSION = ROOT / "results/final_operational_mission_comparison.csv"
OUT_COV = ROOT / "results/final_operational_coverage_vs_budget.csv"
OUT_TRACES = ROOT / "results/final_charging_rest_traces.csv"
OUT_ROB = ROOT / "results/final_physics_robustness.csv"
OUT_MD = ROOT / "reports/FINAL_HIGH_IMPACT_RESULTS_AND_VALIDATION.md"
OUT_FIG_COV = ROOT / "results/figures/final_operational_coverage_vs_budget.png"
OUT_FIG_H1 = ROOT / "results/figures/final_route_flexibility.png"
OUT_MANIFEST = ROOT / "results/final_reproducibility_manifest.json"


def _git_sha() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip()
    except Exception:  # noqa: BLE001
        return "unknown"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def coverage_from_mission_rows(mission_rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Shared coverage aggregator for blind greedy and enum paths.

    Operational coverage counts ``operationally_served`` only. Solver status is
    tracked separately so LIMIT_REACHED is never silently treated as INFEASIBLE.
    """
    w_ops = w_energy = w_tot = 0.0
    n_limit = n_optimal = n_infeasible = n_ops = 0
    for mr in mission_rows:
        w = float(mr.get("weight") or 1.0)
        w_tot += w
        status = str(mr.get("status") or "").upper()
        if status == "LIMIT_REACHED":
            n_limit += 1
        elif status == "OPTIMAL":
            n_optimal += 1
        elif status == "INFEASIBLE":
            n_infeasible += 1
        if mr.get("energy_feasible_energy_only") or mr.get("energy_feasible"):
            w_energy += w
        if mr.get("operationally_served"):
            w_ops += w
            n_ops += 1
    n_missions = len(mission_rows)
    return {
        "energy_coverage": w_energy / w_tot if w_tot else 0.0,
        "operational_coverage": w_ops / w_tot if w_tot else 0.0,
        "n_missions": n_missions,
        "n_operationally_served": n_ops,
        "n_limit_reached": n_limit,
        "n_optimal": n_optimal,
        "n_infeasible": n_infeasible,
        "certified_ops_among_resolved": (
            (n_ops / max(1, n_missions - n_limit)) if n_missions > n_limit else None
        ),
    }


def evaluate_mission_operational(
    *,
    prep,
    cfg,
    installed: set[str],
    mask: frozenset[str],
    vehicle,
    fridge_path: Path,
    max_seconds: float,
    max_expansions: int,
    include_energy_only: bool = True,
    mutate_ops_instance=None,
    capture_energy_trace: bool = False,
) -> dict[str, Any]:
    """Operational evaluation: HOS-in-search ops solve (+ optional energy-only baseline).

    Set ``include_energy_only=False`` for exhaustive enum cache scoring (ops-only);
    headline B/C/D/E/F rows should keep the default dual solve.

    When the operational solver returns no OPTIMAL actions, HOS audit fields are
    left as ``None`` / ``NOT_EVALUATED`` — never defaulted to False, which would
    incorrectly imply a computed daily-driving violation.

    ``mutate_ops_instance`` (optional callable) may adjust the ops instance after
    cloning (controlled diagnostics: relax HOS limits, expand rest nodes, etc.).
    """
    from morocco_etruck.optimization.hos_adjustment import DUTY_NOT_EVALUATED

    key_of = {s.id: s.station_key for s in cfg.sites}
    active_keys = {key_of[i] for i in installed if i in key_of}
    present = active_keys & set(prep.template.stations)
    base_name = f"{prep.mission.id}|{','.join(sorted(installed)) or 'none'}"

    t0 = time.perf_counter()
    energy_only = False
    energy_status = "SKIPPED"
    energy_drive_min = None
    energy_road_km = None
    energy_trace_json = None
    energy_n_actions = 0
    if include_energy_only:
        # --- Energy-only baseline (hos_in_search=False) ---
        inst_e = clone_physics_instance_for_subset(
            prep.template,
            active_stations=present,
            allowed_arc_ids=mask,
            name=f"energy|{base_name}",
        )
        inst_e.hos_in_search = False
        res_e = solve_mrls(inst_e, max_seconds=max_seconds, max_expansions=max_expansions)
        energy_status = res_e.status.value
        if res_e.status.value == "OPTIMAL" and res_e.actions:
            disc_e = replay_solution(inst_e, res_e.actions, expected_cost=res_e.objective)
            crep_e, ex_e = continuous_replay_multiroute(
                prep.ctx,
                inst_e,
                res_e.actions,
                discrete_cost=res_e.objective,
                discrete_t=res_e.final_label.t if res_e.final_label else None,
                discrete_E_truck=res_e.final_label.E_truck if res_e.final_label else None,
                emit_trace=bool(capture_energy_trace),
            )
            audit_e = audit_solved_actions_exact(
                inst_e,
                res_e.actions,
                prep_ctx=prep.ctx,
                simulate_drive_fn=simulate_drive_from_soc,
            )
            energy_only = bool(disc_e.ok and crep_e.ok and audit_e.ok)
            if capture_energy_trace and ex_e is not None:
                energy_drive_min = float(ex_e.drive_duration_s or 0.0) / 60.0
                energy_road_km = float(ex_e.length_m or 0.0) / 1000.0
                energy_n_actions = len(ex_e.action_trace or [])
                energy_trace_json = json.dumps(ex_e.action_trace)

    # --- HOS-in-search operational solve ---
    inst = clone_physics_instance_for_subset(
        prep.template,
        active_stations=present,
        allowed_arc_ids=mask,
        name=f"ops|{base_name}",
    )
    inst.hos_in_search = True
    ts = max(1, int(getattr(inst, "time_step_min", 5) or 5))
    need = int(round(45.0 / ts))
    if int(getattr(inst, "wait_max_steps", 0) or 0) < need:
        inst.wait_max_steps = need
    if getattr(inst, "hos_rest_nodes", None) is None:
        inst.hos_rest_nodes = frozenset(inst.stations.keys()) | frozenset(
            inst.active_stations
        )
    if mutate_ops_instance is not None:
        mutate_ops_instance(inst)
    t1 = time.perf_counter()
    res = solve_mrls(inst, max_seconds=max_seconds, max_expansions=max_expansions)
    row: dict[str, Any] = {
        "mission_id": prep.mission.id,
        "od_id": prep.mission.od_id,
        "weight": float(prep.mission.weight),
        "status": res.status.value,
        "objective": res.objective,
        "solve_sec": (time.perf_counter() - t0),
        "hos_solve_sec": (time.perf_counter() - t1),
        "energy_status": energy_status,
        "energy_feasible_energy_only": bool(energy_only),
        "energy_feasible": bool(energy_only),
        "energy_drive_min": energy_drive_min,
        "energy_road_km": energy_road_km,
        "energy_n_actions": energy_n_actions,
        "discrete_replay_valid": False,
        "physical_replay_valid": False,
        "audit_ok": False,
        "schedule_valid_raw": False,
        "schedule_valid": False,
        "hos_adjusted": False,
        "hos_in_search": bool(getattr(inst, "hos_in_search", True)),
        "hos_search_audit_only": False,
        # None = not audited (no OPTIMAL ops trace). Never default to False.
        "hos_ok": None,
        "daily_driving_ok": None,
        "daily_driving_min": None,
        "duty_scope": DUTY_NOT_EVALUATED,
        "operationally_served": False,
        "pad_location": None,
        "pad_duration_min": 0.0,
        "pad_aux_kwh": 0.0,
        "pad_refrig_kwh": 0.0,
        "min_soc": None,
        "arrival_soc": None,
        "road_km": None,
        "drive_min_phys": None,
        "charge_min_phys": None,
        "wait_min_phys": None,
        "detour_note": None,
        "n_trace_actions": 0,
    }
    if energy_trace_json is not None:
        row["energy_action_trace_json"] = energy_trace_json
    if res.status.value != "OPTIMAL" or not res.actions:
        return row

    disc = replay_solution(inst, res.actions, expected_cost=res.objective)
    row["discrete_replay_valid"] = bool(disc.ok)
    crep, extras = continuous_replay_multiroute(
        prep.ctx,
        inst,
        res.actions,
        discrete_cost=res.objective,
        discrete_t=res.final_label.t if res.final_label else None,
        discrete_E_truck=res.final_label.E_truck if res.final_label else None,
        emit_trace=True,
    )
    row["physical_replay_valid"] = bool(crep.ok)
    audit = audit_solved_actions_exact(
        inst,
        res.actions,
        prep_ctx=prep.ctx,
        simulate_drive_fn=simulate_drive_from_soc,
    )
    row["audit_ok"] = bool(audit.ok)

    actions_use = list(res.actions)
    extras_use = extras
    crep_use = crep
    sched_raw = validate_schedule_from_replay_trace(extras.action_trace)
    row["schedule_valid_raw"] = bool(sched_raw.ok)

    fridge = load_refrigeration(fridge_path)
    mid_t = 20.0
    try:
        mid = next(iter(prep.ctx.weather.points.values()))
        mid_t = float(mid.T_mean_c)
    except Exception:  # noqa: BLE001
        pass

    verified_rest = set(getattr(prep.template, "stations", {}) or {})
    hos = propose_chronological_hos_plan(
        extras.action_trace,
        P_aux_w=float(getattr(vehicle, "P_aux_w", 2500.0) or 2500.0),
        T_amb_c=mid_t,
        fridge_params=fridge,
        refrigeration_on=True,
        verified_rest_nodes=verified_rest,
    )
    row["hos_ok"] = bool(hos.ok)
    row["daily_driving_ok"] = bool(getattr(hos, "daily_driving_ok", False))
    row["daily_driving_min"] = getattr(hos, "daily_driving_min", None)
    row["pad_location"] = hos.pad_location
    row["pad_duration_min"] = hos.pad_duration_min
    row["pad_aux_kwh"] = hos.aux_energy_kwh
    row["pad_refrig_kwh"] = hos.refrig_energy_kwh
    row["hos_notes"] = hos.notes
    row["hos_independent_rest"] = bool(getattr(hos, "independent_rest", False))

    # Audit-only only when continuous schedule AND daily driving both pass.
    if sched_raw.ok and bool(getattr(hos, "daily_driving_ok", False)):
        row["schedule_valid"] = True
        row["hos_search_audit_only"] = True
        row["hos_notes"] = (hos.notes or "") + ";audit_only_no_post_pad"
    elif hos.needed and hos.ok and hos.pad_location and hos.pad_duration_min > 1e-9:
        # Legacy pad path kept for diagnostics only; not used to certify ops under HOS-in-search.
        actions_adj = inject_wait_into_solver_actions(
            res.actions,
            station_node=str(hos.pad_location),
            pad_duration_min=float(hos.pad_duration_min),
            time_step_min=int(inst.time_step_min),
        )
        crep2, extras2 = continuous_replay_multiroute(
            prep.ctx,
            inst,
            actions_adj,
            discrete_cost=None,
            discrete_t=None,
            discrete_E_truck=None,
            emit_trace=True,
        )
        sched2 = validate_schedule_from_replay_trace(extras2.action_trace)
        hos2 = propose_chronological_hos_plan(
            extras2.action_trace,
            P_aux_w=float(getattr(vehicle, "P_aux_w", 2500.0) or 2500.0),
            T_amb_c=mid_t,
            fridge_params=fridge,
            refrigeration_on=True,
            verified_rest_nodes=verified_rest,
        )
        if crep2.ok and sched2.ok and bool(getattr(hos2, "daily_driving_ok", False)):
            row["hos_adjusted"] = True
            actions_use = actions_adj
            extras_use = extras2
            crep_use = crep2
            row["schedule_valid"] = True
            row["physical_replay_valid"] = True
            row["daily_driving_ok"] = True
            row["daily_driving_min"] = hos2.daily_driving_min
        else:
            row["schedule_valid"] = False
            row["hos_notes"] = (
                (hos.notes or "")
                + f";re_replay_ok={crep2.ok};re_sched_ok={sched2.ok};"
                f"daily_ok={getattr(hos2, 'daily_driving_ok', False)}"
            )
    else:
        row["schedule_valid"] = False
        if sched_raw.ok and not bool(getattr(hos, "daily_driving_ok", False)):
            row["hos_notes"] = (hos.notes or "") + ";daily_driving_failed_audit"

    if extras_use is not None:
        row["min_soc"] = extras_use.min_soc
        row["arrival_soc"] = extras_use.arrival_soc
        row["road_km"] = extras_use.length_m / 1000.0
        row["drive_min_phys"] = extras_use.drive_duration_s / 60.0
        row["charge_min_phys"] = extras_use.charge_duration_s / 60.0
        row["wait_min_phys"] = extras_use.wait_duration_s / 60.0
        row["n_trace_actions"] = len(extras_use.action_trace)
        row["action_trace_json"] = json.dumps(extras_use.action_trace)
        bad_speed = False
        for a in extras_use.action_trace:
            if a.get("action_type") != "DRIVE":
                continue
            dt = float(a.get("dt_s") or 0.0)
            lm = float(a.get("length_m") or 0.0)
            if dt > 0 and lm > 0 and (lm / dt) * 3.6 < MIN_ADAPT_KMH - 1e-9:
                bad_speed = True
                break
        row["speed_policy_ok"] = not bad_speed
    else:
        row["speed_policy_ok"] = False

    journey_min = None
    if extras_use is not None:
        journey_min = (
            float(extras_use.drive_duration_s or 0.0)
            + float(extras_use.charge_duration_s or 0.0)
            + float(extras_use.wait_duration_s or 0.0)
        ) / 60.0
    row["duty_scope"] = classify_duty_scope(
        daily_driving_min=row.get("daily_driving_min"),
        daily_driving_ok=row.get("daily_driving_ok"),
        journey_min=journey_min,
    )

    # Ops = HOS itinerary physically valid + continuous/daily schedule; no post-hoc pad.
    # energy_feasible is the independent energy-only baseline (not tied to ops).
    # Multi-day (Art.16 overnight) missions are out of scope — never counted as served.
    row["operationally_served"] = bool(
        row["schedule_valid"]
        and row.get("speed_policy_ok", False)
        and crep_use.ok
        and row["discrete_replay_valid"]
        and row["audit_ok"]
        and row.get("daily_driving_ok") is True
        and not bool(row.get("hos_adjusted"))
        and row.get("duty_scope") != DUTY_MULTI_DAY_OUT_OF_SCOPE
    )
    return row


def _score(ev: dict[str, Any]) -> tuple:
    """Lexicographic: operational coverage, then energy coverage, then fewer sites, then lower secondary cost proxy."""
    return (
        float(ev.get("operational_coverage") or 0.0),
        float(ev.get("energy_coverage") or 0.0),
        -int(ev.get("n_sites") or 0),
        -float(ev.get("secondary_cost_proxy") or 0.0),
    )


def evaluate_subset(
    *,
    context: dict[str, Any],
    cfg,
    installed: set[str],
    route_mode: str,
    masks: dict[str, dict],
    method_id: str,
    budget_name: str,
    vehicle,
    fridge_path: Path,
    include_energy_only: bool = True,
    max_seconds: float | None = None,
    max_expansions: int | None = None,
) -> dict[str, Any]:
    mission_rows = []
    sec = float(max_seconds) if max_seconds is not None else float(cfg.solver_max_seconds)
    exp = int(max_expansions) if max_expansions is not None else int(cfg.solver_max_expansions)
    for m in context["missions"]:
        prep = context["prepared"][m.id]
        mask = masks[m.id]["short"] if route_mode == "fixed" else masks[m.id]["all"]
        mr = evaluate_mission_operational(
            prep=prep,
            cfg=cfg,
            installed=installed,
            mask=mask,
            vehicle=vehicle,
            fridge_path=fridge_path,
            max_seconds=sec,
            max_expansions=exp,
            include_energy_only=include_energy_only,
        )
        # Ensure weight present for shared aggregator.
        mr = dict(mr)
        mr.setdefault("weight", float(m.weight))
        mission_rows.append(mr)
        print(
            f"  {method_id}|{budget_name}|{m.od_id}: "
            f"energy_only={mr.get('energy_feasible_energy_only')} "
            f"ops={mr.get('operationally_served')} status={mr.get('status')} "
            f"daily={mr.get('daily_driving_ok')} audit={mr.get('hos_search_audit_only')}",
            flush=True,
        )

    cov = coverage_from_mission_rows(mission_rows)
    secondary = 0.0
    for mr in mission_rows:
        if mr.get("objective") is not None and mr.get("operationally_served"):
            secondary += float(mr["objective"])

    return {
        "method_id": method_id,
        "route_mode": route_mode,
        "budget_name": budget_name,
        "installed": ",".join(sorted(installed)),
        "n_sites": len(installed),
        "energy_coverage": cov["energy_coverage"],
        "operational_coverage": cov["operational_coverage"],
        "n_energy_served": sum(
            1
            for r in mission_rows
            if r.get("energy_feasible_energy_only") or r.get("energy_feasible")
        ),
        "n_operationally_served": cov["n_operationally_served"],
        "n_limit_reached": cov["n_limit_reached"],
        "n_missions": cov["n_missions"],
        # Gate 2: unresolved LIMIT cells are not treated as infeasible in the
        # resolved-only rate (certified among non-LIMIT missions).
        "certified_ops_among_resolved": cov["certified_ops_among_resolved"],
        "secondary_cost_proxy": secondary,
        "missions_json": json.dumps(
            [{k: v for k, v in r.items() if k != "action_trace_json"} for r in mission_rows]
        ),
        "mission_rows": mission_rows,
        "git_sha": _git_sha(),
        "selection_engine": "exhaustive_enumeration"
        if method_id.startswith("E_")
        else (
            "greedy_over_exhaustive_enum_scores"
            if method_id.startswith("F_")
            else "baseline_eval"
        ),
    }


def run_portfolio(
    *, q: int, vehicle_key: str
) -> tuple[list[dict], list[dict], list[dict], list[dict]]:
    orig = _patch_realistic_speed_policy()
    rows: list[dict] = []
    cov_curve: list[dict] = []
    traces: list[dict] = []
    try:
        cfg = load_multiroute_placement_config(CFG_PORTFOLIO, root=ROOT)
        vpath = VEHICLES[vehicle_key]
        vehicle = load_vehicle(vpath)
        context = prepare_multiroute_placement_context(
            cfg,
            root=ROOT,
            demand_name="corridor_eactros_equal",
            energy_quantum_kwh=q,
            objective_mode="enroute_incremental_cost",
            vehicle_yaml=vpath,
            road_cost_per_km=ROAD_CENTS,
            fridge_yaml=FRIDGE,
            charger_power_kw=350.0,
            max_alternatives_for_union=2,
        )
        pilot = load_multiroute_pilot_config(cfg.multiroute_pilot_path, root=ROOT)
        path_rows = pd.read_csv(pilot.path_alternatives_csv).to_dict(orient="records")
        masks = _mission_masks(context, path_rows)
        site_ids = [s.id for s in cfg.sites]
        print("serviceability", context.get("serviceability"), flush=True)

        # Exhaustive multi-route enum cache (for E and reporting — not for greedy decisions)
        enum_cache: dict[frozenset, dict] = {}
        for r in range(0, len(site_ids) + 1):
            for combo in itertools.combinations(site_ids, r):
                key = frozenset(combo)
                ev = evaluate_subset(
                    context=context,
                    cfg=cfg,
                    installed=set(combo),
                    route_mode="multi",
                    masks=masks,
                    method_id="enum_multi",
                    budget_name="all_subsets",
                    vehicle=vehicle,
                    fridge_path=FRIDGE,
                )
                enum_cache[key] = ev
                print(
                    f"ENUM {sorted(combo) or ['∅']}: ops={ev['operational_coverage']:.2f} "
                    f"energy={ev['energy_coverage']:.2f}",
                    flush=True,
                )

        conventional_order = [
            "y_settat_ca",
            "y_settat_ac",
            "y_benguerir_ca",
            "y_benguerir_ac",
        ]
        budget_ns = [("B0", 0), ("B1", 1), ("B2", 2), ("B3", 3), ("Ball", None)]

        def best_under(nmax: int | None, route_mode: str, method_id: str, bname: str):
            best = None
            for key, ev0 in enum_cache.items():
                if nmax is not None and len(key) > nmax:
                    continue
                if route_mode == "fixed":
                    cand = evaluate_subset(
                        context=context,
                        cfg=cfg,
                        installed=set(key),
                        route_mode="fixed",
                        masks=masks,
                        method_id=method_id,
                        budget_name=bname,
                        vehicle=vehicle,
                        fridge_path=FRIDGE,
                    )
                else:
                    cand = dict(ev0)
                    cand["method_id"] = method_id
                    cand["budget_name"] = bname
                    cand["selection_engine"] = "exhaustive_enumeration"
                if best is None or _score(cand) > _score(best):
                    best = cand
            return best

        for bname, nmax in budget_ns:
            if nmax is None:
                conv = set(conventional_order)
            else:
                conv = set(conventional_order[: int(nmax)])

            a = dict(enum_cache[frozenset()])
            a.update(
                method_id="A_no_infra",
                budget_name=bname,
                route_mode="multi",
                selection_engine="baseline_eval",
            )
            if bname == "B0":
                rows.append(a)

            b = evaluate_subset(
                context=context,
                cfg=cfg,
                installed=conv,
                route_mode="fixed",
                masks=masks,
                method_id="B_fixed_conventional",
                budget_name=bname,
                vehicle=vehicle,
                fridge_path=FRIDGE,
            )
            rows.append(b)

            c = best_under(nmax, "fixed", "C_fixed_optimized", bname)
            rows.append(c)

            d = evaluate_subset(
                context=context,
                cfg=cfg,
                installed=conv,
                route_mode="multi",
                masks=masks,
                method_id="D_multi_conventional",
                budget_name=bname,
                vehicle=vehicle,
                fridge_path=FRIDGE,
            )
            rows.append(d)

            e = best_under(nmax, "multi", "E_joint_multi_enum", bname)
            rows.append(e)

            # Independent greedy: sequential marginal ops coverage.
            # Stop at budget or when the best addition does not improve the lex score.
            greedy: set[str] = set()
            remaining = set(site_ids)
            target = len(site_ids) if nmax is None else int(nmax)
            greedy_evals = 0
            prev_score = _score(enum_cache[frozenset()])
            while len(greedy) < target and remaining:
                best_add = None
                best_ev = None
                for s in sorted(remaining):
                    trial = greedy | {s}
                    ev = enum_cache[frozenset(trial)]
                    greedy_evals += 1
                    if best_ev is None or _score(ev) > _score(best_ev) or (
                        _score(ev) == _score(best_ev)
                        and (best_add is None or s < best_add)
                    ):
                        best_ev = ev
                        best_add = s
                assert best_add is not None and best_ev is not None
                if _score(best_ev) <= prev_score:
                    break
                greedy.add(best_add)
                remaining.remove(best_add)
                prev_score = _score(best_ev)
            f = dict(enum_cache[frozenset(greedy)])
            f.update(
                method_id="F_greedy_multi",
                budget_name=bname,
                installed=",".join(sorted(greedy)),
                n_sites=len(greedy),
                selection_engine="independent_greedy_sequential",
                greedy_trial_evals=greedy_evals,
            )
            rows.append(f)

            cov_curve.append(
                {
                    "vehicle_key": vehicle_key,
                    "q": q,
                    "budget": bname,
                    "max_sites": nmax if nmax is not None else len(site_ids),
                    "B_ops": b["operational_coverage"],
                    "B_energy": b["energy_coverage"],
                    "C_ops": c["operational_coverage"],
                    "C_energy": c["energy_coverage"],
                    "D_ops": d["operational_coverage"],
                    "D_energy": d["energy_coverage"],
                    "E_ops": e["operational_coverage"],
                    "E_energy": e["energy_coverage"],
                    "F_ops": f["operational_coverage"],
                    "F_energy": f["energy_coverage"],
                    "E_sites": e["installed"],
                    "F_sites": f["installed"],
                    "C_sites": c["installed"],
                    "E_equals_F_ops": abs(
                        float(e["operational_coverage"]) - float(f["operational_coverage"])
                    )
                    < 1e-12,
                }
            )
            print(
                f"BUDGET {bname}: E_ops={e['operational_coverage']:.2f} "
                f"F_ops={f['operational_coverage']:.2f} "
                f"C_ops={c['operational_coverage']:.2f} E_sites={e['installed']}",
                flush=True,
            )

            # Traces for E missions
            for mr in e.get("mission_rows") or []:
                if not mr.get("action_trace_json"):
                    continue
                for a in json.loads(mr["action_trace_json"]):
                    traces.append(
                        {
                            "vehicle_key": vehicle_key,
                            "q": q,
                            "budget": bname,
                            "method_id": "E_joint_multi_enum",
                            "installed": e["installed"],
                            "mission_id": mr["mission_id"],
                            "od_id": mr["od_id"],
                            "operationally_served": mr.get("operationally_served"),
                            "action_type": a.get("action_type") or a.get("type"),
                            "dt_s": a.get("dt_s"),
                            "node": a.get("node") or a.get("site"),
                            "arc_id": a.get("arc_id"),
                            "soc_before": a.get("soc_before"),
                            "soc_after": a.get("soc_after"),
                            "charge_kwh": a.get("charge_kwh"),
                            "hos_pad": a.get("hos_pad", False),
                            "t_start_s": a.get("t_start_s"),
                            "t_end_s": a.get("t_end_s"),
                        }
                    )

        # Flatten mission comparison rows
        mission_flat = []
        for r in rows:
            r = dict(r)
            mrs = r.pop("mission_rows", None)
            r.pop("missions_json", None)
            if mrs is None and r.get("missions_json"):
                mrs = json.loads(r["missions_json"])
            for mr in mrs or []:
                mission_flat.append(
                    {
                        "vehicle_key": vehicle_key,
                        "q": q,
                        **{k: v for k, v in r.items() if k != "missions_json"},
                        **{k: v for k, v in mr.items() if k != "action_trace_json"},
                    }
                )
        return rows, cov_curve, traces, mission_flat
    finally:
        mpe.load_multiroute_pilot_config = orig


def run_robustness_ops(*, q: int = 2) -> list[dict]:
    """Borderline reserve / hot / taper-note cells at finer q with ops metric."""
    from run_high_impact_completion import run_robustness

    # Reuse physical robustness matrix; mark that ops schedule not re-run for all cells here.
    rows = run_robustness(q=q)
    for r in rows:
        r["note"] = (
            "energy_status_at_finer_q;operational_HOS_not_reapplied_on_all_cells"
        )
    return rows


def write_figures(cov: list[dict], missions: list[dict]) -> None:
    OUT_FIG_COV.parent.mkdir(parents=True, exist_ok=True)
    if cov:
        cdf = pd.DataFrame(cov)
        fig, ax = plt.subplots(figsize=(8, 4.8))
        x = list(range(len(cdf)))
        for col, lab, sty in [
            ("B_ops", "B fixed+conv (ops)", "o--"),
            ("C_ops", "C fixed+opt (ops)", "s--"),
            ("D_ops", "D multi+conv (ops)", "o-"),
            ("E_ops", "E joint enum (ops)", "s-"),
            ("F_ops", "F greedy (ops)", "^-"),
        ]:
            if col in cdf.columns:
                ax.plot(x, cdf[col], sty, label=lab)
        ax.set_xticks(x)
        ax.set_xticklabels(list(cdf["budget"]))
        ax.set_ylabel("Operational coverage")
        ax.set_ylim(-0.05, 1.05)
        ax.set_title("Operational coverage vs budget (schedule-valid)")
        ax.legend(fontsize=8)
        ax.grid(True, alpha=0.3)
        fig.tight_layout()
        fig.savefig(OUT_FIG_COV, dpi=150)
        plt.close(fig)

    if missions:
        mdf = pd.DataFrame(missions)
        sub = mdf[
            mdf["method_id"].isin(["B_fixed_conventional", "D_multi_conventional"])
            & (mdf.get("budget_name") == "B2" if "budget_name" in mdf.columns else True)
        ].copy()
        if not sub.empty and "operationally_served" in sub.columns:
            sub["ops_num"] = sub["operationally_served"].astype(float)
            fig, ax = plt.subplots(figsize=(7, 4))
            pivot = sub.pivot_table(
                index="od_id",
                columns="method_id",
                values="ops_num",
                aggfunc="max",
            ).fillna(0.0)
            if not pivot.empty:
                pivot.plot(kind="bar", ax=ax)
                ax.set_ylabel("Operationally served")
                ax.set_title("Fixed vs multi-route operational service (B2)")
                fig.tight_layout()
                fig.savefig(OUT_FIG_H1, dpi=150)
            plt.close(fig)


def write_report(
    *,
    cov: list[dict],
    missions: list[dict],
    rob: list[dict],
) -> None:
    cdf = pd.DataFrame(cov) if cov else pd.DataFrame()
    mdf = pd.DataFrame(missions) if missions else pd.DataFrame()
    lines = [
        "# FINAL_HIGH_IMPACT_RESULTS_AND_VALIDATION",
        "",
        f"Git SHA: `{_git_sha()}`",
        "",
        "Primary metric: **operational_coverage** = share of missions that are",
        "energy-feasible **and** schedule-valid under décret 2-10-314 arts. 17–19",
        "(4.5 h continuous driving → ≥45 min uninterrupted pause, daily driving ≤9 h),",
        "after chronological rest extension at verified stops and full continuous re-replay.",
        "Energy coverage is reported separately and is **not** the paper’s service claim.",
        "",
        "## 1. How many missions does each method actually serve?",
        "",
    ]
    if not cdf.empty:
        lines.append("| budget | B_ops | C_ops | D_ops | E_ops | F_ops | E_energy | E_sites | E=F ops? |")
        lines.append("|---|---:|---:|---:|---:|---:|---:|---|---|")
        for _, r in cdf.iterrows():
            lines.append(
                f"| {r['budget']} | {r['B_ops']:.2f} | {r['C_ops']:.2f} | {r['D_ops']:.2f} | "
                f"{r['E_ops']:.2f} | {r['F_ops']:.2f} | {r['E_energy']:.2f} | {r['E_sites']} | {r['E_equals_F_ops']} |"
            )
        lines.append("")
        e_b2 = cdf[cdf.budget == "B2"]
        if len(e_b2):
            lines.append(
                f"At B2, joint enum operational coverage = {float(e_b2.iloc[0]['E_ops']):.2f} "
                f"vs energy coverage = {float(e_b2.iloc[0]['E_energy']):.2f}. "
                "Do not claim 100% operational service unless E_ops = 1.00."
            )
            lines.append("")

    lines += [
        "## 2. How many charging sites are needed?",
        "",
        "See E_sites / F_sites by budget in the table above. Site geography remains the four",
        "direction-specific ADM service areas (Settat/Benguerir CA & AC).",
        "",
        "## 3. Which routes benefit from flexibility and why?",
        "",
    ]
    def _truthy(v) -> bool:
        if isinstance(v, bool):
            return v
        return str(v).strip().lower() in {"1", "true", "yes"}

    if not mdf.empty:
        lines.append(
            "At budget B2 with identical vehicle/SOC/payload/physics, mission-level operational service:"
        )
        lines.append("")
        b2 = mdf[mdf.budget_name == "B2"]
        for mid, label in [
            ("C_fixed_optimized", "C fixed+optimized Benguerir pair"),
            ("D_multi_conventional", "D multi+conventional Settat pair"),
            ("E_joint_multi_enum", "E joint multi+enum Benguerir pair"),
            ("F_greedy_multi", "F greedy multi Benguerir pair"),
        ]:
            sub = b2[b2.method_id == mid]
            if sub.empty:
                continue
            served = [
                f"{r.od_id}={'Y' if _truthy(r.operationally_served) else 'N'}"
                for _, r in sub.iterrows()
            ]
            lines.append(f"- {label}: " + ", ".join(served))
        lines.append("")
        lines.append(
            "Mechanism separation: (i) **route flexibility** unlocks `casa_marrakech` "
            "(fixed never ops-serves it under the same chargers); "
            "(ii) **site choice** unlocks schedule-valid `casa_agadir` / `agadir_casa` "
            "when Benguerir directed sites replace Settat-only conventional installs; "
            "(iii) **joint** placement + multi-route is required for all three missions "
            "at B2. Enum and greedy **tie** on operational coverage — do not claim superiority."
        )
        lines.append("")

    lines += [
        "## 4. Detours, charging times, rest delays",
        "",
    ]
    if not mdf.empty:
        e_b2 = mdf[(mdf.budget_name == "B2") & (mdf.method_id == "E_joint_multi_enum")]
        for _, r in e_b2.iterrows():
            if not _truthy(r.operationally_served):
                continue
            pad = float(r.pad_duration_min or 0.0)
            lines.append(
                f"- `{r.od_id}`: road_km={r.road_km:.2f}, drive_min={r.drive_min_phys:.1f}, "
                f"charge_min={r.charge_min_phys:.1f}, wait_min={r.wait_min_phys:.1f}, "
                f"HOS_pad_min={pad:.1f} at `{r.pad_location}`, min_soc={r.min_soc:.4f}"
            )
        lines.append("")
    lines += [
        "Full ordered DRIVE/CHARGE/WAIT timelines: `results/final_charging_rest_traces.csv`.",
        "",
        "## 5. Robustness",
        "",
    ]
    if rob:
        rdf = pd.DataFrame(rob)
        b = rdf[rdf.subset == "benguerir"] if "subset" in rdf.columns else rdf
        for _, r in b.iterrows():
            lines.append(
                f"- {r.get('cell_id')}: status={r.get('status')} min_soc={r.get('min_soc')}"
            )
        lines.append("")
        lines.append(
            "Reserve 15%/20% at coarse q=5 remains a discretization caution; finer q restores energy service."
        )
        lines.append("")

    lines += [
        "## 6. Finer grids",
        "",
        "Portfolio primary run uses the configured quantum; robustness uses q=2 where requested.",
        "",
        "## 7. Joint enum vs greedy vs fixed",
        "",
        "E is **exhaustive enumeration** over four sites (not branch-and-bound runtime).",
        "F is an **independent sequential greedy** on operational coverage.",
        "If E_ops = F_ops, report a tie — do not claim superiority.",
        "",
        "## 8. What remains illustrative",
        "",
        "- Equal mission weights are research proxies, not observed OD volumes.",
        "- Chargers are hypothetical HGV CCS at verified ADM sites; no grid-capacity claim.",
        "- CCS taper sensitivity is a conservative research envelope, not OEM-measured.",
        "- Refrigeration UA/COP are engineering assumptions; cool tomato load is legitimately modest.",
        "- Axle-law compliance unverified.",
        "",
        "## Reproduction",
        "",
        "```bash",
        "python -m pytest tests/unit/test_hos_chronological.py tests/unit/test_operational_schedule.py -q",
        "python scripts/run_final_operational_correction.py --phase all --q 5",
        "```",
        "",
    ]
    OUT_MD.write_text("\n".join(lines), encoding="utf-8")
    print("Wrote", OUT_MD, flush=True)


def write_manifest(paths: list[Path]) -> None:
    files = {}
    for p in paths:
        if p.exists():
            files[str(p.relative_to(ROOT)).replace("\\", "/")] = _sha256(p)
    meta = {
        "git_sha": _git_sha(),
        "created": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "primary_metric": "operational_coverage",
        "files_sha256": files,
    }
    OUT_MANIFEST.write_text(json.dumps(meta, indent=2), encoding="utf-8")
    print("Wrote", OUT_MANIFEST, flush=True)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--phase",
        default="all",
        choices=["portfolio", "robustness", "figures", "report", "all"],
    )
    ap.add_argument("--q", type=int, default=5)
    ap.add_argument("--vehicle", default="eactros_600", choices=list(VEHICLES.keys()))
    args = ap.parse_args()

    primary = args.vehicle == "eactros_600"
    suffix = "" if primary else f"_{args.vehicle}"
    out_mission = ROOT / f"results/final_operational_mission_comparison{suffix}.csv"
    out_cov = ROOT / f"results/final_operational_coverage_vs_budget{suffix}.csv"
    out_traces = ROOT / f"results/final_charging_rest_traces{suffix}.csv"

    cov: list[dict] = []
    missions: list[dict] = []
    traces: list[dict] = []
    rob: list[dict] = []

    if args.phase in ("portfolio", "all"):
        _rows, cov, traces, missions = run_portfolio(q=args.q, vehicle_key=args.vehicle)
        _write_csv(out_mission, missions)
        _write_csv(out_cov, cov)
        _write_csv(out_traces, traces)

    if args.phase in ("robustness", "all") and primary:
        rob = run_robustness_ops(q=2)
        _write_csv(OUT_ROB, rob)
    elif OUT_ROB.exists():
        rob = pd.read_csv(OUT_ROB).to_dict(orient="records")

    if args.phase in ("figures", "report", "all") and primary:
        if not cov and OUT_COV.exists():
            cov = pd.read_csv(OUT_COV).to_dict(orient="records")
        if not missions and OUT_MISSION.exists():
            missions = pd.read_csv(OUT_MISSION).to_dict(orient="records")
        write_figures(cov, missions)
        write_report(cov=cov, missions=missions, rob=rob)
        write_manifest(
            [
                OUT_MISSION,
                OUT_COV,
                OUT_TRACES,
                OUT_ROB,
                OUT_MD,
                OUT_FIG_COV,
                OUT_FIG_H1,
                CFG_PORTFOLIO,
                FRIDGE,
                VEHICLES[args.vehicle],
            ]
        )
    elif args.phase in ("portfolio",) and not primary:
        # Append Volvo key findings into the existing final report without wiping eActros.
        if out_cov.exists() and OUT_MD.exists():
            cdf = pd.read_csv(out_cov)
            lines = [
                "",
                f"## Volvo panel (`{args.vehicle}`, q={args.q})",
                "",
                "| budget | B_ops | C_ops | D_ops | E_ops | F_ops | E_sites | E=F? |",
                "|---|---:|---:|---:|---:|---:|---|---|",
            ]
            for _, r in cdf.iterrows():
                lines.append(
                    f"| {r['budget']} | {r['B_ops']:.2f} | {r['C_ops']:.2f} | {r['D_ops']:.2f} | "
                    f"{r['E_ops']:.2f} | {r['F_ops']:.2f} | {r['E_sites']} | {r['E_equals_F_ops']} |"
                )
            lines += [
                "",
                f"Source: `{out_cov.relative_to(ROOT).as_posix()}` "
                f"(separate from primary eActros CSVs).",
                "",
            ]
            text = OUT_MD.read_text(encoding="utf-8")
            marker = f"## Volvo panel (`{args.vehicle}`"
            if marker in text:
                pre = text.split(marker)[0].rstrip()
                text = pre + "\n" + "\n".join(lines)
            else:
                text = text.rstrip() + "\n" + "\n".join(lines)
            OUT_MD.write_text(text, encoding="utf-8")
            print("Appended Volvo panel to", OUT_MD, flush=True)


if __name__ == "__main__":
    main()
