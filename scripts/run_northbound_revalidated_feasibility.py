#!/usr/bin/env python
"""PRIORITY 4: Revalidate Agadir→Casablanca A80 after power-feasible climb speeds.

Opt-in via speed_policy.adapt_speed_to_peak_power (and optional continuous).
Does not retune OEM power, fabricate chargers, or smooth DEM.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from morocco_etruck.energy.vehicle import (  # noqa: E402
    empty_combination_kg,
    gcm_from_payload,
    load_vehicle,
    validate_gcm,
)
from morocco_etruck.optimization.multiroute_adapter import (  # noqa: E402
    load_multiroute_pilot_config as _load_pilot,
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
import morocco_etruck.optimization.multiroute_placement_evaluation as mpe  # noqa: E402

CFG = ROOT / "configs/optimization/multiroute_placement_pass2a.yaml"
FRIDGE = ROOT / "configs/energy/pass2_tomato_firm_ripe.yaml"
VEHICLES = {
    "volvo_475": ROOT / "configs/vehicles/volvo_fh_electric_4x2_540kwh.yaml",
    "eactros_600": ROOT / "configs/vehicles/eactros_600.yaml",
}
OUT_CSV = ROOT / "results/northbound_revalidated_placement.csv"
OUT_JSON = ROOT / "results/northbound_revalidated_summary.json"
DEMAND = "A_nb_tomato_p5300_soc08"
ROAD_CENTS = 100.0
MOROCCAN_PTRA = 40000.0


def _speed_policy(
    *,
    adapt_peak: bool,
    adapt_cont: bool,
    min_adapt_kmh: float,
) -> dict[str, Any]:
    base = _load_pilot(ROOT / "configs/optimization/multiroute_pilot.yaml", root=ROOT)
    sp = dict(base.speed_policy)
    sp["adapt_speed_to_peak_power"] = bool(adapt_peak)
    sp["adapt_speed_to_continuous_power"] = bool(adapt_cont)
    sp["min_adapt_speed_mps"] = float(min_adapt_kmh) / 3.6
    sp["note_decree_2_10_420"] = (
        "Motorway max 80 km/h (>19 t goods); non-motorway outside urban generally 70; "
        "normal motorway min 60 (Art. 18). Cruise defaults are legal caps, not mandatory "
        "climb speeds. Operation below 60 km/h on motorways is flagged, not asserted legal."
    )
    return sp


def _patch_pilot_speed_policy(sp: dict[str, Any]):
    """Patch both module bindings used by prepare_multiroute_placement_context."""
    orig = mpe.load_multiroute_pilot_config

    def _wrapped(path, *, root):  # type: ignore[no-untyped-def]
        c = orig(path, root=root)
        c.speed_policy = dict(sp)
        return c

    mpe.load_multiroute_pilot_config = _wrapped  # type: ignore[assignment]
    return orig


def _legal(vehicle, payload: float) -> dict[str, Any]:
    empty = empty_combination_kg(vehicle)
    gcm = gcm_from_payload(payload, vehicle)
    validate_gcm(gcm, vehicle)
    return {
        "empty_combination_kg": empty,
        "gcm_kg": gcm,
        "legal_mass_status": "gross_mass_within_limit_axle_unverified",
        "gross_within_40t": gcm <= MOROCCAN_PTRA + 1e-6,
    }


def _run_case(
    *,
    vehicle_name: str,
    vpath: Path,
    adapt_peak: bool,
    adapt_cont: bool,
    min_adapt_kmh: float,
    max_alts: int,
    q: int,
    installed_mode: str,
    do_placement: bool,
    policy_tag: str,
) -> dict[str, Any]:
    cfg = load_multiroute_placement_config(CFG, root=ROOT)
    sp = _speed_policy(
        adapt_peak=adapt_peak, adapt_cont=adapt_cont, min_adapt_kmh=min_adapt_kmh
    )
    orig = _patch_pilot_speed_policy(sp)
    t0 = time.perf_counter()
    row: dict[str, Any] = {
        "policy_tag": policy_tag,
        "vehicle": vehicle_name,
        "demand": DEMAND,
        "payload_kg": 5300.0,
        "soc": 0.8,
        "q": q,
        "max_alts": max_alts,
        "adapt_speed_to_peak_power": adapt_peak,
        "adapt_speed_to_continuous_power": adapt_cont,
        "min_adapt_speed_kmh": min_adapt_kmh,
        "installed_mode": installed_mode,
        "fridge": str(FRIDGE.relative_to(ROOT)),
    }
    vehicle = load_vehicle(vpath)
    row.update(_legal(vehicle, 5300.0))
    try:
        ctx = prepare_multiroute_placement_context(
            cfg,
            root=ROOT,
            demand_name=DEMAND,
            energy_quantum_kwh=q,
            objective_mode="enroute_incremental_cost",
            vehicle_yaml=vpath,
            road_cost_per_km=ROAD_CENTS,
            fridge_yaml=FRIDGE,
            charger_power_kw=350.0,
            max_alternatives_for_union=max_alts,
        )
        prep = next(iter(ctx["prepared"].values()))
        row["dem_complete"] = bool(prep.ctx.dem_complete)
        row["adapt_flag_on_ctx"] = bool(prep.ctx.adapt_speed_to_peak_power)
        row["adapt_cont_flag_on_ctx"] = bool(prep.ctx.adapt_speed_to_continuous_power)
        if installed_mode == "none":
            installed: set[str] = set()
        else:
            installed = {s.id for s in cfg.sites}
        r = evaluate_multiroute_mission(
            prep,
            installed=installed,
            sites=cfg.sites,
            max_seconds=cfg.solver_max_seconds,
            max_expansions=cfg.solver_max_expansions,
        )
        limiting = "unknown"
        if r.served:
            limiting = "none_served"
        elif not adapt_peak:
            limiting = "fixed_cruise_or_other_pre_adapt"
        elif r.status == "INFEASIBLE" or not r.served:
            limiting = (
                "range_before_reachable_candidate_chargers_or_soc_floor"
            )
        row.update(
            {
                "mission_status": r.status,
                "served": bool(r.served),
                "uncertified": bool(r.uncertified),
                "discrete_replay_ok": r.discrete_replay_ok,
                "continuous_replay_ok": r.continuous_replay_ok,
                "reason": r.reason,
                "limiting_cause_class": limiting,
                "objective_cents": r.objective_cents,
                "charge_kwh": r.charge_kwh,
                "charges": r.charges,
                "path": r.path,
            }
        )

        if do_placement:
            for bname in ("B0", "Ball"):
                enum_rows, e_inc, _ = run_multiroute_enumeration(
                    cfg,
                    root=ROOT,
                    demand_name=DEMAND,
                    capex_name="equal",
                    budget_name=bname,
                    context=ctx,
                )
                bb, _ = run_multiroute_branch_and_bound(
                    cfg,
                    root=ROOT,
                    demand_name=DEMAND,
                    capex_name="equal",
                    budget_name=bname,
                    context=ctx,
                )
                b_inc = bb.incumbent
                agree = False
                if e_inc is not None and b_inc is not None:
                    agree = (
                        abs(e_inc.coverage_serviceable - b_inc.coverage_serviceable)
                        <= 1e-9
                        and abs(e_inc.secondary_cost - b_inc.secondary_cost) <= 1e-6
                    )
                elif e_inc is None and b_inc is None:
                    agree = True
                opt_sets = all_optimal_site_sets(enum_rows)
                row[f"place_{bname}_bb_coverage"] = (
                    None if b_inc is None else b_inc.coverage_serviceable
                )
                row[f"place_{bname}_bb_sites"] = (
                    "" if b_inc is None else ",".join(sorted(b_inc.site_ids))
                )
                row[f"place_{bname}_enum_sites"] = (
                    "" if e_inc is None else ",".join(sorted(e_inc.site_ids))
                )
                row[f"place_{bname}_bb_enum_agree"] = agree
                row[f"place_{bname}_opt_sets"] = str(opt_sets)
                row[f"place_{bname}_optimality"] = bb.optimality_status.value
    except Exception as exc:  # noqa: BLE001
        row["mission_status"] = "BUILD_OR_SOLVE_ERROR"
        row["error"] = str(exc)
    finally:
        mpe.load_multiroute_pilot_config = orig  # type: ignore[assignment]

    row["sec"] = time.perf_counter() - t0
    return row


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--q", type=int, default=10)
    ap.add_argument(
        "--quick",
        action="store_true",
        help="Only Volvo peak-adapt vs fixed, alts=2, none/both (faster smoke).",
    )
    args = ap.parse_args()

    cases: list[dict[str, Any]] = []
    if args.quick:
        schedule = [
            ("volvo_475", "A_fixed", False, False, 1.0, 2, False),
            ("volvo_475", "C_peak_adapt", True, False, 1.0, 2, True),
            ("volvo_475", "C_peak_adapt", True, False, 1.0, 2, False),  # none install via mode
        ]
        # expand installed modes manually below
        policies_quick = [
            ("volvo_475", "A_fixed", False, False, 1.0, 2, "none", False),
            ("volvo_475", "A_fixed", False, False, 1.0, 2, "both", False),
            ("volvo_475", "C_peak_adapt", True, False, 1.0, 2, "none", False),
            ("volvo_475", "C_peak_adapt", True, False, 1.0, 2, "both", True),
        ]
        run_list = policies_quick
    else:
        run_list = []
        policies = [
            ("A_fixed", False, False, 1.0),
            ("C_peak_adapt", True, False, 1.0),
            ("D_cont_adapt", True, True, 1.0),
            ("C_peak_adapt_floor60", True, False, 60.0),
        ]
        for vname in VEHICLES:
            for tag, apk, act, mk in policies:
                for max_alts in (2, 4):
                    for installed in ("none", "both"):
                        do_place = (
                            installed == "both"
                            and max_alts == 2
                            and tag in {"A_fixed", "C_peak_adapt"}
                        )
                        run_list.append(
                            (vname, tag, apk, act, mk, max_alts, installed, do_place)
                        )

    for vname, tag, apk, act, mk, max_alts, installed, do_place in run_list:
        print(
            f"=== {vname} {tag} alts={max_alts} inst={installed} place={do_place} ===",
            flush=True,
        )
        row = _run_case(
            vehicle_name=vname,
            vpath=VEHICLES[vname],
            adapt_peak=apk,
            adapt_cont=act,
            min_adapt_kmh=mk,
            max_alts=max_alts,
            q=args.q,
            installed_mode=installed,
            do_placement=do_place,
            policy_tag=tag,
        )
        cases.append(row)
        print(
            f"  -> {row.get('mission_status')} served={row.get('served')} "
            f"reason={row.get('reason')} sec={row.get('sec'):.1f}",
            flush=True,
        )

    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    keys: list[str] = []
    seen: set[str] = set()
    for r in cases:
        for k in r:
            if k not in seen:
                seen.add(k)
                keys.append(k)
    with OUT_CSV.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=keys, extrasaction="ignore")
        w.writeheader()
        for r in cases:
            w.writerow(
                {
                    k: (
                        json.dumps(v)
                        if isinstance(v, (dict, list, set))
                        else v
                    )
                    for k, v in r.items()
                }
            )

    served_adapt = [
        c for c in cases if c.get("policy_tag") == "C_peak_adapt" and c.get("served")
    ]
    n_adapt = sum(1 for c in cases if c.get("policy_tag") == "C_peak_adapt")
    summary = {
        "n_cases": len(cases),
        "n_served_peak_adapt": len(served_adapt),
        "n_peak_adapt_cases": n_adapt,
        "reproduce": "python scripts/run_northbound_revalidated_feasibility.py",
        "note": (
            "Peak-adapt is a physical model correction (power-feasible climb speed), "
            "not a new optimizer. Floor60 tests motorway normal-min constraint."
        ),
    }
    OUT_JSON.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"Wrote {OUT_CSV}")
    print(f"Served under peak-adapt: {len(served_adapt)} / {n_adapt}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
