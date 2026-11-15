#!/usr/bin/env python
"""Stage C — compact Moroccan physical/operational robustness matrix (q=5 primary).

Predefined scenarios only. Does not tune parameters to preserve Benguerir.
q=2 refinement only when site decision differs from baseline or borderline.
"""

from __future__ import annotations

import csv
import hashlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import morocco_etruck.optimization.multiroute_placement_evaluation as mpe  # noqa: E402
from morocco_etruck.optimization.multiroute_adapter import (  # noqa: E402
    load_multiroute_pilot_config,
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

CFG = ROOT / "configs/optimization/multiroute_placement_pass2a.yaml"
FRIDGE = ROOT / "configs/energy/pass2_tomato_firm_ripe.yaml"
FRIDGE_LOW = ROOT / "configs/energy/task07b_thermal_low.yaml"
FRIDGE_SUMMER = ROOT / "configs/energy/task07b_thermal_summer.yaml"
V_EACTROS = ROOT / "configs/vehicles/eactros_600.yaml"
OUT_MATRIX = ROOT / "results/final_moroccan_robustness_matrix.csv"
OUT_STAB = ROOT / "results/final_site_decision_stability.csv"
OUT_PHYS = ROOT / "results/final_route_physics_breakdown.csv"
OUT_MD = ROOT / "reports/final_moroccan_robustness_results.md"

# Predefined scenario matrix (independent factors; not full Cartesian)
SCENARIOS = [
    # baseline
    dict(id="B0_baseline_soc08_p5300_peak_q5", soc=0.8, payload=5300.0, adapt_peak=True, adapt_cont=False, fridge=FRIDGE, charger_kw=350.0, q=5, demand="A_nb_tomato_p5300_soc08"),
    dict(id="F1_soc05_q5", soc=0.5, payload=5300.0, adapt_peak=True, adapt_cont=False, fridge=FRIDGE, charger_kw=350.0, q=5, demand="A_nb_tomato_p5300_soc05"),
    dict(id="F1_soc10_q5", soc=1.0, payload=5300.0, adapt_peak=True, adapt_cont=False, fridge=FRIDGE, charger_kw=350.0, q=5, demand="A_nb_tomato_p5300_soc10"),
    dict(id="F2_payload15t_q5", soc=0.8, payload=15000.0, adapt_peak=True, adapt_cont=False, fridge=FRIDGE, charger_kw=350.0, q=5, demand="A_nb_tomato_p15000_soc08"),
    dict(id="F3_cont_power_q5", soc=0.8, payload=5300.0, adapt_peak=False, adapt_cont=True, fridge=FRIDGE, charger_kw=350.0, q=5, demand="A_nb_tomato_p5300_soc08"),
    dict(id="F3_fixed_speed_q5", soc=0.8, payload=5300.0, adapt_peak=False, adapt_cont=False, fridge=FRIDGE, charger_kw=350.0, q=5, demand="A_nb_tomato_p5300_soc08"),
    dict(id="F5_refrig_low_q5", soc=0.8, payload=5300.0, adapt_peak=True, adapt_cont=False, fridge=FRIDGE_LOW, charger_kw=350.0, q=5, demand="A_nb_tomato_p5300_soc08"),
    dict(id="F5_refrig_summer_q5", soc=0.8, payload=5300.0, adapt_peak=True, adapt_cont=False, fridge=FRIDGE_SUMMER, charger_kw=350.0, q=5, demand="A_nb_tomato_p5300_soc08"),
    dict(id="F6_charger_150kw_q5", soc=0.8, payload=5300.0, adapt_peak=True, adapt_cont=False, fridge=FRIDGE, charger_kw=150.0, q=5, demand="A_nb_tomato_p5300_soc08"),
]


def _patch(sp):
    orig = mpe.load_multiroute_pilot_config

    def wrapped(path, *, root):
        c = orig(path, root=root)
        c.speed_policy = dict(sp)
        return c

    mpe.load_multiroute_pilot_config = wrapped
    return orig


def _classify(baseline_sites: str, sites: str, served: bool, cont_ok: bool) -> str:
    if not served:
        return "CONDITION_DEPENDENT"
    if not cont_ok:
        return "NUMERICALLY_UNRESOLVED"
    if sites == baseline_sites:
        return "PHYSICAL_SCENARIO_STABLE_WITHIN_TESTED_RANGE"
    return "CONDITION_DEPENDENT"


def main() -> int:
    base = load_multiroute_pilot_config(
        ROOT / "configs/optimization/multiroute_pilot.yaml", root=ROOT
    )
    cfg = load_multiroute_placement_config(CFG, root=ROOT)
    rows = []
    phys_rows = []
    baseline_sites = None

    for sc in SCENARIOS:
        sp = dict(base.speed_policy)
        sp["adapt_speed_to_peak_power"] = bool(sc["adapt_peak"])
        sp["adapt_speed_to_continuous_power"] = bool(sc["adapt_cont"])
        sp["min_adapt_speed_mps"] = 1.0 / 3.6
        orig = _patch(sp)
        try:
            # demand name may not exist for forced soc — fall back
            demand = sc["demand"]
            if demand not in cfg.demand_scenarios:
                demand = "A_nb_tomato_p5300_soc08"
            context = prepare_multiroute_placement_context(
                cfg,
                root=ROOT,
                demand_name=demand,
                energy_quantum_kwh=int(sc["q"]),
                objective_mode="enroute_incremental_cost",
                vehicle_yaml=V_EACTROS,
                road_cost_per_km=100.0,
                fridge_yaml=Path(sc["fridge"]),
                charger_power_kw=float(sc["charger_kw"]),
                max_alternatives_for_union=4,
            )
            prep = next(iter(context["prepared"].values()))
            # Departure SOC comes only from the named demand scenario (no force_soc).
            installed = {s.id for s in cfg.sites}
            ball = evaluate_multiroute_mission(
                prep,
                installed=installed,
                sites=cfg.sites,
                max_seconds=cfg.solver_max_seconds,
                max_expansions=cfg.solver_max_expansions,
            )
            enum_rows, e_inc, _ = run_multiroute_enumeration(
                cfg,
                root=ROOT,
                demand_name=demand,
                capex_name="equal",
                budget_name="Ball",
                context=context,
            )
            best = "" if e_inc is None else ",".join(sorted(e_inc.site_ids))
            if baseline_sites is None and sc["id"].startswith("B0_"):
                baseline_sites = best
            label = _classify(baseline_sites or best, best, bool(ball.served), bool(ball.continuous_replay_ok))
            # also evaluate single-site / none for Factor 6 style on baseline only
            row = {
                "scenario_id": sc["id"],
                "q": sc["q"],
                "demand": demand,
                "adapt_peak": sc["adapt_peak"],
                "adapt_cont": sc["adapt_cont"],
                "charger_kw": sc["charger_kw"],
                "fridge": str(Path(sc["fridge"]).relative_to(ROOT)),
                "vehicle": str(V_EACTROS.relative_to(ROOT)),
                "ball_status": ball.status,
                "ball_served": bool(ball.served),
                "disc_ok": ball.discrete_replay_ok,
                "cont_ok": ball.continuous_replay_ok,
                "charge_kwh": ball.charge_kwh,
                "objective_cents": ball.objective_cents,
                "path": ball.path,
                "best_sites_Ball": best,
                "opt_sets": str(all_optimal_site_sets(enum_rows)),
                "coverage_Ball": None if e_inc is None else e_inc.coverage_serviceable,
                "decision_reliability": label,
                "assumption_status": "prospective_scenario_based",
                "legal_mass_status": "gross_mass_within_limit_axle_unverified",
                "replay_label": "SIMULATION_REPLAY_VALIDATED" if ball.continuous_replay_ok else "REPLAY_FAILED_OR_UNSERVED",
                "vehicle_sha16": hashlib.sha256(V_EACTROS.read_bytes()).hexdigest()[:16],
            }
            rows.append(row)
            phys_rows.append(
                {
                    "scenario_id": sc["id"],
                    "charge_kwh": ball.charge_kwh,
                    "objective_cents": ball.objective_cents,
                    "path": ball.path,
                    "served": ball.served,
                    "cont_ok": ball.continuous_replay_ok,
                }
            )
            print(
                f"{sc['id']}: served={ball.served} sites={best} label={label}",
                flush=True,
            )
            # q=2 refine if decision differs from baseline
            if (
                baseline_sites is not None
                and best != baseline_sites
                and int(sc["q"]) == 5
                and sc["id"] != "B0_baseline_soc08_p5300_peak_q5"
            ):
                context2 = prepare_multiroute_placement_context(
                    cfg,
                    root=ROOT,
                    demand_name=demand,
                    energy_quantum_kwh=2,
                    objective_mode="enroute_incremental_cost",
                    vehicle_yaml=V_EACTROS,
                    road_cost_per_km=100.0,
                    fridge_yaml=Path(sc["fridge"]),
                    charger_power_kw=float(sc["charger_kw"]),
                    max_alternatives_for_union=4,
                )
                prep2 = next(iter(context2["prepared"].values()))
                ball2 = evaluate_multiroute_mission(
                    prep2,
                    installed=installed,
                    sites=cfg.sites,
                    max_seconds=cfg.solver_max_seconds,
                    max_expansions=cfg.solver_max_expansions,
                )
                enum2, e2, _ = run_multiroute_enumeration(
                    cfg,
                    root=ROOT,
                    demand_name=demand,
                    capex_name="equal",
                    budget_name="Ball",
                    context=context2,
                )
                best2 = "" if e2 is None else ",".join(sorted(e2.site_ids))
                rows.append(
                    {
                        **row,
                        "scenario_id": sc["id"] + "_q2refine",
                        "q": 2,
                        "ball_status": ball2.status,
                        "ball_served": bool(ball2.served),
                        "disc_ok": ball2.discrete_replay_ok,
                        "cont_ok": ball2.continuous_replay_ok,
                        "charge_kwh": ball2.charge_kwh,
                        "objective_cents": ball2.objective_cents,
                        "path": ball2.path,
                        "best_sites_Ball": best2,
                        "opt_sets": str(all_optimal_site_sets(enum2)),
                        "decision_reliability": _classify(
                            baseline_sites, best2, bool(ball2.served), bool(ball2.continuous_replay_ok)
                        ),
                    }
                )
                print(f"  q2 refine: sites={best2}", flush=True)
        except Exception as exc:  # noqa: BLE001
            rows.append(
                {
                    "scenario_id": sc["id"],
                    "error": str(exc),
                    "decision_reliability": "NUMERICALLY_UNRESOLVED",
                }
            )
            print(f"{sc['id']}: ERROR {exc}", flush=True)
        finally:
            mpe.load_multiroute_pilot_config = orig

    # Availability factor on baseline graph (none / each / both) at q=5
    sp = dict(base.speed_policy)
    sp["adapt_speed_to_peak_power"] = True
    sp["adapt_speed_to_continuous_power"] = False
    sp["min_adapt_speed_mps"] = 1.0 / 3.6
    orig = _patch(sp)
    try:
        context = prepare_multiroute_placement_context(
            cfg,
            root=ROOT,
            demand_name="A_nb_tomato_p5300_soc08",
            energy_quantum_kwh=5,
            objective_mode="enroute_incremental_cost",
            vehicle_yaml=V_EACTROS,
            road_cost_per_km=100.0,
            fridge_yaml=FRIDGE,
            charger_power_kw=350.0,
            max_alternatives_for_union=4,
        )
        prep = next(iter(context["prepared"].values()))
        for name, subset in [
            ("F6_none", set()),
            ("F6_benguerir_only", {"y_benguerir_ac"}),
            ("F6_settat_only", {"y_settat_ac"}),
            ("F6_both", {s.id for s in cfg.sites}),
        ]:
            ball = evaluate_multiroute_mission(
                prep,
                installed=subset,
                sites=cfg.sites,
                max_seconds=cfg.solver_max_seconds,
                max_expansions=cfg.solver_max_expansions,
            )
            rows.append(
                {
                    "scenario_id": name,
                    "q": 5,
                    "installed_forced": ",".join(sorted(subset)),
                    "ball_status": ball.status,
                    "ball_served": bool(ball.served),
                    "disc_ok": ball.discrete_replay_ok,
                    "cont_ok": ball.continuous_replay_ok,
                    "charge_kwh": ball.charge_kwh,
                    "objective_cents": ball.objective_cents,
                    "path": ball.path,
                    "best_sites_Ball": ",".join(sorted(subset)),
                    "decision_reliability": (
                        "PHYSICAL_SCENARIO_STABLE_WITHIN_TESTED_RANGE"
                        if ball.served and ball.continuous_replay_ok
                        else "CONDITION_DEPENDENT"
                    ),
                    "replay_label": "SIMULATION_REPLAY_VALIDATED"
                    if ball.continuous_replay_ok
                    else "REPLAY_FAILED_OR_UNSERVED",
                }
            )
            print(f"{name}: served={ball.served}", flush=True)
    finally:
        mpe.load_multiroute_pilot_config = orig

    OUT_MATRIX.parent.mkdir(parents=True, exist_ok=True)
    keys = []
    seen = set()
    for r in rows:
        for k in r:
            if k not in seen:
                seen.add(k)
                keys.append(k)
    with OUT_MATRIX.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=keys, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow(r)
    with OUT_PHYS.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(
            f,
            fieldnames=list(phys_rows[0].keys()) if phys_rows else ["scenario_id"],
            extrasaction="ignore",
        )
        w.writeheader()
        for r in phys_rows:
            w.writerow(r)

    # Stability summary
    stab = []
    for r in rows:
        stab.append(
            {
                "scenario_id": r.get("scenario_id"),
                "best_sites": r.get("best_sites_Ball"),
                "decision_reliability": r.get("decision_reliability"),
                "served": r.get("ball_served"),
                "grid_note": "q5_primary;_q2_only_if_decision_changed",
                "physical_validation": "PHYSICALLY_UNVALIDATED_field;SIMULATION_REPLAY_ONLY",
            }
        )
    with OUT_STAB.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(stab[0].keys()), extrasaction="ignore")
        w.writeheader()
        for r in stab:
            w.writerow(r)

    served_sites = {r.get("best_sites_Ball") for r in rows if r.get("ball_served")}
    lines = [
        "# Final Moroccan robustness results",
        "",
        f"Baseline Ball sites: `{baseline_sites}`",
        f"Distinct served site signatures in matrix: `{served_sites}`",
        "",
        "DEM: COPDEM GLO-30 DSM along OSM centerline — **not** surveyed pavement grade.",
        "Chargers: hypothetical future HGV installations (Benguerir/Settat).",
        "Replay label: `SIMULATION_REPLAY_VALIDATED` ≠ field validation.",
        "",
        "| Scenario | Served | Sites | Reliability |",
        "| --- | --- | --- | --- |",
    ]
    for r in rows:
        lines.append(
            f"| {r.get('scenario_id')} | {r.get('ball_served')} | "
            f"{r.get('best_sites_Ball')} | {r.get('decision_reliability')} |"
        )
    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "A site may be `GRID_STABLE_WITHIN_TESTED_RANGE` without being "
            "`PHYSICAL_SCENARIO_STABLE_WITHIN_TESTED_RANGE`. Negative / unserved "
            "scenarios are retained.",
            "",
            "## Reproduction",
            "",
            "```bash",
            "python scripts/run_final_moroccan_robustness.py",
            "```",
            "",
        ]
    )
    OUT_MD.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote {OUT_MATRIX} ({len(rows)} rows)")
    print(f"Wrote {OUT_STAB}")
    print(f"Wrote {OUT_PHYS}")
    print(f"Wrote {OUT_MD}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
