#!/usr/bin/env python
"""P0.1 — Reconcile publication journey metrics with full continuous replay."""

from __future__ import annotations

import csv
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import morocco_etruck.optimization.multiroute_placement_evaluation as mpe  # noqa: E402
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
from morocco_etruck.optimization.replay import replay_solution  # noqa: E402

CFG = ROOT / "configs/optimization/multiroute_placement_pass2a.yaml"
FRIDGE = ROOT / "configs/energy/pass2_tomato_firm_ripe.yaml"
VPATH = ROOT / "configs/vehicles/eactros_600.yaml"
OUT_CSV = ROOT / "results/physical_trace_reconciliation.csv"
OUT_MD = ROOT / "reports/physical_replay_trace_integrity.md"
TOL_M = 1.0
TOL_SOC = 1e-6


def _patch_peak(sp):
    orig = mpe.load_multiroute_pilot_config

    def wrapped(path, *, root):
        c = orig(path, root=root)
        c.speed_policy = dict(sp)
        return c

    mpe.load_multiroute_pilot_config = wrapped
    return orig


def main() -> int:
    base = load_multiroute_pilot_config(
        ROOT / "configs/optimization/multiroute_pilot.yaml", root=ROOT
    )
    sp = dict(base.speed_policy)
    sp["adapt_speed_to_peak_power"] = True
    sp["adapt_speed_to_continuous_power"] = False
    sp["min_adapt_speed_mps"] = 1.0 / 3.6
    orig = _patch_peak(sp)
    rows = []
    try:
        cfg = load_multiroute_placement_config(CFG, root=ROOT)
        # Rebuild-2 graph (historically published OPTIMAL at q=10) + canonical-4 at q=5
        cases = [
            ("rebuild_max_alts2_q10", 2, 10),
            ("canonical_max_alts4_q5", 4, 5),
        ]
        for tag, max_alts, q in cases:
            ctx = prepare_multiroute_placement_context(
                cfg,
                root=ROOT,
                demand_name="A_nb_tomato_p5300_soc08",
                energy_quantum_kwh=q,
                objective_mode="enroute_incremental_cost",
                vehicle_yaml=VPATH,
                road_cost_per_km=100.0,
                fridge_yaml=FRIDGE,
                charger_power_kw=350.0,
                max_alternatives_for_union=max_alts,
            )
            prep = next(iter(ctx["prepared"].values()))
            installed = {s.id for s in cfg.sites}
            active = active_keys_for_installed(cfg.sites, installed, prep.template)
            inst = clone_physics_instance_for_subset(prep.template, active_stations=active)
            sol = solve_mrls(inst, max_seconds=120.0, max_expansions=500_000)
            row = {
                "case": tag,
                "max_alts": max_alts,
                "q": q,
                "status": sol.status.value,
                "vehicle_sha16": hashlib.sha256(VPATH.read_bytes()).hexdigest()[:16],
                "fridge_sha16": hashlib.sha256(FRIDGE.read_bytes()).hexdigest()[:16],
            }
            if sol.status != SolverStatus.OPTIMAL:
                row["trace_status"] = "NO_SOLUTION"
                rows.append(row)
                continue
            disc = replay_solution(inst, sol.actions)
            crep, ex = continuous_replay_multiroute(
                prep.ctx, inst, sol.actions, emit_trace=True
            )
            summary = summarize_complete_trace(ex)
            # Historical defective profile (commit-era integrity JSON): DRIVE micros
            # without CHARGE state updates; early stop → ~353.6 km vs journey ~429.2 km.
            hist_path = ROOT / "results/northbound_route_expansion_summary.json"
            hist_defective_m = None
            hist_journey_m = None
            if hist_path.exists() and tag.startswith("rebuild"):
                hist = json.loads(hist_path.read_text(encoding="utf-8"))
                prof = hist.get("profile_rebuild2_q10") or {}
                hist_defective_m = prof.get("drive_length_m")
                hist_journey_m = prof.get("journey_length_m")
            auth_m = float(summary.get("length_m") or 0.0)
            row.update(
                {
                    "disc_ok": disc.ok,
                    "cont_ok": crep.ok,
                    "trace_status": summary.get("trace_status"),
                    "auth_length_m": summary.get("length_m"),
                    "auth_drive_duration_s": summary.get("drive_duration_s"),
                    "auth_charge_duration_s": summary.get("charge_duration_s"),
                    "auth_total_duration_s": summary.get("total_duration_s"),
                    "auth_min_soc": summary.get("min_soc"),
                    "auth_arrival_soc": summary.get("arrival_soc"),
                    "auth_charge_kwh": summary.get("charge_kwh_total"),
                    "auth_speed_min_kmh": summary.get("speed_min_kmh"),
                    "auth_motorway_min_kmh": summary.get("motorway_min_kmh"),
                    "auth_P_wheel_max_kw": summary.get("P_wheel_max_kw"),
                    "hist_defective_drive_only_m": hist_defective_m,
                    "hist_journey_length_m": hist_journey_m,
                    "hist_defective_km": None
                    if hist_defective_m is None
                    else float(hist_defective_m) / 1000.0,
                    "hist_journey_km": None
                    if hist_journey_m is None
                    else float(hist_journey_m) / 1000.0,
                    "auth_vs_hist_journey_agree": (
                        hist_journey_m is not None
                        and abs(auth_m - float(hist_journey_m)) <= TOL_M
                    ),
                    "extras_length_m": ex.length_m,
                    "length_agree_extras": abs(float(ex.length_m) - auth_m) <= TOL_M,
                    "n_osm_nodes": len(ex.osm_node_path),
                    "n_arc_ids": len(ex.arc_ids),
                    "n_actions": len(ex.action_trace),
                    "n_micros": len(ex.micro_trace),
                    "path": "->".join(sol.path_nodes),
                }
            )
            row["historical_defective_353p6km_superseded"] = True
            row["authoritative_distance_km"] = auth_m / 1000.0
            rows.append(row)
            print(
                f"{tag}: {sol.status.value} length_km={row['authoritative_distance_km']:.2f} "
                f"charge_kwh={row['auth_charge_kwh']} trace={row['trace_status']}"
            )
    finally:
        mpe.load_multiroute_pilot_config = orig

    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    keys = []
    seen = set()
    for r in rows:
        for k in r:
            if k not in seen:
                seen.add(k)
                keys.append(k)
    with OUT_CSV.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader()
        for r in rows:
            w.writerow(r)

    lines = [
        "# Physical replay trace integrity",
        "",
        "## Problem",
        "",
        "A publication-oriented `_speed_power_profile` diagnostic previously reported "
        "~353.6 km while full continuous replay reported ~429 km for the same eActros "
        "solution. That diagnostic processed DRIVE micros without applying CHARGE state "
        "updates and could terminate early while still emitting trip-like statistics.",
        "",
        "## Correction",
        "",
        "Authoritative journey metrics now come exclusively from "
        "`continuous_replay_multiroute(..., emit_trace=True)` + `summarize_complete_trace`. "
        "Incomplete traces are labelled `INCOMPLETE` and excluded from complete-trip stats.",
        "",
        f"Tolerances: distance ≤ {TOL_M} m; SOC ≤ {TOL_SOC}.",
        "",
        "## Results",
        "",
        "| Case | Status | Auth. km | Charge kWh | Min SOC | Arrival SOC | Trace |",
        "| --- | --- | ---: | ---: | ---: | ---: | --- |",
    ]
    for r in rows:
        if r.get("status") != "OPTIMAL":
            lines.append(
                f"| {r['case']} | {r['status']} | — | — | — | — | {r.get('trace_status')} |"
            )
        else:
            lines.append(
                f"| {r['case']} | {r['status']} | {r['authoritative_distance_km']:.2f} | "
                f"{r['auth_charge_kwh']} | {r['auth_min_soc']:.4f} | "
                f"{r['auth_arrival_soc']:.4f} | {r['trace_status']} |"
            )
    lines.extend(
        [
            "",
            "The historical ~353.6 km figure (`profile_rebuild2_q10.drive_length_m` in "
            "`results/northbound_route_expansion_summary.json`) is **SUPERSEDED**. The same "
            "JSON already recorded the consistent continuous journey length (~429.2 km). "
            "Authoritative publication metrics must use the full replay trace only.",
            "",
            "## Reproduction",
            "",
            "```bash",
            "python scripts/run_physical_trace_reconciliation.py",
            "pytest -q tests/unit/test_physical_replay_trace.py",
            "```",
            "",
            f"CSV: `{OUT_CSV.relative_to(ROOT).as_posix()}`",
            "",
        ]
    )
    OUT_MD.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote {OUT_CSV}")
    print(f"Wrote {OUT_MD}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
