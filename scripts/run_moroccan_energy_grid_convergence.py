#!/usr/bin/env python
"""P0.3 — Battery quantum convergence on the canonical Agadir→Casablanca graph."""

from __future__ import annotations

import csv
import hashlib
import json
import sys
import time
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
    run_multiroute_branch_and_bound,
    run_multiroute_enumeration,
)
from morocco_etruck.optimization.quantization_audit import (  # noqa: E402
    summarize_quantization_policy,
)

CFG_NB = ROOT / "configs/optimization/multiroute_placement_pass2a.yaml"
CFG_SB = ROOT / "configs/optimization/multiroute_placement_08.yaml"
FRIDGE_NB = ROOT / "configs/energy/pass2_tomato_firm_ripe.yaml"
FRIDGE_SB = ROOT / "configs/energy/task07b_thermal_nominal.yaml"
VPATH = ROOT / "configs/vehicles/eactros_600.yaml"
VPATH_VOLVO = ROOT / "configs/vehicles/volvo_fh_electric_4x2_540kwh.yaml"
OUT_CSV = ROOT / "results/moroccan_energy_grid_convergence.csv"
OUT_MD = ROOT / "reports/battery_quantization_and_convergence.md"


def _patch(sp):
    orig = mpe.load_multiroute_pilot_config

    def wrapped(path, *, root):
        c = orig(path, root=root)
        c.speed_policy = dict(sp)
        return c

    mpe.load_multiroute_pilot_config = wrapped
    return orig


def _run_panel(
    *,
    label: str,
    cfg_path: Path,
    demand: str,
    fridge: Path,
    vehicle: Path,
    max_alts: int,
    qs: list[int],
    adapt: bool,
) -> list[dict]:
    base = load_multiroute_pilot_config(
        ROOT / "configs/optimization/multiroute_pilot.yaml", root=ROOT
    )
    sp = dict(base.speed_policy)
    sp["adapt_speed_to_peak_power"] = adapt
    sp["adapt_speed_to_continuous_power"] = False
    sp["min_adapt_speed_mps"] = 1.0 / 3.6
    orig = _patch(sp)
    rows = []
    try:
        cfg = load_multiroute_placement_config(cfg_path, root=ROOT)
        for q in qs:
            t0 = time.perf_counter()
            try:
                context = prepare_multiroute_placement_context(
                    cfg,
                    root=ROOT,
                    demand_name=demand,
                    energy_quantum_kwh=q,
                    objective_mode="enroute_incremental_cost",
                    vehicle_yaml=vehicle,
                    road_cost_per_km=100.0,
                    fridge_yaml=fridge,
                    charger_power_kw=350.0,
                    max_alternatives_for_union=max_alts,
                )
            except Exception as exc:  # noqa: BLE001
                rows.append(
                    {
                        "panel": label,
                        "q": q,
                        "status": "BUILD_ERROR",
                        "error": str(exc),
                        "sec": time.perf_counter() - t0,
                    }
                )
                continue
            prep = next(iter(context["prepared"].values()))
            installed = {s.id for s in cfg.sites}
            ball = evaluate_multiroute_mission(
                prep,
                installed=installed,
                sites=cfg.sites,
                max_seconds=cfg.solver_max_seconds,
                max_expansions=cfg.solver_max_expansions,
            )
            place = {}
            try:
                enum_rows, e_inc, _ = run_multiroute_enumeration(
                    cfg,
                    root=ROOT,
                    demand_name=demand,
                    capex_name="equal",
                    budget_name="Ball",
                    context=context,
                )
                bb, _ = run_multiroute_branch_and_bound(
                    cfg,
                    root=ROOT,
                    demand_name=demand,
                    capex_name="equal",
                    budget_name="Ball",
                    context=context,
                )
                b_inc = bb.incumbent
                agree = (
                    (e_inc is None and b_inc is None)
                    or (
                        e_inc is not None
                        and b_inc is not None
                        and abs(e_inc.coverage_serviceable - b_inc.coverage_serviceable)
                        <= 1e-9
                        and abs(e_inc.secondary_cost - b_inc.secondary_cost) <= 1e-6
                    )
                )
                place = {
                    "ball_coverage": None
                    if b_inc is None
                    else b_inc.coverage_serviceable,
                    "min_sites": None if b_inc is None else len(b_inc.site_ids),
                    "best_sites": ""
                    if b_inc is None
                    else ",".join(sorted(b_inc.site_ids)),
                    "opt_sets": str(all_optimal_site_sets(enum_rows)),
                    "bb_enum_agree": agree,
                    "optimality": bb.optimality_status.value,
                    "secondary_cost": None if b_inc is None else b_inc.secondary_cost,
                }
            except Exception as exc:  # noqa: BLE001
                place = {"place_error": str(exc)}
            rows.append(
                {
                    "panel": label,
                    "q": q,
                    "max_alts": max_alts,
                    "adapt_peak": adapt,
                    "n_arcs": len(prep.template.arcs),
                    "ball_status": ball.status,
                    "ball_served": bool(ball.served),
                    "disc_ok": ball.discrete_replay_ok,
                    "cont_ok": ball.continuous_replay_ok,
                    "charge_kwh": ball.charge_kwh,
                    "objective_cents": ball.objective_cents,
                    "reason": ball.reason,
                    "sec": time.perf_counter() - t0,
                    "vehicle": str(vehicle.relative_to(ROOT)),
                    "demand": demand,
                    **place,
                }
            )
            print(
                f"{label} q={q}: ball={ball.status} served={ball.served} "
                f"sites={place.get('best_sites')} sec={rows[-1]['sec']:.1f}",
                flush=True,
            )
    finally:
        mpe.load_multiroute_pilot_config = orig
    return rows


def main() -> int:
    rows: list[dict] = []
    # Primary: canonical 4-alt northbound eActros peak-adapt
    rows.extend(
        _run_panel(
            label="northbound_eactros_canonical4_peakadapt",
            cfg_path=CFG_NB,
            demand="A_nb_tomato_p5300_soc08",
            fridge=FRIDGE_NB,
            vehicle=VPATH,
            max_alts=4,
            qs=[10, 5, 2],
            adapt=True,
        )
    )
    # q=1 attempt on same graph (may be heavy)
    rows.extend(
        _run_panel(
            label="northbound_eactros_canonical4_peakadapt",
            cfg_path=CFG_NB,
            demand="A_nb_tomato_p5300_soc08",
            fridge=FRIDGE_NB,
            vehicle=VPATH,
            max_alts=4,
            qs=[1],
            adapt=True,
        )
    )
    # Southbound heavy q-sensitive counterexample (Task 08 H80)
    rows.extend(
        _run_panel(
            label="southbound_H80_volvo_maxalts2",
            cfg_path=CFG_SB,
            demand="H80_dem_p15000_soc08",
            fridge=FRIDGE_SB,
            vehicle=VPATH_VOLVO,
            max_alts=2,
            qs=[10, 5],
            adapt=False,
        )
    )

    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    keys = []
    seen = set()
    for r in rows:
        for k in r:
            if k not in seen:
                seen.add(k)
                keys.append(k)
    with OUT_CSV.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=keys, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow(r)

    nb = [r for r in rows if r["panel"].startswith("northbound") and r.get("q") in (10, 5, 2, 1)]
    site_sets = {
        (r.get("q"), r.get("best_sites"), r.get("ball_served")) for r in nb if "best_sites" in r
    }
    stable = len({r.get("best_sites") for r in nb if r.get("ball_served")}) <= 1 and any(
        r.get("ball_served") for r in nb
    )
    pol = summarize_quantization_policy()
    lines = [
        "# Battery quantization and grid convergence",
        "",
        "## Quantization policy",
        "",
        "Conservative flooring after DRIVE (table build) and CHARGE/WAIT (stationary snap) "
        "is **retained**. Removing it would risk optimistic discrete feasibility.",
        "",
        f"- Novel algorithm claim: `{pol['novel_algorithm_claim']}`",
        f"- Adopted representation change: `{pol['adopted_correction']}`",
        f"- Rationale: {pol['rationale']}",
        "",
        "Unit proof that CHARGE can yield zero discrete gain: "
        "`tests/unit/test_quantization_error_and_charge.py`.",
        "",
        "## Northbound canonical max_alts=4 (eActros, peak-adapt)",
        "",
        "| q | Ball status | Served | Best sites (Ball) | Opt sets | B&B↔enum | Cont replay | sec |",
        "| --- | --- | --- | --- | --- | --- | --- | ---: |",
    ]
    for r in nb:
        lines.append(
            f"| {r.get('q')} | {r.get('ball_status')} | {r.get('ball_served')} | "
            f"{r.get('best_sites')} | {r.get('opt_sets')} | {r.get('bb_enum_agree')} | "
            f"{r.get('cont_ok')} | {r.get('sec'):.1f} |"
            if r.get("sec") is not None
            else f"| {r.get('q')} | {r.get('status', r.get('ball_status'))} | — | — | — | — | — | — |"
        )
    sb = [r for r in rows if r["panel"].startswith("southbound")]
    lines.extend(
        [
            "",
            f"Site-set stability among served northbound q-grid rows: **{stable}** "
            f"(distinct served site signatures={site_sets}).",
            "",
            "q=1 is **not** an exact continuous optimum. Continuous replay validates a "
            "candidate path; it does not prove uniqueness among continuous-feasible paths.",
            "",
            "## Southbound H80 counterexample (Task 08)",
            "",
            "| q | Ball status | Served | Best sites |",
            "| --- | --- | --- | --- |",
        ]
    )
    for r in sb:
        lines.append(
            f"| {r.get('q')} | {r.get('ball_status')} | {r.get('ball_served')} | {r.get('best_sites')} |"
        )
    lines.extend(
        [
            "",
            "## Reproduction",
            "",
            "```bash",
            "python scripts/run_moroccan_energy_grid_convergence.py",
            "pytest -q tests/unit/test_quantization_error_and_charge.py",
            "```",
            "",
            f"CSV: `{OUT_CSV.relative_to(ROOT).as_posix()}`",
            "",
            f"Config hashes: vehicle={hashlib.sha256(VPATH.read_bytes()).hexdigest()[:16]} "
            f"fridge_nb={hashlib.sha256(FRIDGE_NB.read_bytes()).hexdigest()[:16]}",
            "",
        ]
    )
    OUT_MD.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote {OUT_CSV} ({len(rows)} rows)")
    print(f"Wrote {OUT_MD}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
