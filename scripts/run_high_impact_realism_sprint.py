#!/usr/bin/env python
"""HIGH_IMPACT_REALISM_RESULTS sprint — Stages 1–5 orchestration.

Priorities: realistic speed floor, physical-time HOS, reserve-SOC physical witness,
H1 revalidation, corridor multi-mission placement, coverage curves, critical report.

Does not overwrite FINAL_RESEARCH_FREEZE or manuscript.tex.
"""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import math
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402
import yaml  # noqa: E402

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
)
from morocco_etruck.optimization.multiroute_placement import (  # noqa: E402
    load_multiroute_placement_config,
)
from morocco_etruck.optimization.multiroute_placement_evaluation import (  # noqa: E402
    all_optimal_site_sets,
    evaluate_multiroute_mission,
    prepare_multiroute_placement_context,
    run_multiroute_enumeration,
)
from morocco_etruck.optimization.multiroute_replay import continuous_replay_multiroute  # noqa: E402
from morocco_etruck.optimization.operational_schedule import (  # noqa: E402
    validate_operational_schedule,
    validate_schedule_from_replay_trace,
)
from morocco_etruck.optimization.quantization_audit import audit_solved_actions_exact  # noqa: E402
from morocco_etruck.optimization.replay import replay_solution  # noqa: E402

VEHICLES = {
    "eactros_600": ROOT / "configs/vehicles/eactros_600.yaml",
    "volvo_475": ROOT / "configs/vehicles/volvo_fh_electric_4x2_540kwh.yaml",
}
CFG_PASS2A = ROOT / "configs/optimization/multiroute_placement_pass2a.yaml"
CFG_PORTFOLIO = ROOT / "configs/optimization/multiroute_placement_corridor_portfolio.yaml"
FRIDGE = ROOT / "configs/energy/pass2_tomato_firm_ripe.yaml"
FRIDGE_07 = ROOT / "configs/energy/task07b_thermal_nominal.yaml"

OUT_H1 = ROOT / "results/high_impact_h1_realism.csv"
OUT_RESERVE = ROOT / "results/high_impact_reserve_soc_witness.csv"
OUT_SPEED = ROOT / "results/high_impact_speed_audit.csv"
OUT_PORTFOLIO = ROOT / "results/high_impact_corridor_portfolio.csv"
OUT_COVERAGE = ROOT / "results/high_impact_coverage_vs_budget.csv"
OUT_OPS = ROOT / "results/high_impact_operational_metrics.csv"
OUT_FIG_COV = ROOT / "results/figures/high_impact_coverage_vs_budget.png"
OUT_FIG_H1 = ROOT / "results/figures/high_impact_h1_realism.png"
OUT_MD = ROOT / "reports/HIGH_IMPACT_REALISM_RESULTS.md"

PAYLOAD = 5300.0
ROAD_CENTS = 100.0
DT_MIN = 5
MIN_ADAPT_KMH = 40.0  # operational motorway floor under peak adaptation


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


def _patch_realistic_speed_policy(
    *,
    adapt_peak: bool = True,
    adapt_cont: bool = False,
    min_adapt_kmh: float = MIN_ADAPT_KMH,
):
    """Peak adapt ON with operational floor (not walking-speed crawl)."""
    orig = mpe.load_multiroute_pilot_config

    def wrapped(path, *, root):
        c = orig(path, root=root)
        sp = dict(c.speed_policy)
        sp["adapt_speed_to_peak_power"] = bool(adapt_peak)
        sp["adapt_speed_to_continuous_power"] = bool(adapt_cont)
        sp["min_adapt_speed_kmh"] = float(min_adapt_kmh)
        sp.pop("min_adapt_speed_mps", None)
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


def _speed_audit_from_trace(action_trace: list[dict[str, Any]]) -> dict[str, Any]:
    speeds = []
    below_40 = 0.0
    below_60 = 0.0
    drive_s = 0.0
    for a in action_trace:
        if str(a.get("action_type") or a.get("type") or "") != "DRIVE":
            continue
        dt = float(a.get("dt_s") or 0.0)
        lm = float(a.get("length_m") or 0.0)
        if dt <= 0 or lm <= 0:
            continue
        v_kmh = (lm / dt) * 3.6
        speeds.append(v_kmh)
        drive_s += dt
        if v_kmh < 40.0 - 1e-9:
            below_40 += dt
        if v_kmh < 60.0 - 1e-9:
            below_60 += dt
    if not speeds:
        return {
            "n_drive_arcs": 0,
            "min_arc_speed_kmh": None,
            "p05_arc_speed_kmh": None,
            "median_arc_speed_kmh": None,
            "frac_time_below_40kmh": None,
            "frac_time_below_60kmh": None,
        }
    speeds_sorted = sorted(speeds)
    p05 = speeds_sorted[max(0, int(math.floor(0.05 * (len(speeds_sorted) - 1))))]
    med = speeds_sorted[len(speeds_sorted) // 2]
    return {
        "n_drive_arcs": len(speeds),
        "min_arc_speed_kmh": min(speeds),
        "p05_arc_speed_kmh": p05,
        "median_arc_speed_kmh": med,
        "frac_time_below_40kmh": below_40 / drive_s if drive_s > 0 else None,
        "frac_time_below_60kmh": below_60 / drive_s if drive_s > 0 else None,
    }


def _enrich_realism(
    *,
    row: dict[str, Any],
    inst,
    ctx,
    vehicle,
    actions,
    objective,
    final_E,
    final_t,
    status: str,
) -> dict[str, Any]:
    disc_ok = cont_ok = audit_ok = False
    cont_reason = audit_reason = None
    extras = None
    sched_disc = sched_phys = None
    speed = {}
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
            emit_trace=True,
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
        sched_disc = validate_operational_schedule(
            actions, time_step_min=inst.time_step_min, use_physical_times=False
        )
        if extras is not None and extras.action_trace:
            sched_phys = validate_schedule_from_replay_trace(extras.action_trace)
            speed = _speed_audit_from_trace(extras.action_trace)
    usable = float(vehicle.usable_kwh)
    row.update(
        {
            "discrete_replay_ok": disc_ok,
            "continuous_replay_ok": cont_ok,
            "continuous_replay_reason": cont_reason,
            "audit_ok": audit_ok,
            "audit_reason": audit_reason,
            "charge_kwh_total": None if extras is None else extras.charge_kwh_total,
            "charge_duration_s": None if extras is None else extras.charge_duration_s,
            "drive_duration_s": None if extras is None else extras.drive_duration_s,
            "wait_duration_s": None if extras is None else extras.wait_duration_s,
            "min_soc": None if extras is None else extras.min_soc,
            "arrival_soc": None if extras is None else extras.arrival_soc,
            "road_distance_m": None if extras is None else extras.length_m,
            "E_traction_kwh": None if extras is None else extras.E_traction_kwh,
            "E_refrig_drive_kwh": None if extras is None else extras.E_refrig_drive_kwh,
            "E_refrig_stationary_kwh": (
                None if extras is None else extras.E_refrig_stationary_kwh
            ),
            "terminal_soc_disc": (
                None if final_E is None else float(final_E) / usable
            ),
            "schedule_disc_ok": None if sched_disc is None else sched_disc.ok,
            "schedule_disc_drive_min": (
                None if sched_disc is None else sched_disc.driving_min
            ),
            "schedule_phys_ok": None if sched_phys is None else sched_phys.ok,
            "schedule_phys_drive_min": (
                None if sched_phys is None else sched_phys.driving_min
            ),
            "schedule_phys_charge_min": (
                None if sched_phys is None else sched_phys.charging_min
            ),
            "schedule_phys_cont_max_min": (
                None if sched_phys is None else sched_phys.continuous_driving_max_min
            ),
            "schedule_phys_extra_rest_min": (
                None if sched_phys is None else sched_phys.extra_rest_beyond_charge_min
            ),
            "schedule_phys_charge_rest_overlap_min": (
                None if sched_phys is None else sched_phys.charging_rest_overlap_min
            ),
            "schedule_phys_total_realistic_min": (
                None if sched_phys is None else sched_phys.total_realistic_journey_min
            ),
            "schedule_phys_violation": (
                None if sched_phys is None else sched_phys.violation
            ),
            "schedule_phys_vs_disc_drive_delta_min": (
                None
                if sched_phys is None or sched_disc is None
                else float(sched_phys.driving_min) - float(sched_disc.driving_min)
            ),
            "min_adapt_speed_kmh": MIN_ADAPT_KMH,
            **speed,
            "git_sha": _git_sha(),
        }
    )
    return row


def _build_od(
    *,
    od_id: str,
    vpath: Path,
    q: int,
    soc_frac: float,
    deadline_h: float,
    charger_kw: float,
    fridge: Path,
    max_alts: int = 2,
    speed_policy_override: dict[str, Any] | None = None,
):
    cfg = load_multiroute_pilot_config(
        ROOT / "configs/optimization/multiroute_pilot.yaml", root=ROOT
    )
    if speed_policy_override:
        sp = dict(cfg.speed_policy)
        sp.update(speed_policy_override)
        cfg.speed_policy = sp
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


# ---------------------------------------------------------------------------
# Stage 2 — H1 revalidation with realism gates
# ---------------------------------------------------------------------------


def run_h1_realism(*, quanta: list[int] | None = None) -> list[dict[str, Any]]:
    quanta = quanta or [5]
    cases = [
        ("casa_marrakech", "eactros_600", "settat_benguerir"),
        ("casa_marrakech", "volvo_475", "settat_benguerir"),
        ("casa_agadir", "volvo_475", "settat_benguerir"),
    ]
    install_map = {
        "none": set(),
        "settat_benguerir": {"settat_ca", "benguerir_ca"},
    }
    speed_ov = {
        "adapt_speed_to_peak_power": True,
        "adapt_speed_to_continuous_power": False,
        "min_adapt_speed_kmh": MIN_ADAPT_KMH,
    }
    rows: list[dict[str, Any]] = []
    for q in quanta:
        for od_id, vkey, iname in cases:
            for install_name in ("none", iname):
                t0 = time.perf_counter()
                try:
                    _cfg, path_rows, template, ctx, notes, vehicle = _build_od(
                        od_id=od_id,
                        vpath=VEHICLES[vkey],
                        q=q,
                        soc_frac=0.5,
                        deadline_h=20.0,
                        charger_kw=350.0,
                        fridge=FRIDGE_07,
                        max_alts=2,
                        speed_policy_override=speed_ov,
                    )
                except Exception as exc:  # noqa: BLE001
                    rows.append(
                        {
                            "experiment": "h1_realism",
                            "od_id": od_id,
                            "vehicle_key": vkey,
                            "q": q,
                            "install_set": install_name,
                            "status": "BUILD_ERROR",
                            "error": str(exc),
                            "git_sha": _git_sha(),
                        }
                    )
                    continue
                if not ctx.dem_complete:
                    rows.append(
                        {
                            "experiment": "h1_realism",
                            "od_id": od_id,
                            "vehicle_key": vkey,
                            "q": q,
                            "install_set": install_name,
                            "status": "dem_incomplete",
                            "git_sha": _git_sha(),
                        }
                    )
                    continue
                active = set(install_map[install_name]) & set(template.stations)
                short_mask = shortest_path_allowed_arc_ids(ctx, path_rows, od_id)
                all_mask = frozenset(str(a.arc_id) for a in template.arcs if a.arc_id)
                prep_s = time.perf_counter() - t0
                shortest_csv_m = None
                for r in path_rows:
                    if str(r.get("od_id")) != od_id:
                        continue
                    if str(r.get("method")) == "shortest_distance":
                        shortest_csv_m = float(r["length_m"])
                        break
                for baseline_id, method, mask, mask_name in [
                    ("B", "mrls_fixed_shortest", short_mask, "shortest"),
                    ("D", "mrls_multi_route", all_mask, "all"),
                ]:
                    inst = clone_physics_instance_for_subset(
                        template,
                        active_stations=set(active),
                        allowed_arc_ids=mask,
                        name=f"{baseline_id}|{od_id}|{install_name}|q{q}",
                    )
                    t1 = time.perf_counter()
                    res = solve_mrls(inst, max_seconds=120.0, max_expansions=1_000_000)
                    row: dict[str, Any] = {
                        "experiment": "h1_realism",
                        "baseline_id": baseline_id,
                        "method": method,
                        "od_id": od_id,
                        "vehicle_key": vkey,
                        "payload_kg": PAYLOAD,
                        "soc_frac": 0.5,
                        "q": q,
                        "install_set": install_name,
                        "active_stations": ",".join(sorted(active)),
                        "route_mask": mask_name,
                        "status": res.status.value,
                        "objective": res.objective,
                        "final_E_truck": (
                            res.final_label.E_truck if res.final_label else None
                        ),
                        "final_t_steps": (
                            res.final_label.t if res.final_label else None
                        ),
                        "prep_sec": prep_s,
                        "solve_sec": time.perf_counter() - t1,
                        "shortest_csv_m": shortest_csv_m,
                        "vehicle_sha16": _file_hash(VEHICLES[vkey]),
                        "fridge_sha16": _file_hash(FRIDGE_07),
                        "ccs_cap_kw": vehicle.ccs_max_charge_kw,
                    }
                    row = _enrich_realism(
                        row=row,
                        inst=inst,
                        ctx=ctx,
                        vehicle=vehicle,
                        actions=res.actions or [],
                        objective=res.objective,
                        final_E=row["final_E_truck"],
                        final_t=row["final_t_steps"],
                        status=res.status.value,
                    )
                    if row.get("road_distance_m") and shortest_csv_m:
                        row["detour_ratio"] = float(row["road_distance_m"]) / float(
                            shortest_csv_m
                        )
                        row["detour_km"] = (
                            float(row["road_distance_m"]) - float(shortest_csv_m)
                        ) / 1000.0
                    # Operational credibility gate
                    row["ops_credible"] = bool(
                        row.get("status") == "OPTIMAL"
                        and row.get("audit_ok")
                        and row.get("continuous_replay_ok")
                        and row.get("schedule_phys_ok")
                        and (
                            row.get("min_arc_speed_kmh") is None
                            or float(row["min_arc_speed_kmh"]) + 1e-9 >= MIN_ADAPT_KMH
                        )
                    )
                    rows.append(row)
                    print(
                        f"H1 {baseline_id}|{vkey}|{od_id}|{install_name}|q{q}: "
                        f"{res.status.value} ops={row.get('ops_credible')} "
                        f"min_v={row.get('min_arc_speed_kmh')} "
                        f"phys_drive={row.get('schedule_phys_drive_min')}",
                        flush=True,
                    )
                # Annotate flexibility gain
                cell = [
                    r
                    for r in rows
                    if r.get("od_id") == od_id
                    and r.get("vehicle_key") == vkey
                    and r.get("q") == q
                    and r.get("install_set") == install_name
                ]
                b = next((r for r in cell if r.get("baseline_id") == "B"), None)
                d = next((r for r in cell if r.get("baseline_id") == "D"), None)
                if b and d:
                    d["h1_fixed_infeasible"] = b.get("status") != "OPTIMAL"
                    d["h1_multi_feasible"] = d.get("status") == "OPTIMAL"
                    d["h1_route_flexibility_gain"] = bool(
                        b.get("status") != "OPTIMAL" and d.get("status") == "OPTIMAL"
                    )
                    d["h1_ops_credible_gain"] = bool(
                        b.get("ops_credible") is not True
                        and d.get("ops_credible") is True
                    )
    return rows


# ---------------------------------------------------------------------------
# Stage 1/6 — Reserve SOC physical witness
# ---------------------------------------------------------------------------


def run_reserve_witness(*, quanta: list[int] | None = None) -> list[dict[str, Any]]:
    """Correct 15% cliff interpretation with continuous min_soc + finer q."""
    quanta = quanta or [5, 2]
    rows: list[dict[str, Any]] = []
    orig = _patch_realistic_speed_policy()
    try:
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            # First: solve at policy reserve 10%, record continuous min_soc
            for q in quanta:
                v10 = _policy_vehicle_yaml(VEHICLES["eactros_600"], 0.10, tmp)
                cfg = load_multiroute_placement_config(CFG_PASS2A, root=ROOT)
                context = prepare_multiroute_placement_context(
                    cfg,
                    root=ROOT,
                    demand_name="A_nb_tomato_p5300_soc08",
                    energy_quantum_kwh=q,
                    objective_mode="enroute_incremental_cost",
                    vehicle_yaml=v10,
                    road_cost_per_km=ROAD_CENTS,
                    fridge_yaml=FRIDGE,
                    charger_power_kw=350.0,
                    max_alternatives_for_union=4,
                )
                prep = next(iter(context["prepared"].values()))
                key_of = {s.id: s.station_key for s in cfg.sites}
                for subset_name, site_ids in [
                    ("none", set()),
                    ("benguerir", {"y_benguerir_ac"}),
                    ("settat", {"y_settat_ac"}),
                    ("both", {s.id for s in cfg.sites}),
                ]:
                    active = {key_of[i] for i in site_ids if i in key_of}
                    present = active & set(prep.template.stations)
                    inst = clone_physics_instance_for_subset(
                        prep.template,
                        active_stations=present,
                        name=f"reserve10|{subset_name}|q{q}",
                    )
                    res = solve_mrls(
                        inst,
                        max_seconds=cfg.solver_max_seconds,
                        max_expansions=cfg.solver_max_expansions,
                    )
                    row: dict[str, Any] = {
                        "experiment": "reserve_witness",
                        "policy_reserve": 0.10,
                        "q": q,
                        "subset": subset_name,
                        "installed": ",".join(sorted(site_ids)),
                        "status": res.status.value,
                        "objective": res.objective,
                        "final_E_truck": (
                            res.final_label.E_truck if res.final_label else None
                        ),
                        "final_t_steps": (
                            res.final_label.t if res.final_label else None
                        ),
                    }
                    row = _enrich_realism(
                        row=row,
                        inst=inst,
                        ctx=prep.ctx,
                        vehicle=load_vehicle(v10),
                        actions=res.actions or [],
                        objective=res.objective,
                        final_E=row["final_E_truck"],
                        final_t=row["final_t_steps"],
                        status=res.status.value,
                    )
                    if row.get("min_soc") is not None:
                        ms = float(row["min_soc"])
                        row["physically_meets_reserve_15"] = ms + 1e-9 >= 0.15
                        row["physically_meets_reserve_20"] = ms + 1e-9 >= 0.20
                    rows.append(row)
                    print(
                        f"RESERVE10 q={q} {subset_name}: {res.status.value} "
                        f"min_soc={row.get('min_soc')}",
                        flush=True,
                    )

            # Discrete rebuild at 15% / 20% with q=5 and q=2 (Benguerir)
            for reserve in (0.15, 0.20):
                for q in quanta:
                    vpath = _policy_vehicle_yaml(
                        VEHICLES["eactros_600"], reserve, tmp
                    )
                    cfg = load_multiroute_placement_config(CFG_PASS2A, root=ROOT)
                    context = prepare_multiroute_placement_context(
                        cfg,
                        root=ROOT,
                        demand_name="A_nb_tomato_p5300_soc08",
                        energy_quantum_kwh=q,
                        objective_mode="enroute_incremental_cost",
                        vehicle_yaml=vpath,
                        road_cost_per_km=ROAD_CENTS,
                        fridge_yaml=FRIDGE,
                        charger_power_kw=350.0,
                        max_alternatives_for_union=4,
                    )
                    prep = next(iter(context["prepared"].values()))
                    for subset_name, site_ids in [
                        ("benguerir", {"y_benguerir_ac"}),
                        ("both", {s.id for s in cfg.sites}),
                    ]:
                        key_of = {s.id: s.station_key for s in cfg.sites}
                        active = {key_of[i] for i in site_ids if i in key_of}
                        present = active & set(prep.template.stations)
                        inst = clone_physics_instance_for_subset(
                            prep.template,
                            active_stations=present,
                            name=f"reserve{int(reserve*100)}|{subset_name}|q{q}",
                        )
                        res = solve_mrls(
                            inst,
                            max_seconds=cfg.solver_max_seconds,
                            max_expansions=cfg.solver_max_expansions,
                        )
                        row = {
                            "experiment": "reserve_discrete_rebuild",
                            "policy_reserve": reserve,
                            "q": q,
                            "subset": subset_name,
                            "installed": ",".join(sorted(site_ids)),
                            "status": res.status.value,
                            "objective": res.objective,
                            "final_E_truck": (
                                res.final_label.E_truck if res.final_label else None
                            ),
                            "final_t_steps": (
                                res.final_label.t if res.final_label else None
                            ),
                        }
                        row = _enrich_realism(
                            row=row,
                            inst=inst,
                            ctx=prep.ctx,
                            vehicle=load_vehicle(vpath),
                            actions=res.actions or [],
                            objective=res.objective,
                            final_E=row["final_E_truck"],
                            final_t=row["final_t_steps"],
                            status=res.status.value,
                        )
                        rows.append(row)
                        print(
                            f"RESERVE_DISC {reserve:.0%} q={q} {subset_name}: "
                            f"{res.status.value} min_soc={row.get('min_soc')}",
                            flush=True,
                        )
    finally:
        mpe.load_multiroute_pilot_config = orig
    return rows


# ---------------------------------------------------------------------------
# Stage 3 — Corridor multi-mission placement comparison
# ---------------------------------------------------------------------------


def _mission_masks(context: dict[str, Any], path_rows: list[dict]) -> dict[str, dict]:
    out = {}
    for mid, prep in context["prepared"].items():
        od_id = prep.mission.od_id
        short = shortest_path_allowed_arc_ids(prep.ctx, path_rows, od_id)
        all_mask = frozenset(str(a.arc_id) for a in prep.template.arcs if a.arc_id)
        out[mid] = {"short": short, "all": all_mask, "od_id": od_id, "prep": prep}
    return out


def _eval_portfolio_subset(
    *,
    context: dict[str, Any],
    cfg,
    installed: set[str],
    route_mode: str,
    masks: dict[str, dict],
    method_id: str,
    budget_name: str,
) -> dict[str, Any]:
    """Evaluate one site subset under fixed-shortest or multi-route masks."""
    served_w = 0.0
    total_w = 0.0
    mission_rows = []
    for m in context["missions"]:
        prep = context["prepared"][m.id]
        total_w += float(m.weight)
        key_of = {s.id: s.station_key for s in cfg.sites}
        active_keys = {key_of[i] for i in installed if i in key_of}
        present = active_keys & set(prep.template.stations)
        mask = masks[m.id]["short"] if route_mode == "fixed" else masks[m.id]["all"]
        inst = clone_physics_instance_for_subset(
            prep.template,
            active_stations=present,
            allowed_arc_ids=mask,
            name=f"{method_id}|{m.id}|{budget_name}",
        )
        res = solve_mrls(
            inst,
            max_seconds=cfg.solver_max_seconds,
            max_expansions=cfg.solver_max_expansions,
        )
        served = res.status.value == "OPTIMAL"
        if served:
            # Certify
            disc = replay_solution(inst, res.actions or [], expected_cost=res.objective)
            crep, extras = continuous_replay_multiroute(
                prep.ctx,
                inst,
                res.actions or [],
                discrete_cost=res.objective,
                discrete_t=res.final_label.t if res.final_label else None,
                discrete_E_truck=res.final_label.E_truck if res.final_label else None,
                emit_trace=True,
            )
            audit = audit_solved_actions_exact(
                inst,
                res.actions or [],
                prep_ctx=prep.ctx,
                simulate_drive_fn=simulate_drive_from_soc,
            )
            sched = None
            if extras is not None and extras.action_trace:
                sched = validate_schedule_from_replay_trace(extras.action_trace)
            certified = bool(disc.ok and crep.ok and audit.ok)
            if not certified:
                served = False
            mission_rows.append(
                {
                    "mission_id": m.id,
                    "od_id": m.od_id,
                    "weight": m.weight,
                    "served": served,
                    "certified": certified,
                    "status": res.status.value,
                    "objective": res.objective,
                    "min_soc": None if extras is None else extras.min_soc,
                    "road_km": None
                    if extras is None
                    else extras.length_m / 1000.0,
                    "drive_min_phys": None
                    if extras is None
                    else extras.drive_duration_s / 60.0,
                    "charge_min_phys": None
                    if extras is None
                    else extras.charge_duration_s / 60.0,
                    "schedule_phys_ok": None if sched is None else sched.ok,
                    "charge_rest_overlap_min": (
                        None if sched is None else sched.charging_rest_overlap_min
                    ),
                }
            )
            if served:
                served_w += float(m.weight)
        else:
            mission_rows.append(
                {
                    "mission_id": m.id,
                    "od_id": m.od_id,
                    "weight": m.weight,
                    "served": False,
                    "certified": False,
                    "status": res.status.value,
                    "objective": res.objective,
                }
            )
    cov = served_w / total_w if total_w > 0 else 0.0
    return {
        "method_id": method_id,
        "route_mode": route_mode,
        "budget_name": budget_name,
        "installed": ",".join(sorted(installed)),
        "n_sites": len(installed),
        "coverage": cov,
        "served_weight": served_w,
        "total_weight": total_w,
        "n_missions_served": sum(1 for r in mission_rows if r.get("served")),
        "n_missions": len(mission_rows),
        "missions_json": json.dumps(mission_rows),
        "git_sha": _git_sha(),
    }


def run_corridor_portfolio(*, q: int = 5) -> tuple[list[dict[str, Any]], list[dict]]:
    """Multi-mission coverage-vs-budget under fair planning methods."""
    rows: list[dict[str, Any]] = []
    coverage_curve: list[dict] = []
    orig = _patch_realistic_speed_policy()
    try:
        cfg = load_multiroute_placement_config(CFG_PORTFOLIO, root=ROOT)
        context = prepare_multiroute_placement_context(
            cfg,
            root=ROOT,
            demand_name="corridor_eactros_equal",
            energy_quantum_kwh=q,
            objective_mode="enroute_incremental_cost",
            vehicle_yaml=VEHICLES["eactros_600"],
            road_cost_per_km=ROAD_CENTS,
            fridge_yaml=FRIDGE,
            charger_power_kw=350.0,
            # Match H1 realism: path-union of 2 verified alts (alts=4 pulls DEM-incomplete arcs).
            max_alternatives_for_union=2,
        )
        pilot = load_multiroute_pilot_config(cfg.multiroute_pilot_path, root=ROOT)
        path_rows = pd.read_csv(pilot.path_alternatives_csv).to_dict(orient="records")
        masks = _mission_masks(context, path_rows)
        site_ids = [s.id for s in cfg.sites]
        print(
            f"PORTFOLIO serviceability={context.get('serviceability')}",
            flush=True,
        )
        incomplete = [
            mid
            for mid, prep in context["prepared"].items()
            if not prep.ctx.dem_complete
        ]
        if incomplete:
            print(
                f"WARNING: DEM-incomplete missions excluded from certified coverage: {incomplete}",
                flush=True,
            )

        # Enumerate all subsets for joint multi-route optimum per budget
        enum_cache: dict[frozenset, dict] = {}
        for r in range(0, len(site_ids) + 1):
            for combo in itertools.combinations(site_ids, r):
                installed = set(combo)
                key = frozenset(installed)
                ev = _eval_portfolio_subset(
                    context=context,
                    cfg=cfg,
                    installed=installed,
                    route_mode="multi",
                    masks=masks,
                    method_id="enum_multi",
                    budget_name="all_subsets",
                )
                enum_cache[key] = ev
                print(
                    f"  subset {sorted(installed) or ['∅']}: "
                    f"cov={ev['coverage']:.2f} served={ev['n_missions_served']}",
                    flush=True,
                )

        def _best_under_budget(max_n: int | None, route_mode: str) -> dict:
            best = None
            for key, ev in enum_cache.items():
                if max_n is not None and len(key) > max_n:
                    continue
                if route_mode == "fixed":
                    # Re-evaluate fixed mask for this subset
                    cand = _eval_portfolio_subset(
                        context=context,
                        cfg=cfg,
                        installed=set(key),
                        route_mode="fixed",
                        masks=masks,
                        method_id="enum_fixed",
                        budget_name=f"B{max_n if max_n is not None else 'all'}",
                    )
                else:
                    cand = dict(ev)
                    cand["method_id"] = "joint_multi_opt"
                    cand["budget_name"] = (
                        f"B{max_n if max_n is not None else 'all'}"
                    )
                if best is None or (
                    cand["coverage"],
                    -cand["n_sites"],
                ) > (best["coverage"], -best["n_sites"]):
                    best = cand
            return best  # type: ignore[return-value]

        budget_ns = [("B0", 0), ("B1", 1), ("B2", 2), ("B3", 3), ("Ball", None)]

        # Method A: no infrastructure
        a = dict(enum_cache[frozenset()])
        a["method_id"] = "A_no_infra"
        a["route_mode"] = "multi"
        a["budget_name"] = "B0"
        rows.append(a)

        # Conventional heuristic: one site per direction (Settat pair) then Benguerir
        conventional_order = [
            "y_settat_ca",
            "y_settat_ac",
            "y_benguerir_ca",
            "y_benguerir_ac",
        ]
        for bname, nmax in budget_ns:
            if nmax is None:
                conv_set = set(conventional_order)
            else:
                conv_set = set(conventional_order[:nmax])
            # B: fixed-route + conventional
            b_row = _eval_portfolio_subset(
                context=context,
                cfg=cfg,
                installed=conv_set,
                route_mode="fixed",
                masks=masks,
                method_id="B_fixed_conventional",
                budget_name=bname,
            )
            rows.append(b_row)
            # C: fixed-route + optimized sites under budget
            c_row = _best_under_budget(nmax, "fixed")
            c_row = dict(c_row)
            c_row["method_id"] = "C_fixed_optimized"
            c_row["budget_name"] = bname
            rows.append(c_row)
            # D: multi-route + conventional sites
            d_row = _eval_portfolio_subset(
                context=context,
                cfg=cfg,
                installed=conv_set,
                route_mode="multi",
                masks=masks,
                method_id="D_multi_conventional",
                budget_name=bname,
            )
            rows.append(d_row)
            # E: joint multi-route optimized
            e_row = _best_under_budget(nmax, "multi")
            e_row = dict(e_row)
            e_row["method_id"] = "E_joint_multi_opt"
            e_row["budget_name"] = bname
            rows.append(e_row)
            # F: greedy — repeatedly add site with largest marginal coverage
            greedy: set[str] = set()
            remaining = set(site_ids)
            target_n = len(site_ids) if nmax is None else int(nmax)
            while len(greedy) < target_n and remaining:
                best_add = None
                best_cov = -1.0
                for s in sorted(remaining):
                    trial = greedy | {s}
                    ev = enum_cache[frozenset(trial)]
                    if ev["coverage"] > best_cov + 1e-15 or (
                        abs(ev["coverage"] - best_cov) < 1e-15
                        and (best_add is None or s < best_add)
                    ):
                        best_cov = float(ev["coverage"])
                        best_add = s
                if best_add is None:
                    break
                greedy.add(best_add)
                remaining.remove(best_add)
            f_row = dict(enum_cache[frozenset(greedy)])
            f_row["method_id"] = "F_greedy_multi"
            f_row["budget_name"] = bname
            f_row["installed"] = ",".join(sorted(greedy))
            f_row["n_sites"] = len(greedy)
            rows.append(f_row)

            coverage_curve.append(
                {
                    "budget": bname,
                    "max_sites": nmax if nmax is not None else len(site_ids),
                    "A_no_infra": a["coverage"] if bname == "B0" else None,
                    "B_fixed_conventional": b_row["coverage"],
                    "C_fixed_optimized": c_row["coverage"],
                    "D_multi_conventional": d_row["coverage"],
                    "E_joint_multi_opt": e_row["coverage"],
                    "F_greedy_multi": f_row["coverage"],
                    "E_sites": e_row["installed"],
                    "C_sites": c_row["installed"],
                    "F_sites": f_row["installed"],
                }
            )
            print(
                f"BUDGET {bname}: E_cov={e_row['coverage']:.2f} "
                f"C_cov={c_row['coverage']:.2f} "
                f"B_cov={b_row['coverage']:.2f} E_sites={e_row['installed']}",
                flush=True,
            )
    finally:
        mpe.load_multiroute_pilot_config = orig
    return rows, coverage_curve


# ---------------------------------------------------------------------------
# Figures + report
# ---------------------------------------------------------------------------


def write_figures(h1_rows: list[dict], coverage_curve: list[dict]) -> None:
    OUT_FIG_COV.parent.mkdir(parents=True, exist_ok=True)
    if h1_rows:
        df = pd.DataFrame(h1_rows)
        gain = df[
            (df.get("baseline_id") == "D")
            if "baseline_id" in df.columns
            else [False] * len(df)
        ]
        if "h1_route_flexibility_gain" in df.columns:
            sub = df[df["baseline_id"] == "D"].copy()
            sub = sub[sub["install_set"] != "none"]
            fig, ax = plt.subplots(figsize=(8, 4.2))
            labels = [
                f"{r.od_id}\n{r.vehicle_key}\nq={r.q}"
                for r in sub.itertuples()
            ]
            colors = [
                "#2ca02c" if r.h1_route_flexibility_gain else "#d62728"
                for r in sub.itertuples()
            ]
            ax.bar(range(len(sub)), [1 if g else 0 for g in sub["h1_route_flexibility_gain"]], color=colors)
            ax.set_xticks(range(len(sub)))
            ax.set_xticklabels(labels, fontsize=7)
            ax.set_ylabel("Route-flexibility gain (1=yes)")
            ax.set_title(
                f"H1 under realism gates (min adapt {MIN_ADAPT_KMH:.0f} km/h)"
            )
            ax.set_ylim(0, 1.2)
            fig.tight_layout()
            fig.savefig(OUT_FIG_H1, dpi=150)
            plt.close(fig)

    if coverage_curve:
        cdf = pd.DataFrame(coverage_curve)
        fig, ax = plt.subplots(figsize=(7.5, 4.5))
        x = list(range(len(cdf)))
        for col, label, style in [
            ("B_fixed_conventional", "B fixed+conventional", "o--"),
            ("C_fixed_optimized", "C fixed+optimized", "s--"),
            ("D_multi_conventional", "D multi+conventional", "o-"),
            ("E_joint_multi_opt", "E joint multi opt", "s-"),
            ("F_greedy_multi", "F greedy multi", "^-"),
        ]:
            if col in cdf.columns:
                ax.plot(x, cdf[col], style, label=label)
        ax.set_xticks(x)
        ax.set_xticklabels(list(cdf["budget"]))
        ax.set_ylabel("Weighted mission coverage")
        ax.set_xlabel("Infrastructure budget")
        ax.set_ylim(-0.05, 1.05)
        ax.set_title("Corridor portfolio: coverage vs budget")
        ax.legend(fontsize=8)
        ax.grid(True, alpha=0.3)
        fig.tight_layout()
        fig.savefig(OUT_FIG_COV, dpi=150)
        plt.close(fig)


def write_report(
    *,
    h1_rows: list[dict],
    reserve_rows: list[dict],
    portfolio_rows: list[dict],
    coverage_curve: list[dict],
) -> None:
    h1 = pd.DataFrame(h1_rows) if h1_rows else pd.DataFrame()
    res = pd.DataFrame(reserve_rows) if reserve_rows else pd.DataFrame()
    port = pd.DataFrame(portfolio_rows) if portfolio_rows else pd.DataFrame()
    cov = pd.DataFrame(coverage_curve) if coverage_curve else pd.DataFrame()

    findings = []
    # Finding 1: H1
    if not h1.empty and "h1_route_flexibility_gain" in h1.columns:
        gains = h1[(h1["baseline_id"] == "D") & (h1["install_set"] != "none")]
        n_gain = int(gains["h1_route_flexibility_gain"].fillna(False).sum())
        n_ops = int(gains["h1_ops_credible_gain"].fillna(False).sum()) if "h1_ops_credible_gain" in gains.columns else 0
        n_tot = len(gains)
        detours = gains["detour_ratio"].dropna() if "detour_ratio" in gains.columns else pd.Series(dtype=float)
        findings.append(
            {
                "id": 1,
                "title": "Energy-aware multi-route planning restores service where fixed-shortest fails",
                "claim": (
                    f"{n_gain}/{n_tot} charged H1 cells retain fixed→multi feasibility gain "
                    f"under min_adapt={MIN_ADAPT_KMH:.0f} km/h; "
                    f"{n_ops}/{n_tot} also pass physical-schedule + speed + audit gates."
                ),
                "detour": (
                    f"Detour ratios: {detours.min():.3f}–{detours.max():.3f}"
                    if len(detours)
                    else "n/a"
                ),
            }
        )

    # Finding 2: portfolio coverage
    if not cov.empty and "E_joint_multi_opt" in cov.columns:
        e_b1 = cov.loc[cov["budget"] == "B1", "E_joint_multi_opt"]
        c_b1 = cov.loc[cov["budget"] == "B1", "C_fixed_optimized"]
        b_b1 = cov.loc[cov["budget"] == "B1", "B_fixed_conventional"]
        e_ball = cov.loc[cov["budget"] == "Ball", "E_joint_multi_opt"]
        findings.append(
            {
                "id": 2,
                "title": "Joint multi-route placement vs fixed-route planning (same budget)",
                "claim": (
                    f"At B1: E={float(e_b1.iloc[0]) if len(e_b1) else 'n/a'}, "
                    f"C_fixed_opt={float(c_b1.iloc[0]) if len(c_b1) else 'n/a'}, "
                    f"B_fixed_conv={float(b_b1.iloc[0]) if len(b_b1) else 'n/a'}; "
                    f"at Ball: E={float(e_ball.iloc[0]) if len(e_ball) else 'n/a'}."
                ),
            }
        )

    # Finding 3: reserve reinterpretation
    if not res.empty:
        w = res[res["experiment"] == "reserve_witness"]
        served = w[(w["subset"] == "benguerir") & (w["status"] == "OPTIMAL")]
        if len(served):
            ms = served["min_soc"].dropna()
            meets15 = served["physically_meets_reserve_15"].fillna(False).any() if "physically_meets_reserve_15" in served.columns else False
            disc15 = res[
                (res["experiment"] == "reserve_discrete_rebuild")
                & (res["policy_reserve"] == 0.15)
            ]
            disc15_opt = (disc15["status"] == "OPTIMAL").any() if len(disc15) else False
            findings.append(
                {
                    "id": 3,
                    "title": "Reserve-SOC policy: physical witness vs discrete rebuild",
                    "claim": (
                        f"At 10% discrete policy with Benguerir, continuous min_soc="
                        f"{float(ms.min()):.3f}–{float(ms.max()):.3f} across q; "
                        f"physically meets 15%={meets15}. "
                        f"Discrete rebuild at 15% finds OPTIMAL={disc15_opt}. "
                        "Do not claim physical impossibility from coarse discrete unserved alone."
                    ),
                }
            )

    lines = [
        "# HIGH_IMPACT_REALISM_RESULTS",
        "",
        f"Git SHA: `{_git_sha()}`  ",
        f"Date: 2026-11-15  ",
        f"Speed policy floor under peak adaptation: **{MIN_ADAPT_KMH:.0f} km/h** "
        "(segments requiring slower travel are power-infeasible, not crawled).",
        "",
        "This package prioritizes transportation decisions (coverage, infrastructure "
        "efficiency, operational time) under realistic physics — not a paper about "
        "numerical failures.",
        "",
        "## 1. Strongest experimentally supported positive findings",
        "",
    ]
    if not findings:
        lines.append("_No completed experimental findings yet — run full sprint._")
    for f in findings:
        lines.append(f"### Finding {f['id']}: {f['title']}")
        lines.append("")
        lines.append(f"{f['claim']}")
        if f.get("detour"):
            lines.append(f"")
            lines.append(f"Detour evidence: {f['detour']}")
        lines.append("")

    lines += [
        "## 2. Evidence and physical validity",
        "",
        "- Same canonical DEM graph; route restriction via `allowed_arc_ids` (no rebuild).",
        "- Continuous physics replay + `audit_solved_actions_exact` required for certified service.",
        "- Operational schedule uses **physical** `dt_s` from continuous-replay action traces.",
        f"- Peak-power speed adaptation floor = {MIN_ADAPT_KMH:.0f} km/h (`min_adapt_speed_kmh`).",
        "- eActros CCS acceptance cap = 400 kW (manufacturer public constant envelope).",
        "- Candidate sites: ADM-named service areas with verified directed OSM access; "
        "chargers remain hypothetical HGV installations.",
        "",
        "## 3. Fair comparisons against alternative planning methods",
        "",
        "| Method | Description |",
        "|---|---|",
        "| A | No new infrastructure |",
        "| B | Fixed-shortest + conventional site order (Settat pair then Benguerir) |",
        "| C | Fixed-shortest + optimized sites under budget |",
        "| D | Multi-route + conventional sites |",
        "| E | Joint multi-route optimized placement |",
        "| F | Greedy multi-route marginal coverage |",
        "",
    ]
    if not cov.empty:
        lines.append("Coverage vs budget (weighted missions):")
        lines.append("")
        lines.append("| " + " | ".join(str(c) for c in cov.columns) + " |")
        lines.append("|" + "|".join(["---"] * len(cov.columns)) + "|")
        for _, r in cov.iterrows():
            lines.append(
                "| "
                + " | ".join(
                    "" if pd.isna(r[c]) else (f"{r[c]:.3f}" if isinstance(r[c], float) else str(r[c]))
                    for c in cov.columns
                )
                + " |"
            )
        lines.append("")

    lines += [
        "## 4. Sensitivity ranges and exceptions",
        "",
    ]
    if not res.empty:
        lines.append(
            "- Reserve 10%/15%/20%: see `results/high_impact_reserve_soc_witness.csv`. "
            "Prior sprint-01b '15% cliff' must be read with the physical witness."
        )
    if not h1.empty and "ops_credible" in h1.columns:
        failed_ops = h1[(h1["status"] == "OPTIMAL") & (h1["ops_credible"] != True)]
        lines.append(
            f"- Optimal but not ops-credible rows: {len(failed_ops)} "
            "(schedule / speed / audit failures — reported, not hidden)."
        )
    lines += [
        "",
        "## 5. Remaining scientific weaknesses",
        "",
        "- Four-site bidirectional universe is nontrivial vs 2-site northbound case study, "
        "but still a corridor research proxy — not nationwide Moroccan freight demand.",
        "- Equal mission weights are documented proxies, not observed annual OD volumes.",
        "- No grid-capacity evidence for proposed chargers; electrical feasibility unclaimed.",
        "- SOC-dependent CCS taper unavailable from OEM; constant envelope + sensitivity needed.",
        "- Moroccan axle-law compliance unverified (GCM within manufacturer screen only).",
        "- Refrigeration energy remains small vs traction under cool tomato assumptions — "
        "quantify, do not inflate.",
        "",
        "## 6. Journal-contribution assessment",
        "",
        "A persuasive contribution is supportable **if** Findings 1–2 hold under the realism "
        "gates: (i) route flexibility as an operational coverage instrument under identical "
        "infrastructure, and (ii) coverage-vs-budget advantage (or parity, honestly reported) "
        "for joint multi-route placement vs fixed-route heuristics. Solver certification and "
        "discretization analysis remain methodological validation, not the main selling point.",
        "",
        "If H1 gains collapse under the 40 km/h floor or physical HOS, do not weaken "
        "constraints — investigate legitimate alternatives and report negative results.",
        "",
        "## 7. Prioritized remaining experiments",
        "",
        "1. Confirm Finding 1 at q=2 with the same realism gates.",
        "2. Add Volvo corridor portfolio (same missions) as vehicle-sensitivity panel.",
        "3. Ambient/refrigeration sensitivity without inflating duty cycles.",
        "4. Limited DEM grade noise / aero-rolling resistance bands (pre-registered).",
        "5. Only then revise `paper/manuscript.tex`.",
        "",
        "## Reproduction",
        "",
        "```bash",
        "python -m pytest tests/unit/test_multi_vehicle_06c.py "
        "tests/unit/test_operational_schedule.py -q",
        "python scripts/run_high_impact_realism_sprint.py --phase all",
        "# phases: h1 | reserve | portfolio | figures | report | all",
        "```",
        "",
        "## Artifacts",
        "",
        f"- `{OUT_H1.relative_to(ROOT).as_posix()}`",
        f"- `{OUT_RESERVE.relative_to(ROOT).as_posix()}`",
        f"- `{OUT_PORTFOLIO.relative_to(ROOT).as_posix()}`",
        f"- `{OUT_COVERAGE.relative_to(ROOT).as_posix()}`",
        f"- `{OUT_FIG_H1.relative_to(ROOT).as_posix()}`",
        f"- `{OUT_FIG_COV.relative_to(ROOT).as_posix()}`",
        f"- `{OUT_MD.relative_to(ROOT).as_posix()}`",
        "",
    ]
    OUT_MD.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote {OUT_MD}", flush=True)


def _write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    pd.DataFrame(rows).to_csv(path, index=False)
    print(f"Wrote {path} ({len(rows)} rows)", flush=True)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--phase",
        default="all",
        choices=["h1", "reserve", "portfolio", "figures", "report", "all"],
    )
    ap.add_argument("--q", type=int, default=5)
    args = ap.parse_args()

    h1_rows: list[dict] = []
    reserve_rows: list[dict] = []
    portfolio_rows: list[dict] = []
    coverage_curve: list[dict] = []

    if args.phase in ("h1", "all"):
        h1_rows = run_h1_realism(quanta=[args.q])
        # Merge with prior quanta so q=2 does not erase q=5.
        if OUT_H1.exists():
            prev = pd.read_csv(OUT_H1)
            new = pd.DataFrame(h1_rows)
            if "q" in prev.columns and "q" in new.columns:
                keep = prev[prev["q"].astype(int) != int(args.q)]
                h1_rows = pd.concat([keep, new], ignore_index=True).to_dict(
                    orient="records"
                )
        _write_csv(OUT_H1, h1_rows)
    elif OUT_H1.exists():
        h1_rows = pd.read_csv(OUT_H1).to_dict(orient="records")

    if args.phase in ("reserve", "all"):
        reserve_rows = run_reserve_witness(quanta=[args.q, 2] if args.phase == "all" else [args.q])
        _write_csv(OUT_RESERVE, reserve_rows)
    elif OUT_RESERVE.exists():
        reserve_rows = pd.read_csv(OUT_RESERVE).to_dict(orient="records")

    if args.phase in ("portfolio", "all"):
        portfolio_rows, coverage_curve = run_corridor_portfolio(q=args.q)
        _write_csv(OUT_PORTFOLIO, portfolio_rows)
        _write_csv(OUT_COVERAGE, coverage_curve)
    else:
        if OUT_PORTFOLIO.exists():
            portfolio_rows = pd.read_csv(OUT_PORTFOLIO).to_dict(orient="records")
        if OUT_COVERAGE.exists():
            coverage_curve = pd.read_csv(OUT_COVERAGE).to_dict(orient="records")

    if args.phase in ("figures", "all"):
        write_figures(h1_rows, coverage_curve)
    if args.phase == "report":
        # Curated narrative lives in reports/HIGH_IMPACT_REALISM_RESULTS.md.
        # Regenerate the auto draft only with --phase report (does not run on --phase all).
        write_report(
            h1_rows=h1_rows,
            reserve_rows=reserve_rows,
            portfolio_rows=portfolio_rows,
            coverage_curve=coverage_curve,
        )


if __name__ == "__main__":
    main()
