#!/usr/bin/env python
"""Stage A+B — action-exact rounding audit, microsegment min SOC, charge-energy explanation.

Reuses committed q=1 placement conclusions (sites) and only re-solves MRLS for audits.
Marks superseded path-node rounding losses from the prior CSV.
"""

from __future__ import annotations

import csv
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import morocco_etruck.optimization.multiroute_placement_evaluation as mpe  # noqa: E402
from morocco_etruck.optimization.arc_preprocessing import simulate_drive_from_soc  # noqa: E402
from morocco_etruck.optimization.label_setting import SolverStatus, solve_mrls  # noqa: E402
from morocco_etruck.optimization.multiroute_adapter import (  # noqa: E402
    clone_physics_instance_for_subset,
    load_multiroute_pilot_config,
)
from morocco_etruck.optimization.multiroute_placement import (  # noqa: E402
    load_multiroute_placement_config,
)
from morocco_etruck.optimization.multiroute_placement_evaluation import (  # noqa: E402
    active_keys_for_installed,
    prepare_multiroute_placement_context,
)
from morocco_etruck.optimization.multiroute_replay import (  # noqa: E402
    continuous_replay_multiroute,
    summarize_complete_trace,
)
from morocco_etruck.optimization.quantization_audit import (  # noqa: E402
    audit_solved_actions_exact,
)

CFG = ROOT / "configs/optimization/multiroute_placement_pass2a.yaml"
FRIDGE = ROOT / "configs/energy/pass2_tomato_firm_ripe.yaml"
VPATH = ROOT / "configs/vehicles/eactros_600.yaml"
HIST_CSV = ROOT / "results/moroccan_energy_grid_convergence.csv"
OUT_AUDIT = ROOT / "results/final_action_rounding_audit.csv"
OUT_TRACE = ROOT / "results/final_physical_trace_metrics.csv"
OUT_MD = ROOT / "reports/final_numerical_integrity.md"
OUT_CHG = ROOT / "reports/charging_energy_convergence_explanation.md"


def _patch(sp):
    orig = mpe.load_multiroute_pilot_config

    def wrapped(path, *, root):
        c = orig(path, root=root)
        c.speed_policy = dict(sp)
        return c

    mpe.load_multiroute_pilot_config = wrapped
    return orig


def _sites_for_q(q: int, hist: list[dict]) -> set[str]:
    for r in hist:
        if str(r.get("panel", "")).startswith("northbound") and int(r.get("q") or -1) == q:
            if str(r.get("ball_status")) == "OPTIMAL" and r.get("best_sites"):
                return set(str(r["best_sites"]).split(","))
            if str(r.get("ball_status")) == "OPTIMAL":
                return set()
    # fallback: all config sites
    return set()


def _run_q(q: int, installed: set[str], cfg, sp) -> dict:
    orig = _patch(sp)
    try:
        context = prepare_multiroute_placement_context(
            cfg,
            root=ROOT,
            demand_name="A_nb_tomato_p5300_soc08",
            energy_quantum_kwh=q,
            objective_mode="enroute_incremental_cost",
            vehicle_yaml=VPATH,
            road_cost_per_km=100.0,
            fridge_yaml=FRIDGE,
            charger_power_kw=350.0,
            max_alternatives_for_union=4,
        )
        prep = next(iter(context["prepared"].values()))
        if not installed:
            # Ball empty optimum (southbound-style); northbound expects Benguerir
            installed = {s.id for s in cfg.sites}
        active = active_keys_for_installed(cfg.sites, installed, prep.template)
        inst = clone_physics_instance_for_subset(prep.template, active_stations=active)
        sol = solve_mrls(
            inst,
            max_seconds=cfg.solver_max_seconds,
            max_expansions=cfg.solver_max_expansions,
        )
        row: dict = {
            "q": q,
            "installed": ",".join(sorted(installed)),
            "status": sol.status.value,
            "objective_cents": sol.objective,
            "n_actions": len(sol.actions or []),
            "n_drive_actions": sum(1 for a in (sol.actions or []) if a.get("type") == "DRIVE"),
            "n_charge_actions": sum(1 for a in (sol.actions or []) if a.get("type") == "CHARGE"),
            "path": "->".join(sol.path_nodes or []),
            "mrls_labels_generated": (sol.stats or {}).get("labels_generated"),
            "mrls_labels_expanded": (sol.stats or {}).get("labels_expanded"),
        }
        if sol.status != SolverStatus.OPTIMAL:
            row["audit_ok"] = False
            return row
        final_E = None if sol.final_label is None else int(sol.final_label.E_truck)
        audit = audit_solved_actions_exact(
            inst,
            sol.actions or [],
            prep_ctx=prep.ctx,
            simulate_drive_fn=simulate_drive_from_soc,
            expected_final_E_disc=final_E,
        )
        crep, ex = continuous_replay_multiroute(
            prep.ctx, inst, sol.actions or [], emit_trace=True
        )
        summary = summarize_complete_trace(ex)
        charge_kwh = sum(float(a.get("delta_e_kwh") or 0) for a in (sol.actions or []) if a.get("type") == "CHARGE")
        charge_nodes = [
            str(a.get("node"))
            for a in (sol.actions or [])
            if a.get("type") == "CHARGE"
        ]
        osm_edges = []
        for a in sol.actions or []:
            if a.get("type") == "DRIVE":
                osm_edges.append(str(a.get("arc_id")))
        row.update(
            {
                "audit_ok": audit.ok,
                "audit_failure": audit.failure_reason,
                "audit_n_drive": audit.n_drive,
                "audit_n_charge": audit.n_charge,
                "audit_n_wait": audit.n_wait,
                "audit_floor_loss_kwh": audit.cumulative_floor_loss_kwh,
                "audit_cap_trunc_kwh": audit.cumulative_cap_truncation_kwh,
                "audit_zero_net_charges": audit.n_zero_net_charge,
                "audit_E_final_disc": audit.E_final_disc,
                "label_E_final_disc": final_E,
                "disc_charge_kwh": charge_kwh,
                "charge_nodes": ",".join(charge_nodes),
                "cont_ok": crep.ok,
                "trace_status": summary.get("trace_status"),
                "auth_length_m": summary.get("length_m"),
                "auth_min_soc": summary.get("min_soc"),
                "auth_min_soc_action": summary.get("min_soc_action"),
                "auth_min_soc_distance_m": summary.get("min_soc_distance_m"),
                "auth_arrival_soc": summary.get("arrival_soc"),
                "auth_charge_kwh": summary.get("charge_kwh_total"),
                "auth_drive_duration_s": summary.get("drive_duration_s"),
                "auth_charge_duration_s": summary.get("charge_duration_s"),
                "E_traction_kwh": summary.get("E_traction_kwh"),
                "E_aux_drive_kwh": summary.get("E_aux_drive_kwh"),
                "E_refrig_drive_kwh": summary.get("E_refrig_drive_kwh"),
                "E_regen_credit_kwh": summary.get("E_regen_credit_kwh"),
                "n_microsegments": summary.get("n_microsegments"),
                "drive_arc_ids": "|".join(osm_edges),
                "hist_superseded_drive_floor_loss_note": (
                    "prior CSV cum_drive_rounding_loss_kwh from drive_path_floor_loss is SUPERSEDED"
                ),
            }
        )
        print(
            f"q={q}: status={sol.status.value} charge={charge_kwh} "
            f"audit_ok={audit.ok} floor_loss={audit.cumulative_floor_loss_kwh:.3f} "
            f"n_drive={audit.n_drive} min_soc={summary.get('min_soc')}",
            flush=True,
        )
        return row
    finally:
        mpe.load_multiroute_pilot_config = orig


def main() -> int:
    hist = []
    if HIST_CSV.exists():
        with HIST_CSV.open(encoding="utf-8") as f:
            hist = list(csv.DictReader(f))
    base = load_multiroute_pilot_config(
        ROOT / "configs/optimization/multiroute_pilot.yaml", root=ROOT
    )
    sp = dict(base.speed_policy)
    sp["adapt_speed_to_peak_power"] = True
    sp["adapt_speed_to_continuous_power"] = False
    sp["min_adapt_speed_mps"] = 1.0 / 3.6
    cfg = load_multiroute_placement_config(CFG, root=ROOT)

    rows = []
    for q in (5, 2, 1):
        sites = _sites_for_q(q, hist)
        if not sites:
            sites = {"y_benguerir_ac"}  # committed Ball optimum for served qs
        rows.append(_run_q(q, sites, cfg, sp))

    OUT_AUDIT.parent.mkdir(parents=True, exist_ok=True)
    keys = []
    seen = set()
    for r in rows:
        for k in r:
            if k not in seen:
                seen.add(k)
                keys.append(k)
    with OUT_AUDIT.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=keys, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow(r)
    # Trace metrics subset
    tkeys = [
        "q",
        "status",
        "auth_length_m",
        "auth_min_soc",
        "auth_min_soc_action",
        "auth_min_soc_distance_m",
        "auth_arrival_soc",
        "auth_charge_kwh",
        "auth_drive_duration_s",
        "auth_charge_duration_s",
        "E_traction_kwh",
        "E_aux_drive_kwh",
        "E_refrig_drive_kwh",
        "E_regen_credit_kwh",
        "n_microsegments",
        "cont_ok",
        "trace_status",
    ]
    with OUT_TRACE.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=tkeys, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k) for k in tkeys})

    # Explain charge energy differences
    by_q = {int(r["q"]): r for r in rows if r.get("status") == "OPTIMAL"}
    same_arcs = None
    if 5 in by_q and 1 in by_q:
        same_arcs = by_q[5].get("drive_arc_ids") == by_q[1].get("drive_arc_ids")
    lines = [
        "# Final numerical integrity",
        "",
        "## A1. Action-exact rounding audit",
        "",
        "`drive_path_floor_loss` (path-node walk) is **SUPERSEDED**. "
        "Authoritative audit: `audit_solved_actions_exact` on the exact ordered "
        "DRIVE/CHARGE/WAIT list with exact `arc_id` resolution.",
        "",
        "| q | OPTIMAL | DRIVE actions | Floor loss kWh | Cap trunc | Zero-net charges | Audit OK |",
        "| --- | --- | ---: | ---: | ---: | ---: | --- |",
    ]
    for r in rows:
        lines.append(
            f"| {r.get('q')} | {r.get('status')} | {r.get('audit_n_drive')} | "
            f"{r.get('audit_floor_loss_kwh')} | {r.get('audit_cap_trunc_kwh')} | "
            f"{r.get('audit_zero_net_charges')} | {r.get('audit_ok')} |"
        )
    lines.extend(
        [
            "",
            "## A2. Microsegment minimum SOC",
            "",
            "Published `auth_min_soc` is the minimum over every DRIVE microsegment, "
            "CHARGE and WAIT endpoints (not macro ends alone).",
            "",
            "| q | Min SOC | At action | Distance m | Arrival SOC |",
            "| --- | ---: | --- | ---: | ---: |",
        ]
    )
    for r in rows:
        lines.append(
            f"| {r.get('q')} | {r.get('auth_min_soc')} | {r.get('auth_min_soc_action')} | "
            f"{r.get('auth_min_soc_distance_m')} | {r.get('auth_arrival_soc')} |"
        )
    lines.extend(
        [
            "",
            "## Reproduction",
            "",
            "```bash",
            "python scripts/run_final_numerical_integrity.py",
            "pytest -q tests/unit/test_action_rounding_and_min_soc.py",
            "```",
            "",
            f"Vehicle sha16={hashlib.sha256(VPATH.read_bytes()).hexdigest()[:16]}",
            "",
        ]
    )
    OUT_MD.write_text("\n".join(lines), encoding="utf-8")

    chg = [
        "# Charging-energy convergence explanation",
        "",
        "Committed Ball site identity for served grids remains Benguerir, but discrete "
        "charging energy is **not** stable across q.",
        "",
        "| q | Discrete charge kWh | Continuous charge kWh | Floor loss kWh | Objective | Same DRIVE arc sequence as q=5? |",
        "| --- | ---: | ---: | ---: | ---: | --- |",
    ]
    ref_arcs = by_q.get(5, {}).get("drive_arc_ids")
    for q in (5, 2, 1):
        r = by_q.get(q, {})
        same = None if not r else (r.get("drive_arc_ids") == ref_arcs)
        chg.append(
            f"| {q} | {r.get('disc_charge_kwh')} | {r.get('auth_charge_kwh')} | "
            f"{r.get('audit_floor_loss_kwh')} | {r.get('objective_cents')} | {same} |"
        )
    # Classification
    classes = []
    if same_arcs is True:
        classes.append(
            "**Primary classification: C (different discretized charge choices)** "
            "and **B (conservative numerical flooring)**, on the same physical arc sequence."
        )
    elif same_arcs is False:
        classes.append(
            "**Primary classification includes A (route-choice differences)**; "
            "also quantify B/C on shared arcs where present."
        )
    else:
        classes.append("Insufficient OPTIMAL rows to classify.")
    # Floor loss cannot alone explain 175→94 if losses are smaller than delta
    if 5 in by_q and 1 in by_q:
        d_chg = float(by_q[5].get("disc_charge_kwh") or 0) - float(
            by_q[1].get("disc_charge_kwh") or 0
        )
        d_loss = float(by_q[5].get("audit_floor_loss_kwh") or 0) - float(
            by_q[1].get("audit_floor_loss_kwh") or 0
        )
        classes.append(
            f"Charge energy drop q5−q1 = {d_chg:.1f} kWh; floor-loss drop = {d_loss:.1f} kWh. "
            "Do **not** attribute the entire charge difference to flooring unless "
            "d_loss accounts for d_chg (it generally does not)."
        )
    chg.extend(
        [
            "",
            "## Interpretation",
            "",
            *classes,
            "",
            "Site-selection stability ≠ charging-energy / cost convergence.",
            "",
            f"CSV: `{OUT_AUDIT.relative_to(ROOT).as_posix()}`",
            "",
        ]
    )
    OUT_CHG.write_text("\n".join(chg), encoding="utf-8")
    print(f"Wrote {OUT_AUDIT}")
    print(f"Wrote {OUT_TRACE}")
    print(f"Wrote {OUT_MD}")
    print(f"Wrote {OUT_CHG}")
    return 0 if all(r.get("audit_ok") or r.get("status") != "OPTIMAL" for r in rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
