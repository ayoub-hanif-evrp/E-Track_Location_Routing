#!/usr/bin/env python
"""PAPER_RESULTS_SPRINT_01 — integrity + matched H1 pilots + site evidence + schedule.

Does not overwrite FINAL_RESEARCH_FREEZE or manuscript.tex.
Writes new artifacts under results/paper_results_* and reports/PAPER_RESULTS_SPRINT_01.md.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import subprocess
import sys
import time
from collections import defaultdict
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
from morocco_etruck.optimization.arc_preprocessing import simulate_drive_from_soc  # noqa: E402
from morocco_etruck.optimization.label_setting import solve_mrls  # noqa: E402
from morocco_etruck.optimization import multiroute_placement_evaluation as mpe  # noqa: E402
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
)
from morocco_etruck.optimization.quantization_audit import audit_solved_actions_exact  # noqa: E402
from morocco_etruck.optimization.replay import replay_solution  # noqa: E402

VEHICLES = {
    "eactros_600": ROOT / "configs/vehicles/eactros_600.yaml",
    "volvo_475": ROOT / "configs/vehicles/volvo_fh_electric_4x2_540kwh.yaml",
}
CFG_PASS2A = ROOT / "configs/optimization/multiroute_placement_pass2a.yaml"
FRIDGE = ROOT / "configs/energy/pass2_tomato_firm_ripe.yaml"
FRIDGE_07 = ROOT / "configs/energy/task07b_thermal_nominal.yaml"
CAND_CSV = ROOT / "data/processed/candidate_sites.csv"

OUT_BASELINES = ROOT / "results/paper_results_matched_baselines.csv"
OUT_SITES = ROOT / "results/paper_results_site_candidates.csv"
OUT_SCHED = ROOT / "results/paper_results_operational_schedule.csv"
OUT_SOC100 = ROOT / "results/paper_results_soc100_placement.csv"
OUT_FIG = ROOT / "results/figures/paper_results_sprint_01_h1_feasibility.png"
OUT_MD = ROOT / "reports/PAPER_RESULTS_SPRINT_01.md"

PAYLOAD = 5300.0
ROAD_CENTS = 100.0
DT_MIN = 5


def _git_sha() -> str:
    try:
        return (
            subprocess.check_output(
                ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
            ).strip()
        )
    except Exception:  # noqa: BLE001
        return "unknown"


def _file_hash(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()[:16]


def _hours_to_steps(h: float) -> int:
    return int(round(h * 60.0 / DT_MIN))


def _patch_peak_speed_policy(
    *,
    adapt_peak: bool = True,
    adapt_cont: bool = False,
):
    """Match authoritative Moroccan robustness baseline (peak adaptation ON)."""
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


def write_site_candidates() -> list[dict[str, Any]]:
    """ADM directory evidence + OSM access status; no fabricated geometry."""
    rows_in = list(csv.DictReader(CAND_CSV.open(encoding="utf-8")))
    out: list[dict[str, Any]] = []
    for r in rows_in:
        token = (r.get("name_token") or "").strip().lower()
        direction = (r.get("travel_direction") or "").strip()
        match = (r.get("location_match_status") or "").strip()
        access = (r.get("directed_access_status") or "").strip()
        topo = (r.get("match_status") or "").strip()
        # Prospective corridor candidates of interest
        in_scope = token in {
            "benguerir",
            "settat",
            "marrakech",
            "oum rbii",
            "amskroud",
            "berrchid",
        }
        if not in_scope:
            continue
        hgv_chg = "unverified"
        elec = "unverified"
        accept = "rejected_unmatched_osm"
        if topo == "access_topology_ok" and match == "matched_osm":
            accept = "accepted_topology_ok_hypothetical_charger"
        elif access == "opposite_carriageway_only":
            accept = "rejected_opposite_carriageway"
        elif match == "unmatched":
            accept = "prospective_official_name_only_no_osm_geometry"
        out.append(
            {
                "official_adm_name": r.get("official_name"),
                "partner": r.get("partner"),
                "adm_direction": direction,
                "name_token": token,
                "adm_source": r.get("source")
                or "https://www.adm.co.ma/fr/gares-de-peage-et-aires-de-services",
                "osm_lat": r.get("lat"),
                "osm_lon": r.get("lon"),
                "osm_id": r.get("osm_id"),
                "location_match_status": match,
                "location_match_confidence": r.get("location_match_confidence"),
                "directed_access_status": access,
                "hgv_access_status": r.get("hgv_access_status") or "unknown",
                "connection_distance_m": r.get("connection_distance_m"),
                "entrance_path_m": r.get("entrance_path_m"),
                "exit_path_m": r.get("exit_path_m"),
                "topology_status": topo,
                "existing_hgv_hp_charger_verified": hgv_chg,
                "electrical_power_evidence": elec,
                "candidate_acceptance": accept,
                "enabled_in_pass2a_northbound": (
                    "yes"
                    if token in ("benguerir", "settat")
                    and direction.replace(" ", "") in ("Agadir→Casablanca", "Agadir->Casablanca")
                    and accept.startswith("accepted")
                    else "no"
                ),
                "notes": (
                    "Service-area name ≠ 350 kW HGV charger. "
                    "HGV access unknown unless independently certified. "
                    + (r.get("evidence") or "")
                )[:500],
            }
        )
    OUT_SITES.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(out).to_csv(OUT_SITES, index=False)
    print(f"Wrote {OUT_SITES} ({len(out)} rows)", flush=True)
    return out


def run_soc100_placement(*, quanta: list[int]) -> list[dict[str, Any]]:
    cfg = load_multiroute_placement_config(CFG_PASS2A, root=ROOT)
    demand = "A_nb_tomato_p5300_soc10"
    assert demand in cfg.demand_scenarios, "missing explicit SOC100 demand"
    rows: list[dict[str, Any]] = []
    orig = _patch_peak_speed_policy(adapt_peak=True, adapt_cont=False)
    try:
        rows = _run_soc100_placement_inner(cfg, demand=demand, quanta=quanta)
    finally:
        mpe.load_multiroute_pilot_config = orig
    OUT_SOC100.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(OUT_SOC100, index=False)
    return rows


def _run_soc100_placement_inner(cfg, *, demand: str, quanta: list[int]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for q in quanta:
        t0 = time.perf_counter()
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
        e_init = int(prep.template.E_truck_init)
        usable = float(prep.ctx.vehicle.usable_kwh)
        soc = e_init / usable
        assert abs(soc - 1.0) < 0.02, f"SOC100 demand produced soc={soc}"
        # Mission feasibility for each subset once per q (actions/audit).
        subset_cache: dict[str, dict[str, Any]] = {}
        from morocco_etruck.optimization.multiroute_placement_evaluation import (
            active_keys_for_installed,
        )

        for subset_name, installed in [
            ("none", set()),
            ("settat_only", {"y_settat_ac"}),
            ("benguerir_only", {"y_benguerir_ac"}),
            ("both", {s.id for s in cfg.sites}),
        ]:
            ev = evaluate_multiroute_mission(
                prep,
                installed=installed,
                sites=cfg.sites,
                max_seconds=cfg.solver_max_seconds,
                max_expansions=cfg.solver_max_expansions,
            )
            sched = None
            audit_ok = None
            if ev.served:
                active = active_keys_for_installed(cfg.sites, installed, prep.template)
                inst = clone_physics_instance_for_subset(
                    prep.template, active_stations=active, name=f"soc100|{subset_name}"
                )
                res = solve_mrls(
                    inst,
                    max_seconds=cfg.solver_max_seconds,
                    max_expansions=cfg.solver_max_expansions,
                )
                if res.status.value == "OPTIMAL" and res.actions:
                    sched = validate_operational_schedule(
                        res.actions, time_step_min=prep.template.time_step_min
                    )
                    audit = audit_solved_actions_exact(
                        inst,
                        res.actions,
                        prep_ctx=prep.ctx,
                        simulate_drive_fn=simulate_drive_from_soc,
                    )
                    audit_ok = audit.ok
            subset_cache[subset_name] = {
                "installed": installed,
                "ev": ev,
                "sched": sched,
                "audit_ok": audit_ok,
            }
            print(f"SOC100 q={q} subset {subset_name}: served={ev.served}", flush=True)

        for budget in ("B0", "B1", "Ball"):
            enum_rows, best, _ = run_multiroute_enumeration(
                cfg,
                root=ROOT,
                demand_name=demand,
                capex_name="equal",
                budget_name=budget,
                context=context,
            )
            opt_sets = all_optimal_site_sets(enum_rows)
            feas = [
                r
                for r in enum_rows
                if r.get("budget_ok") and r.get("certified")
            ]
            greedy = None
            if feas:
                greedy = sorted(
                    feas,
                    key=lambda r: (
                        -float(r.get("coverage_serviceable") or 0),
                        int(r.get("n_sites") or 99),
                        float(r.get("secondary_cost") or 1e18),
                    ),
                )[0]
            for subset_name, cached in subset_cache.items():
                ev = cached["ev"]
                sched = cached["sched"]
                rows.append(
                    {
                        "experiment": "soc100_placement",
                        "demand": demand,
                        "q": q,
                        "budget": budget,
                        "subset_eval": subset_name,
                        "installed": ",".join(sorted(cached["installed"])),
                        "E_truck_init": e_init,
                        "soc_frac": round(soc, 4),
                        "payload_kg": PAYLOAD,
                        "served": bool(ev.served),
                        "status": ev.status,
                        "disc_ok": ev.discrete_replay_ok,
                        "cont_ok": ev.continuous_replay_ok,
                        "audit_ok": cached["audit_ok"],
                        "charge_kwh": ev.charge_kwh,
                        "objective_cents": ev.objective_cents,
                        "path": ev.path,
                        "best_sites": ""
                        if best is None
                        else ",".join(sorted(best.site_ids)),
                        "all_optimal_site_sets": json.dumps(opt_sets),
                        "n_optimal_sets": len(opt_sets),
                        "greedy_sites": ""
                        if greedy is None
                        else str(greedy.get("sites")),
                        "greedy_coverage": None
                        if greedy is None
                        else greedy.get("coverage_serviceable"),
                        "driving_min": None if sched is None else sched.driving_min,
                        "charging_min": None if sched is None else sched.charging_min,
                        "charge_rest_overlap_min": None
                        if sched is None
                        else sched.charging_rest_overlap_min,
                        "extra_rest_min": None
                        if sched is None
                        else sched.extra_rest_beyond_charge_min,
                        "schedule_ok": None if sched is None else sched.ok,
                        "prep_solve_sec": time.perf_counter() - t0,
                        "git_sha": _git_sha(),
                    }
                )
                print(
                    f"SOC100 q={q} {budget}/{subset_name}: opt_sets={opt_sets}",
                    flush=True,
                )
    return rows


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


def _enrich(
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
        sched = validate_operational_schedule(
            actions, time_step_min=inst.time_step_min
        )
    row.update(
        {
            "discrete_replay_ok": disc_ok,
            "continuous_replay_ok": cont_ok,
            "continuous_replay_reason": cont_reason,
            "audit_ok": audit_ok,
            "audit_reason": audit_reason,
            "charge_kwh_total": None if extras is None else extras.charge_kwh_total,
            "charge_duration_s": None if extras is None else extras.charge_duration_s,
            "min_soc": None if extras is None else extras.min_soc,
            "road_distance_m": None if extras is None else extras.length_m,
            "terminal_soc": (
                None
                if final_E is None
                else float(final_E) / float(vehicle.usable_kwh)
            ),
            "driving_min": None if sched is None else sched.driving_min,
            "charging_min": None if sched is None else sched.charging_min,
            "mandatory_rest_min": None
            if sched is None
            else sched.mandatory_rest_required_min,
            "charge_rest_overlap_min": None
            if sched is None
            else sched.charging_rest_overlap_min,
            "extra_rest_min": None
            if sched is None
            else sched.extra_rest_beyond_charge_min,
            "total_realistic_journey_min": None
            if sched is None
            else sched.total_realistic_journey_min,
            "schedule_ok": None if sched is None else sched.ok,
            "schedule_violation": None if sched is None else sched.violation,
            "n_charge_actions": None if sched is None else sched.n_charge_actions,
        }
    )
    return row


def run_h1_matched_pilots(*, quanta: list[int]) -> list[dict[str, Any]]:
    """Re-test Task07C H1 cases on one canonical graph + allowed_arc_ids."""
    cases = [
        ("casa_marrakech", "eactros_600", "settat_benguerir"),
        ("casa_marrakech", "volvo_475", "settat_benguerir"),
        ("casa_agadir", "volvo_475", "settat_benguerir"),
    ]
    install_map = {
        "none": set(),
        "settat_benguerir": {"settat_ca", "benguerir_ca"},
    }
    rows: list[dict[str, Any]] = []
    for q in quanta:
        for od_id, vkey, iname in cases:
            # also run none for infrastructure contrast
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
                    )
                except Exception as exc:  # noqa: BLE001
                    rows.append(
                        {
                            "experiment": "h1_matched",
                            "od_id": od_id,
                            "vehicle_key": vkey,
                            "q": q,
                            "install_set": install_name,
                            "status": "BUILD_ERROR",
                            "error": str(exc),
                        }
                    )
                    continue
                if not ctx.dem_complete:
                    rows.append(
                        {
                            "experiment": "h1_matched",
                            "od_id": od_id,
                            "vehicle_key": vkey,
                            "q": q,
                            "install_set": install_name,
                            "status": "dem_incomplete",
                        }
                    )
                    continue
                active = set(install_map[install_name]) & set(template.stations)
                short_mask = shortest_path_allowed_arc_ids(ctx, path_rows, od_id)
                all_mask = frozenset(str(a.arc_id) for a in template.arcs if a.arc_id)
                prep_s = time.perf_counter() - t0
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
                    row = {
                        "experiment": "h1_matched",
                        "baseline_id": baseline_id,
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
                        "n_arcs_allowed": len(mask),
                        "graph_rebuild": False,
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
                        "labels_explored": getattr(res, "labels_explored", None),
                        "station_notes": ";".join(notes),
                        "git_sha": _git_sha(),
                        "ccs_cap_kw": vehicle.ccs_max_charge_kw,
                    }
                    row = _enrich(
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
                    # Failure diagnosis for fixed route
                    if baseline_id == "B" and res.status.value != "OPTIMAL":
                        row["fixed_fail_reason"] = "mrls_infeasible_on_shortest_mask"
                    rows.append(row)
                    print(
                        f"H1 {baseline_id}|{vkey}|{od_id}|{install_name}|q{q}: "
                        f"{res.status.value} obj={res.objective} audit={row.get('audit_ok')}",
                        flush=True,
                    )
                # Compare gain
                b_rows = [r for r in rows if r.get("od_id") == od_id and r.get("vehicle_key") == vkey and r.get("q") == q and r.get("install_set") == install_name]
                b = next((r for r in b_rows if r.get("baseline_id") == "B"), None)
                d = next((r for r in b_rows if r.get("baseline_id") == "D"), None)
                if b and d:
                    d["h1_fixed_infeasible"] = b.get("status") != "OPTIMAL"
                    d["h1_multi_feasible"] = d.get("status") == "OPTIMAL"
                    d["h1_route_flexibility_gain"] = bool(
                        b.get("status") != "OPTIMAL" and d.get("status") == "OPTIMAL"
                    )
                    if (
                        b.get("status") == "OPTIMAL"
                        and d.get("status") == "OPTIMAL"
                        and b.get("objective") is not None
                        and d.get("objective") is not None
                    ):
                        d["objective_delta_vs_fixed"] = float(d["objective"]) - float(
                            b["objective"]
                        )
    return rows


def run_northbound_matched(*, q: int = 5) -> list[dict[str, Any]]:
    """Primary Agadir→Casablanca matched A/B/D/E-style comparisons at q."""
    cfg = load_multiroute_placement_config(CFG_PASS2A, root=ROOT)
    rows: list[dict[str, Any]] = []
    orig = _patch_peak_speed_policy(adapt_peak=True, adapt_cont=False)
    try:
        rows = _run_northbound_matched_inner(cfg, q=q)
    finally:
        mpe.load_multiroute_pilot_config = orig
    return rows


def _run_northbound_matched_inner(cfg, *, q: int) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for demand, soc_label in [
        ("A_nb_tomato_p5300_soc08", 0.8),
        ("A_nb_tomato_p5300_soc10", 1.0),
        ("A_nb_tomato_p5300_soc05", 0.5),
    ]:
        t0 = time.perf_counter()
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
        short_mask = shortest_path_allowed_arc_ids(prep.ctx, path_rows, "agadir_casa")
        all_mask = frozenset(str(a.arc_id) for a in prep.template.arcs if a.arc_id)
        installs = {
            "A_none": set(),
            "B_benguerir": {"y_benguerir_ac"},
            "B_settat": {"y_settat_ac"},
            "Ball_both": {s.id for s in cfg.sites},
        }
        # Map placement site ids → station keys on graph
        key_of = {s.id: s.station_key for s in cfg.sites}
        for iname, site_ids in installs.items():
            active_keys = {key_of[i] for i in site_ids if i in key_of}
            for baseline_id, method, mask, mask_name in [
                ("A", "mrls_fixed_shortest_no_or_fixed_sites", short_mask, "shortest"),
                ("D", "mrls_multi_route_same_sites", all_mask, "all"),
            ]:
                # Restrict active stations to those present on graph
                present = set(active_keys) & set(prep.template.stations)
                inst = clone_physics_instance_for_subset(
                    prep.template,
                    active_stations=present,
                    allowed_arc_ids=mask,
                    name=f"NB|{demand}|{iname}|{baseline_id}",
                )
                t1 = time.perf_counter()
                res = solve_mrls(inst, max_seconds=90.0, max_expansions=800_000)
                row = {
                    "experiment": "northbound_matched",
                    "baseline_id": baseline_id,
                    "method": method,
                    "mission_id": "M_agadir_casa",
                    "od_id": "agadir_casa",
                    "direction": "northbound",
                    "vehicle_key": "eactros_600",
                    "payload_kg": PAYLOAD,
                    "soc_frac": soc_label,
                    "demand": demand,
                    "q": q,
                    "install_set": iname,
                    "installed_site_ids": ",".join(sorted(site_ids)),
                    "active_stations": ",".join(sorted(present)),
                    "route_mask": mask_name,
                    "n_arcs_physical": len(prep.template.arcs),
                    "n_arcs_allowed": len(mask),
                    "status": res.status.value,
                    "objective": res.objective,
                    "final_E_truck": (
                        res.final_label.E_truck if res.final_label else None
                    ),
                    "final_t_steps": res.final_label.t if res.final_label else None,
                    "prep_sec": time.perf_counter() - t0,
                    "solve_sec": time.perf_counter() - t1,
                    "git_sha": _git_sha(),
                    "ccs_cap_kw": prep.ctx.vehicle.ccs_max_charge_kw,
                }
                row = _enrich(
                    row=row,
                    inst=inst,
                    ctx=prep.ctx,
                    vehicle=prep.ctx.vehicle,
                    actions=res.actions or [],
                    objective=res.objective,
                    final_E=row["final_E_truck"],
                    final_t=row["final_t_steps"],
                    status=res.status.value,
                )
                rows.append(row)
                print(
                    f"NB {baseline_id}|{demand}|{iname}: {res.status.value}",
                    flush=True,
                )
        # E — joint enum under Ball
        enum_rows, best, _ = run_multiroute_enumeration(
            cfg,
            root=ROOT,
            demand_name=demand,
            capex_name="equal",
            budget_name="Ball",
            context=context,
        )
        opt_sets = all_optimal_site_sets(enum_rows)
        rows.append(
            {
                "experiment": "northbound_matched",
                "baseline_id": "E",
                "method": "joint_enum_bb_style_enumeration",
                "mission_id": "M_agadir_casa",
                "od_id": "agadir_casa",
                "direction": "northbound",
                "vehicle_key": "eactros_600",
                "payload_kg": PAYLOAD,
                "soc_frac": soc_label,
                "demand": demand,
                "q": q,
                "install_set": "optimized_Ball",
                "best_sites": "" if best is None else ",".join(sorted(best.site_ids)),
                "all_optimal_site_sets": json.dumps(opt_sets),
                "n_optimal_sets": len(opt_sets),
                "coverage": None if best is None else best.coverage_serviceable,
                "status": "OPTIMAL" if best is not None else "NO_FEASIBLE",
                "git_sha": _git_sha(),
            }
        )
        # greedy B1
        enum_b1, best_b1, _ = run_multiroute_enumeration(
            cfg,
            root=ROOT,
            demand_name=demand,
            capex_name="equal",
            budget_name="B1",
            context=context,
        )
        feas = [r for r in enum_b1 if r.get("budget_ok") and r.get("certified")]
        greedy = None
        if feas:
            greedy = sorted(
                feas,
                key=lambda r: (
                    -float(r.get("coverage_serviceable") or 0),
                    float(r.get("secondary_cost") or 1e18),
                ),
            )[0]
        rows.append(
            {
                "experiment": "northbound_matched",
                "baseline_id": "GreedyB1",
                "method": "greedy_max_coverage_min_cost_B1",
                "demand": demand,
                "q": q,
                "best_sites": "" if best_b1 is None else ",".join(sorted(best_b1.site_ids)),
                "greedy_sites": None if greedy is None else greedy.get("sites"),
                "enum_agrees_greedy": (
                    None
                    if greedy is None or best_b1 is None
                    else str(greedy.get("sites") or "")
                    == (",".join(sorted(best_b1.site_ids)) or "NONE")
                ),
                "all_optimal_site_sets": json.dumps(all_optimal_site_sets(enum_b1)),
                "git_sha": _git_sha(),
            }
        )
    return rows


def make_figure(baseline_rows: list[dict[str, Any]]) -> None:
    try:
        import matplotlib.pyplot as plt
    except ImportError:
        print("matplotlib unavailable; skip figure", flush=True)
        return
    h1 = [
        r
        for r in baseline_rows
        if r.get("experiment") == "h1_matched" and r.get("baseline_id") in ("B", "D")
    ]
    if not h1:
        return
    # Pivot feasibility by case
    keys = []
    for r in h1:
        keys.append(
            (r.get("od_id"), r.get("vehicle_key"), r.get("install_set"), r.get("q"))
        )
    keys = sorted(set(keys))
    labels = []
    fixed_ok = []
    multi_ok = []
    for od, v, inst, q in keys:
        if inst == "none":
            continue
        labels.append(f"{od}\n{v}\nq={q}")
        b = next(
            (
                r
                for r in h1
                if r.get("od_id") == od
                and r.get("vehicle_key") == v
                and r.get("install_set") == inst
                and r.get("q") == q
                and r.get("baseline_id") == "B"
            ),
            None,
        )
        d = next(
            (
                r
                for r in h1
                if r.get("od_id") == od
                and r.get("vehicle_key") == v
                and r.get("install_set") == inst
                and r.get("q") == q
                and r.get("baseline_id") == "D"
            ),
            None,
        )
        fixed_ok.append(1 if b and b.get("status") == "OPTIMAL" else 0)
        multi_ok.append(1 if d and d.get("status") == "OPTIMAL" else 0)
    if not labels:
        return
    OUT_FIG.parent.mkdir(parents=True, exist_ok=True)
    x = range(len(labels))
    w = 0.35
    fig, ax = plt.subplots(figsize=(10, 4.5))
    ax.bar([i - w / 2 for i in x], fixed_ok, w, label="Fixed shortest (B)", color="#4C78A8")
    ax.bar([i + w / 2 for i in x], multi_ok, w, label="Multi-route MRLS (D)", color="#F58518")
    ax.set_xticks(list(x))
    ax.set_xticklabels(labels, fontsize=8)
    ax.set_ylim(0, 1.25)
    ax.set_yticks([0, 1])
    ax.set_yticklabels(["infeasible", "feasible"])
    ax.set_ylabel("Mission feasibility")
    ax.set_title("H1 pilot: fixed vs multi-route under identical graph / chargers / q")
    ax.legend(loc="upper right")
    fig.tight_layout()
    fig.savefig(OUT_FIG, dpi=150)
    plt.close(fig)
    print(f"Wrote {OUT_FIG}", flush=True)


def write_report(
    *,
    site_rows: list[dict],
    baseline_rows: list[dict],
    soc_rows: list[dict],
    test_summary: str,
) -> None:
    sha = _git_sha()
    h1 = [r for r in baseline_rows if r.get("experiment") == "h1_matched"]
    gains = [
        r
        for r in h1
        if r.get("baseline_id") == "D" and r.get("h1_route_flexibility_gain")
    ]
    nb = [r for r in baseline_rows if r.get("experiment") == "northbound_matched"]
    marrakech = [
        s
        for s in site_rows
        if s.get("name_token") == "marrakech"
        and "Agadir" in str(s.get("adm_direction"))
    ]
    oum = [
        s
        for s in site_rows
        if s.get("name_token") == "oum rbii"
        and "Agadir" in str(s.get("adm_direction"))
    ]

    def _grade(tag: str, text: str) -> str:
        return f"- **{tag}**: {text}\n"

    lines = []
    lines.append("# PAPER_RESULTS_SPRINT_01\n")
    lines.append(
        f"Git SHA: `{sha}`  \n"
        f"Date: 2026-11-15  \n"
        f"Scope: integrity corrections + matched H1 pilots + ADM candidate evidence + "
        f"operational schedule screen. **Not** a publication-ready freeze.\n"
    )
    lines.append("\n## Authoritative vs superseded\n")
    lines.append(
        "- Authoritative prior freeze: `reports/FINAL_RESEARCH_FREEZE.md`, "
        "`final_numerical_integrity.md`, `final_moroccan_robustness_results.md`, "
        "`task07c_*`, `results/final_action_rounding_audit.csv`.\n"
        "- This sprint **adds** `paper_results_*` artifacts; it does not overwrite freeze CSVs.\n"
        "- Historical Task07C H1 at q=10 remains archival; new H1 pilots re-test at q=5(+2) "
        "on the same physical graph with `allowed_arc_ids`.\n"
        "- `drive_path_floor_loss` remains SUPERSEDED by `audit_solved_actions_exact`.\n"
    )
    lines.append("\n## Integrity corrections\n")
    lines.append(
        "1. Explicit demand `A_nb_tomato_p5300_soc10` (SOC=1.0) in "
        "`multiroute_placement_pass2a.yaml`; robustness no longer uses `force_soc` "
        "on an 80% demand (q=2 refine now uses the same SOC100 demand).\n"
        "2. `audit_solved_actions_exact`: continuous DRIVE sim failure or "
        "`table_vs_floor_gap` beyond tolerance → `audit_ok=False`.\n"
        "3. eActros CCS acceptance cap set to **400 kW** "
        "(Mercedes public page); effective power = min(charger, 400). "
        "No OEM SOC-dependent curve — constant envelope stated explicitly.\n"
    )
    lines.append("\n## Site candidates (H5)\n")
    lines.append(
        f"ADM directory lists Marrakech and Oum Rbii (Agadir→Casablanca). "
        f"Current OSM match: Marrakech acceptance=`{marrakech[0]['candidate_acceptance'] if marrakech else 'n/a'}`; "
        f"Oum Rbii=`{oum[0]['candidate_acceptance'] if oum else 'n/a'}`. "
        "**Not enabled** — no fabricated connectors / proximity snaps. "
        f"See `{OUT_SITES.name}`.\n"
    )
    lines.append("\n## H1 matched pilots (fixed vs multi-route)\n")
    if gains:
        lines.append(
            f"Convincing feasibility gains (fixed INFEASIBLE, multi OPTIMAL) in "
            f"**{len(gains)}** case(s):\n"
        )
        for r in gains:
            lines.append(
                f"- {r.get('od_id')} / {r.get('vehicle_key')} / "
                f"install={r.get('install_set')} / q={r.get('q')}: "
                f"multi obj={r.get('objective')}, audit_ok={r.get('audit_ok')}, "
                f"cont_ok={r.get('continuous_replay_ok')}, "
                f"road_m={r.get('road_distance_m')}, min_soc={r.get('min_soc')}\n"
            )
    else:
        lines.append(
            "No confirmed fixed→multi feasibility gain in this sprint's q grid. "
            "See CSV for per-case status (may be both feasible, both infeasible, "
            "or sensitive to q).\n"
        )
    # compact table
    lines.append("\n| OD | Truck | Install | q | Fixed | Multi | Gain |\n|---|---|---|---:|---|---|---|\n")
    seen = set()
    for r in h1:
        if r.get("baseline_id") != "D":
            continue
        key = (r.get("od_id"), r.get("vehicle_key"), r.get("install_set"), r.get("q"))
        if key in seen:
            continue
        seen.add(key)
        b = next(
            (
                x
                for x in h1
                if x.get("baseline_id") == "B"
                and x.get("od_id") == r.get("od_id")
                and x.get("vehicle_key") == r.get("vehicle_key")
                and x.get("install_set") == r.get("install_set")
                and x.get("q") == r.get("q")
            ),
            None,
        )
        lines.append(
            f"| {r.get('od_id')} | {r.get('vehicle_key')} | {r.get('install_set')} | "
            f"{r.get('q')} | {b.get('status') if b else '?'} | {r.get('status')} | "
            f"{r.get('h1_route_flexibility_gain')} |\n"
        )

    lines.append("\n## Northbound SOC100 placement (all optimal sets)\n")
    for r in soc_rows:
        if r.get("subset_eval") != "both":
            continue
        lines.append(
            f"- q={r.get('q')} budget={r.get('budget')}: served={r.get('served')} "
            f"opt_sets={r.get('all_optimal_site_sets')} "
            f"E_init={r.get('E_truck_init')} (soc={r.get('soc_frac')})\n"
        )

    lines.append("\n## Operational schedule (H3)\n")
    sched_rows = [r for r in baseline_rows if r.get("schedule_ok") is not None]
    n_ok = sum(1 for r in sched_rows if r.get("schedule_ok"))
    n_overlap = sum(
        1
        for r in sched_rows
        if (r.get("charge_rest_overlap_min") or 0) >= 45 - 1e-9
    )
    lines.append(
        f"Validated {len(sched_rows)} solved plans: schedule_ok={n_ok}; "
        f"plans with ≥45 min charge/rest overlap={n_overlap}. "
        "Validator only — no HOS re-optimization.\n"
    )

    lines.append("\n## Hypotheses H1–H5\n")
    lines.append(
        _grade(
            "H1",
            (
                f"CONFIRMED in this sprint for {len(gains)} case(s)"
                if gains
                else "UNCERTAIN / not reproduced at screened q — see pilots CSV"
            ),
        )
    )
    # H2 from northbound greedy vs enum
    greedy_rows = [r for r in nb if r.get("baseline_id") == "GreedyB1"]
    agree = [r for r in greedy_rows if r.get("enum_agrees_greedy") is True]
    lines.append(
        _grade(
            "H2",
            f"On 2-site northbound universe, enum vs greedy B1 agreement "
            f"{len(agree)}/{len(greedy_rows)} demands — limited candidate set; "
            "not a strong nationwide siting claim.",
        )
    )
    lines.append(
        _grade(
            "H3",
            f"PARTIAL: {n_overlap}/{len(sched_rows)} solved plans have charge≥45 min "
            "overlap with a qualifying break window; many short missions need no break.",
        )
    )
    lines.append(
        _grade(
            "H4",
            "See SOC/reserve and SOC100 placement rows — report min_soc margins in CSV; "
            "do not claim without paired sensitivity.",
        )
    )
    lines.append(
        _grade(
            "H5",
            "FAILED for enabling Marrakech/Oum Rbii now: official ADM names exist, "
            "but OSM geometry unmatched → not added (no fabricated access).",
        )
    )

    lines.append("\n## Reproduction\n")
    lines.append("```bash\n")
    lines.append("python -m pytest tests/unit/test_action_rounding_and_min_soc.py "
                 "tests/unit/test_operational_schedule.py "
                 "tests/unit/test_soc100_demand_scenario.py -q\n")
    lines.append("python scripts/run_paper_results_sprint_01.py --phase all\n")
    lines.append("```\n")
    lines.append(f"\n## Tests\n\n{test_summary}\n")
    lines.append("\n## Artifacts\n")
    for p in (OUT_BASELINES, OUT_SITES, OUT_SCHED, OUT_SOC100, OUT_FIG):
        lines.append(f"- `{p.relative_to(ROOT)}`\n")
    lines.append(
        "\n## Smallest next experiment\n"
        "- If H1 gains appear only at coarse q: re-run positive cells at q=2 (then q=1 "
        "only if still sensitive) with full audit.\n"
        "- Manual OSM POI resolution for Marrakech/Oum Rbii before any H5 enablement.\n"
        "- Reserve-SOC policy sweep (10/15/20%) on northbound Benguerir-optimal cell.\n"
    )
    OUT_MD.write_text("".join(lines), encoding="utf-8")
    print(f"Wrote {OUT_MD}", flush=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--phase",
        choices=["sites", "soc100", "h1", "northbound", "all"],
        default="all",
    )
    ap.add_argument("--h1-q", default="5", help="comma list, e.g. 5 or 5,2")
    ap.add_argument("--soc-q", default="5,2", help="comma list for SOC100 enum")
    args = ap.parse_args()
    h1_q = [int(x) for x in str(args.h1_q).split(",") if x.strip()]
    soc_q = [int(x) for x in str(args.soc_q).split(",") if x.strip()]

    site_rows: list[dict] = []
    baseline_rows: list[dict] = []
    soc_rows: list[dict] = []

    if args.phase in ("sites", "all"):
        site_rows = write_site_candidates()

    if args.phase in ("soc100", "all"):
        soc_rows = run_soc100_placement(quanta=soc_q)

    if args.phase in ("h1", "all"):
        baseline_rows.extend(run_h1_matched_pilots(quanta=h1_q))

    if args.phase in ("northbound", "all"):
        # Cost gate: q=5 only in this sprint for northbound matrix
        baseline_rows.extend(run_northbound_matched(q=5))

    if baseline_rows:
        OUT_BASELINES.parent.mkdir(parents=True, exist_ok=True)
        new_df = pd.DataFrame(baseline_rows)
        if OUT_BASELINES.exists():
            old = pd.read_csv(OUT_BASELINES)
            # Replace only experiments present in this run; keep others.
            exps = set(new_df.get("experiment", pd.Series(dtype=str)).dropna().unique())
            if "experiment" in old.columns and exps:
                # For h1, also replace only the q values just computed.
                if exps == {"h1_matched"} and "q" in new_df.columns:
                    qs = set(new_df["q"].dropna().unique())
                    keep = old[
                        ~(
                            (old.get("experiment") == "h1_matched")
                            & (old.get("q").isin(qs))
                        )
                    ]
                else:
                    keep = old[~old["experiment"].isin(exps)]
                merged = pd.concat([keep, new_df], ignore_index=True)
            else:
                merged = pd.concat([old, new_df], ignore_index=True)
        else:
            merged = new_df
        merged.to_csv(OUT_BASELINES, index=False)
        print(f"Wrote {OUT_BASELINES} ({len(merged)} rows)", flush=True)
        baseline_rows = merged.to_dict(orient="records")
        # schedule extract
        sched = []
        for r in baseline_rows:
            if r.get("schedule_ok") is None and r.get("driving_min") is None:
                continue
            # pandas may store bools; treat NaN schedule as skip already done
            if pd.isna(r.get("driving_min")) and pd.isna(r.get("schedule_ok")):
                continue
            sched.append(
                {
                    k: r.get(k)
                    for k in (
                        "experiment",
                        "baseline_id",
                        "od_id",
                        "vehicle_key",
                        "demand",
                        "q",
                        "install_set",
                        "status",
                        "driving_min",
                        "charging_min",
                        "mandatory_rest_min",
                        "charge_rest_overlap_min",
                        "extra_rest_min",
                        "total_realistic_journey_min",
                        "schedule_ok",
                        "schedule_violation",
                        "n_charge_actions",
                        "min_soc",
                        "road_distance_m",
                        "git_sha",
                    )
                }
            )
        pd.DataFrame(sched).to_csv(OUT_SCHED, index=False)
        print(f"Wrote {OUT_SCHED} ({len(sched)} rows)", flush=True)
        make_figure(baseline_rows)

    if args.phase == "all":
        # run unit tests summary
        try:
            out = subprocess.check_output(
                [
                    sys.executable,
                    "-m",
                    "pytest",
                    "tests/unit/test_action_rounding_and_min_soc.py",
                    "tests/unit/test_operational_schedule.py",
                    "tests/unit/test_soc100_demand_scenario.py",
                    "-q",
                    "--tb=no",
                ],
                cwd=ROOT,
                text=True,
                stderr=subprocess.STDOUT,
            )
            test_summary = out.strip()
        except subprocess.CalledProcessError as exc:
            test_summary = (exc.output or str(exc)).strip()
        if not site_rows and OUT_SITES.exists():
            site_rows = pd.read_csv(OUT_SITES).to_dict(orient="records")
        if not soc_rows and OUT_SOC100.exists():
            soc_rows = pd.read_csv(OUT_SOC100).to_dict(orient="records")
        write_report(
            site_rows=site_rows,
            baseline_rows=baseline_rows,
            soc_rows=soc_rows,
            test_summary=test_summary,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
