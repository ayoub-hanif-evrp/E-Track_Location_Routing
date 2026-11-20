"""Stage C: regenerate paper_campaign evidence under HOS-in-search.

Phases (can run selectively):
  archive          — snapshot pre-HOS CSVs
  portfolio_rescore — re-eval frozen C/E/F site sets under HOS (fast headline)
  ablation_live     — identical-site cross masks for B2 (placement vs flex)
  q1_boundary       — q=1 refinement for flip/near-reserve cells
  blind_greedy      — F without enum oracle (B0–B2)
  larger_instance   — denser candidate-set certification row
  stability         — refresh uncertainty stability summary
  headline_enum     — full A–F exhaustive enum under HOS (slow; new cache tag)
  mini_panel        — Gate-B style B0/B2/Ball audit-only check on frozen sites
  all_fast          — archive + portfolio_rescore + ablation + q1 + blind + larger + stability + mini
  all               — all_fast + headline_enum

Writes only under results/paper_campaign/.
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from morocco_etruck.energy.vehicle import load_vehicle
from morocco_etruck.optimization.multiroute_adapter import load_multiroute_pilot_config
from morocco_etruck.optimization.multiroute_placement import load_multiroute_placement_config
from morocco_etruck.optimization.multiroute_placement_evaluation import (
    prepare_multiroute_placement_context,
)
from run_final_operational_correction import evaluate_mission_operational, evaluate_subset
from run_paper_scientific_results_campaign import (
    CFG_HEADLINE,
    FRIDGE,
    FULL_SITE_IDS,
    OUT,
    ROAD_CENTS,
    VEHICLES,
    _git_sha,
    _mission_masks,
    _patch_realistic_speed_policy,
    _run_af_portfolio,
    _score,
    _temp_demand_cfg,
    _write_csv,
    write_efficiency_from_missions,
    write_report,
)

ARCHIVE = OUT / "_pre_hos_archive"
SHA = _git_sha()


def _parse_sites(raw: Any) -> set[str]:
    if raw is None or (isinstance(raw, float) and pd.isna(raw)):
        return set()
    s = str(raw).strip()
    if not s or s.lower() == "nan":
        return set()
    return {x.strip() for x in s.split(",") if x.strip() and x.strip().lower() != "nan"}


def archive_pre_hos() -> None:
    ARCHIVE.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d_%H%M%S")
    dest = ARCHIVE / stamp
    dest.mkdir(parents=True, exist_ok=True)
    for name in (
        "q2_critical_portfolio.csv",
        "q2_critical_missions.csv",
        "payload_soc_frontier.csv",
        "payload_soc_frontier_q2_confirm.csv",
        "robustness_matrix.csv",
        "placement_flexibility_ablation.csv",
        "campaign_manifest.json",
    ):
        src = OUT / name
        if src.exists():
            shutil.copy2(src, dest / name)
    (dest / "README.txt").write_text(
        f"Pre-HOS snapshot at {stamp}; git={SHA}\n", encoding="utf-8"
    )
    print(f"Archived pre-HOS CSVs -> {dest}", flush=True)


def _corridor_missions() -> list[dict[str, Any]]:
    raw = __import__("yaml").safe_load(CFG_HEADLINE.read_text(encoding="utf-8"))
    return list(raw["demand_scenarios"]["corridor_eactros_equal"]["missions"])


_PREP_CACHE: dict[tuple, tuple] = {}


def _prepare_one(
    *,
    vehicle_key: str,
    od_id: str,
    payload: float,
    soc: float,
    q: int = 2,
):
    """Single-OD prep (fast path used by smoke / frontier). Cached in-process."""
    key = (vehicle_key, od_id, float(payload), float(soc), int(q))
    if key in _PREP_CACHE:
        return _PREP_CACHE[key]
    cfg_path = _temp_demand_cfg(od_id, float(payload), float(soc))
    cfg = load_multiroute_placement_config(cfg_path, root=ROOT)
    vpath = VEHICLES[vehicle_key]
    vehicle = load_vehicle(vpath)
    t0 = time.perf_counter()
    context = prepare_multiroute_placement_context(
        cfg,
        root=ROOT,
        demand_name="frontier_cell",
        energy_quantum_kwh=q,
        objective_mode="enroute_incremental_cost",
        vehicle_yaml=vpath,
        road_cost_per_km=ROAD_CENTS,
        fridge_yaml=FRIDGE,
        charger_power_kw=350.0,
        max_alternatives_for_union=2,
        probe_serviceability=False,
    )
    pilot = load_multiroute_pilot_config(cfg.multiroute_pilot_path, root=ROOT)
    path_rows = pd.read_csv(pilot.path_alternatives_csv).to_dict(orient="records")
    masks = _mission_masks(context, path_rows)
    print(
        f"  prep {vehicle_key} {od_id} p={payload} soc={soc} q={q} "
        f"sec={time.perf_counter()-t0:.1f}",
        flush=True,
    )
    out = (cfg, vehicle, context, masks)
    _PREP_CACHE[key] = out
    return out


def _prepare_corridor(vehicle_key: str, q: int = 2):
    """Legacy batch prep (slow). Prefer _prepare_one for Stage C rescore."""
    cfg = load_multiroute_placement_config(CFG_HEADLINE, root=ROOT)
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
        probe_serviceability=False,
    )
    pilot = load_multiroute_pilot_config(cfg.multiroute_pilot_path, root=ROOT)
    path_rows = pd.read_csv(pilot.path_alternatives_csv).to_dict(orient="records")
    masks = _mission_masks(context, path_rows)
    return cfg, vehicle, context, masks


def _eval_installed_on_panel(
    *,
    vehicle_key: str,
    installed: set[str],
    route_mode: str,
    method_id: str,
    budget: str,
    q: int = 2,
    max_seconds: float | None = None,
    od_filter: set[str] | None = None,
) -> dict[str, Any]:
    """Evaluate one installed set over the 14-mission panel via single-OD prep."""
    mission_rows: list[dict] = []
    w_ops = w_energy = w_tot = 0.0
    for mdef in _corridor_missions():
        od = str(mdef["od_id"])
        if od_filter is not None and od not in od_filter:
            continue
        payload = float(mdef.get("cargo_payload_kg", 5300.0))
        soc = float(mdef.get("E_init_soc_frac", 0.8))
        weight = float(mdef.get("weight", 1.0))
        cfg, vehicle, context, masks = _prepare_one(
            vehicle_key=vehicle_key, od_id=od, payload=payload, soc=soc, q=q
        )
        mid = context["missions"][0].id
        prep = context["prepared"][mid]
        mask = masks[mid]["short"] if route_mode == "fixed" else masks[mid]["all"]
        sec = float(max_seconds) if max_seconds is not None else float(cfg.solver_max_seconds)
        mr = evaluate_mission_operational(
            prep=prep,
            cfg=cfg,
            installed=installed,
            mask=mask,
            vehicle=vehicle,
            fridge_path=FRIDGE,
            max_seconds=sec,
            max_expansions=cfg.solver_max_expansions,
        )
        row = dict(mr)
        row.update(
            {
                "tag": f"hos_rescore_{vehicle_key}",
                "vehicle_key": vehicle_key,
                "q": q,
                "budget": budget,
                "method_id": method_id,
                "installed": ",".join(sorted(installed)),
                "od_id": od,
                "weight": weight,
                "git_sha": SHA,
                "pipeline": "hos_in_search",
            }
        )
        mission_rows.append(row)
        w_tot += weight
        if mr.get("energy_feasible"):
            w_energy += weight
        if mr.get("operationally_served"):
            w_ops += weight
        print(
            f"  {method_id}|{budget}|{od}: ops={mr.get('operationally_served')} "
            f"energy={mr.get('energy_feasible')} audit={mr.get('hos_search_audit_only')} "
            f"pad={mr.get('hos_adjusted')} status={mr.get('status')}",
            flush=True,
        )
    return {
        "method_id": method_id,
        "route_mode": route_mode,
        "budget_name": budget,
        "installed": ",".join(sorted(installed)),
        "n_sites": len(installed),
        "energy_coverage": w_energy / w_tot if w_tot else 0.0,
        "operational_coverage": w_ops / w_tot if w_tot else 0.0,
        "mission_rows": mission_rows,
        "n_missions": len(mission_rows),
    }


def portfolio_rescore(
    budgets: tuple[str, ...] | None = None,
    vehicles: tuple[str, ...] = ("eactros_600", "volvo_475"),
) -> None:
    """Re-score frozen C/E/F (and B/D) site sets from legacy portfolio under HOS.

    Uses per-OD prep (cached) instead of 14-mission batch context.
    Default budgets: B0,B1,B2,B3,Ball (all). Pass subset via env STAGE_C_BUDGETS.
    """
    import os

    if budgets is None:
        env_b = os.environ.get("STAGE_C_BUDGETS", "").strip()
        budgets = (
            tuple(x.strip() for x in env_b.split(",") if x.strip())
            if env_b
            else ("B0", "B1", "B2", "B3", "Ball")
        )
    archives = sorted(ARCHIVE.glob("*/q2_critical_portfolio.csv")) if ARCHIVE.exists() else []
    if not archives:
        raise SystemExit("No archived portfolio — run --phase archive first")
    port = pd.read_csv(archives[-1])
    print(f"Using frozen sites from {archives[-1]}", flush=True)
    miss_path = archives[-1].parent / "q2_critical_missions.csv"
    mdf = pd.read_csv(miss_path) if miss_path.exists() else pd.DataFrame()

    orig = _patch_realistic_speed_policy()
    cov_rows: list[dict] = []
    mission_rows: list[dict] = []
    try:
        for vehicle_key in vehicles:
            gv = port[port.vehicle_key == vehicle_key]
            if gv.empty:
                continue
            for _, prow in gv.iterrows():
                budget = str(prow["budget"])
                if budget not in budgets:
                    continue
                conv_sites: set[str] = set()
                if not mdf.empty:
                    sub = mdf[
                        (mdf.vehicle_key == vehicle_key)
                        & (mdf.budget.astype(str) == budget)
                        & (mdf.method_id.astype(str).str.contains("B_fixed"))
                    ]
                    if not sub.empty:
                        conv_sites = _parse_sites(sub.iloc[0].get("installed"))
                specs = [
                    ("B_fixed_conventional", "fixed", conv_sites),
                    ("C_fixed_optimized", "fixed", _parse_sites(prow.get("C_sites"))),
                    ("D_multi_conventional", "multi", set(conv_sites)),
                    ("E_joint_multi_enum", "multi", _parse_sites(prow.get("E_sites"))),
                    ("F_greedy_multi", "multi", _parse_sites(prow.get("F_sites"))),
                ]
                method_ev: dict[str, dict] = {}
                for method_id, route_mode, installed in specs:
                    print(
                        f"[portfolio_rescore] {vehicle_key} {budget} {method_id} "
                        f"n={len(installed)} {sorted(installed)}",
                        flush=True,
                    )
                    ev = _eval_installed_on_panel(
                        vehicle_key=str(vehicle_key),
                        installed=installed,
                        route_mode=route_mode,
                        method_id=method_id,
                        budget=budget,
                        q=2,
                    )
                    method_ev[method_id] = ev
                    mission_rows.extend(ev["mission_rows"])

                def _ops(mid: str) -> float:
                    return float(method_ev[mid]["operational_coverage"])

                def _en(mid: str) -> float:
                    return float(method_ev[mid]["energy_coverage"])

                def _inst(mid: str) -> str:
                    return str(method_ev[mid].get("installed") or "")

                cov_rows.append(
                    {
                        "tag": f"hos_rescore_{vehicle_key}",
                        "vehicle_key": vehicle_key,
                        "q": 2,
                        "budget": budget,
                        "max_sites": prow.get("max_sites"),
                        "B_ops": _ops("B_fixed_conventional"),
                        "B_energy": _en("B_fixed_conventional"),
                        "C_ops": _ops("C_fixed_optimized"),
                        "C_energy": _en("C_fixed_optimized"),
                        "C_sites": _inst("C_fixed_optimized"),
                        "D_ops": _ops("D_multi_conventional"),
                        "D_energy": _en("D_multi_conventional"),
                        "E_ops": _ops("E_joint_multi_enum"),
                        "E_energy": _en("E_joint_multi_enum"),
                        "E_sites": _inst("E_joint_multi_enum"),
                        "F_ops": _ops("F_greedy_multi"),
                        "F_energy": _en("F_greedy_multi"),
                        "F_sites": _inst("F_greedy_multi"),
                        "E_equals_F_ops": abs(
                            _ops("E_joint_multi_enum") - _ops("F_greedy_multi")
                        )
                        < 1e-12,
                        "E_minus_C_ops": _ops("E_joint_multi_enum")
                        - _ops("C_fixed_optimized"),
                        "n_missions": 14,
                        "git_sha": SHA,
                        "pipeline": "hos_in_search_frozen_sites",
                        "selection_note": (
                            "site sets frozen from pre-HOS enum; "
                            "coverage re-scored under HOS-in-search"
                        ),
                    }
                )
                _write_csv(OUT / "q2_critical_portfolio_hos.csv", cov_rows)
                _write_csv(OUT / "q2_critical_missions_hos.csv", mission_rows)
                _write_csv(OUT / "q2_critical_portfolio.csv", cov_rows)
                _write_csv(OUT / "q2_critical_missions.csv", mission_rows)
    finally:
        import morocco_etruck.optimization.multiroute_placement_evaluation as mpe

        mpe.load_multiroute_pilot_config = orig

    write_efficiency_from_missions()
    print(
        f"portfolio_rescore done: {len(cov_rows)} portfolio rows, {len(mission_rows)} missions",
        flush=True,
    )


def ablation_live(budgets: tuple[str, ...] = ("B2",)) -> None:
    """Identical-site cross tables: multi@C, fixed@E, multi@E, fixed@C."""
    archives = sorted(ARCHIVE.glob("*/q2_critical_portfolio.csv")) if ARCHIVE.exists() else []
    site_src = (
        pd.read_csv(archives[-1])
        if archives
        else pd.read_csv(OUT / "q2_critical_portfolio.csv")
    )

    orig = _patch_realistic_speed_policy()
    rows: list[dict] = []
    try:
        for vehicle_key, gv in site_src.groupby("vehicle_key"):
            for _, prow in gv.iterrows():
                budget = str(prow["budget"])
                if budget not in budgets:
                    continue
                c_sites = _parse_sites(prow.get("C_sites"))
                e_sites = _parse_sites(prow.get("E_sites"))
                corners = {
                    "fixed_on_C": ("fixed", c_sites),
                    "multi_on_C": ("multi", c_sites),
                    "fixed_on_E": ("fixed", e_sites),
                    "multi_on_E": ("multi", e_sites),
                }
                corner_ev: dict[str, dict] = {}
                for name, (mode, sites) in corners.items():
                    print(
                        f"[ablation] {vehicle_key} {budget} {name} {sorted(sites)}",
                        flush=True,
                    )
                    corner_ev[name] = _eval_installed_on_panel(
                        vehicle_key=str(vehicle_key),
                        installed=sites,
                        route_mode=mode,
                        method_id=f"ablation_{name}",
                        budget=budget,
                        q=2,
                    )
                by_od: dict[str, dict[str, bool]] = {}
                for name, ev in corner_ev.items():
                    for mr in ev.get("mission_rows") or []:
                        od = str(mr.get("od_id") or mr.get("mission_id"))
                        by_od.setdefault(od, {})[name] = bool(mr.get("operationally_served"))
                for od, flags in sorted(by_od.items()):
                    rows.append(
                        {
                            "vehicle_key": vehicle_key,
                            "budget": budget,
                            "od_id": od,
                            "C_sites": ",".join(sorted(c_sites)),
                            "E_sites": ",".join(sorted(e_sites)),
                            "sites_differ": c_sites != e_sites,
                            "ops_fixed_on_C": flags.get("fixed_on_C"),
                            "ops_multi_on_C": flags.get("multi_on_C"),
                            "ops_fixed_on_E": flags.get("fixed_on_E"),
                            "ops_multi_on_E": flags.get("multi_on_E"),
                            "flexibility_effect_on_E": int(flags.get("multi_on_E", False))
                            - int(flags.get("fixed_on_E", False)),
                            "flexibility_effect_on_C": int(flags.get("multi_on_C", False))
                            - int(flags.get("fixed_on_C", False)),
                            "placement_effect_under_multi": int(
                                flags.get("multi_on_E", False)
                            )
                            - int(flags.get("multi_on_C", False)),
                            "placement_effect_under_fixed": int(
                                flags.get("fixed_on_E", False)
                            )
                            - int(flags.get("fixed_on_C", False)),
                            "delta_E_multi_minus_C_fixed": int(
                                flags.get("multi_on_E", False)
                            )
                            - int(flags.get("fixed_on_C", False)),
                            "git_sha": SHA,
                            "pipeline": "hos_in_search",
                        }
                    )
                _write_csv(OUT / "placement_flexibility_ablation.csv", rows)
    finally:
        import morocco_etruck.optimization.multiroute_placement_evaluation as mpe

        mpe.load_multiroute_pilot_config = orig
    print(f"ablation_live rows={len(rows)}", flush=True)


def q1_boundary() -> None:
    """Re-evaluate flip / near-reserve cells at q=1 under HOS-in-search."""
    flip_path = OUT / "q_resolution_flip_inventory.csv"
    if not flip_path.exists():
        print("No flip inventory — skip q1", flush=True)
        return
    flips = pd.read_csv(flip_path)
    # Deduplicate by vehicle/od/payload/soc/infra
    flips = flips.drop_duplicates(
        subset=["vehicle_key", "od_id", "payload_kg", "soc_frac", "infra_label"]
    )
    # Map infra_label -> installed via confirm or frontier
    confirm = (
        pd.read_csv(OUT / "payload_soc_frontier_q2_confirm.csv")
        if (OUT / "payload_soc_frontier_q2_confirm.csv").exists()
        else pd.DataFrame()
    )
    frontier = (
        pd.read_csv(OUT / "payload_soc_frontier.csv")
        if (OUT / "payload_soc_frontier.csv").exists()
        else pd.DataFrame()
    )

    def _installed_for(r) -> set[str]:
        for df in (confirm, frontier):
            if df.empty:
                continue
            hit = df[
                (df.vehicle_key == r.vehicle_key)
                & (df.od_id == r.od_id)
                & (df.payload_kg == float(r.payload_kg))
                & (df.soc_frac == float(r.soc_frac))
                & (df.infra_label == r.infra_label)
            ]
            if not hit.empty and "installed" in hit.columns:
                return _parse_sites(hit.iloc[0]["installed"])
        # Fallback ladders
        lab = str(r.infra_label)
        if "benguerir_ac" in lab and "pair" not in lab:
            return {"y_benguerir_ac"}
        if "benguerir_pair" in lab:
            return {"y_benguerir_ac", "y_benguerir_ca"}
        if lab == "all_ac":
            return {"y_settat_ac", "y_benguerir_ac", "y_amskroud_ca"}
        if "larache" in lab:
            return {"y_larache_rt"}
        if "assilah" in lab:
            return {"y_assilah_tr"}
        if "bouznika_rc" in lab:
            return {"y_bouznika_rc"}
        return set()

    orig = _patch_realistic_speed_policy()
    rows: list[dict] = []
    try:
        for _, r in flips.iterrows():
            installed = _installed_for(r)
            cfg_path = _temp_demand_cfg(str(r.od_id), float(r.payload_kg), float(r.soc_frac))
            cfg = load_multiroute_placement_config(cfg_path, root=ROOT)
            vpath = VEHICLES[str(r.vehicle_key)]
            vehicle = load_vehicle(vpath)
            print(
                f"[q1] {r.vehicle_key} {r.od_id} p={r.payload_kg} soc={r.soc_frac} "
                f"{r.infra_label} sites={sorted(installed)}",
                flush=True,
            )
            t0 = time.perf_counter()
            context = prepare_multiroute_placement_context(
                cfg,
                root=ROOT,
                demand_name="frontier_cell",
                energy_quantum_kwh=1,
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
            mid = context["missions"][0].id
            prep = context["prepared"][mid]
            mr = evaluate_mission_operational(
                prep=prep,
                cfg=cfg,
                installed=installed,
                mask=masks[mid]["all"],
                vehicle=vehicle,
                fridge_path=FRIDGE,
                max_seconds=cfg.solver_max_seconds,
                max_expansions=cfg.solver_max_expansions,
            )
            fr = evaluate_mission_operational(
                prep=prep,
                cfg=cfg,
                installed=installed,
                mask=masks[mid]["short"],
                vehicle=vehicle,
                fridge_path=FRIDGE,
                max_seconds=cfg.solver_max_seconds,
                max_expansions=cfg.solver_max_expansions,
            )
            rows.append(
                {
                    "vehicle_key": r.vehicle_key,
                    "od_id": r.od_id,
                    "payload_kg": float(r.payload_kg),
                    "soc_frac": float(r.soc_frac),
                    "infra_label": r.infra_label,
                    "installed": ",".join(sorted(installed)),
                    "multi_q5": r.get("multi_q5"),
                    "multi_q2": r.get("multi_q2"),
                    "fixed_q5": r.get("fixed_q5"),
                    "fixed_q2": r.get("fixed_q2"),
                    "flex_q5": r.get("flex_q5"),
                    "flex_q2": r.get("flex_q2"),
                    "flip_multi": r.get("flip_multi"),
                    "flip_fixed": r.get("flip_fixed"),
                    "flip_flex": r.get("flip_flex"),
                    "multi_min_soc_q2": r.get("multi_min_soc"),
                    "near_reserve": r.get("near_reserve"),
                    "q1_status": "done",
                    "q1_multi_ops": bool(mr.get("operationally_served")),
                    "q1_fixed_ops": bool(fr.get("operationally_served")),
                    "q1_multi_min_soc": mr.get("min_soc"),
                    "q1_hos_audit_only": mr.get("hos_search_audit_only"),
                    "q1_wall_sec": round(time.perf_counter() - t0, 2),
                    "git_sha": SHA,
                    "note": "q=1 boundary under HOS-in-search",
                }
            )
            _write_csv(OUT / "q1_boundary_refinement.csv", rows)
            print(
                f"  -> multi={rows[-1]['q1_multi_ops']} fixed={rows[-1]['q1_fixed_ops']} "
                f"sec={rows[-1]['q1_wall_sec']}",
                flush=True,
            )
    finally:
        import morocco_etruck.optimization.multiroute_placement_evaluation as mpe

        mpe.load_multiroute_pilot_config = orig
    print(f"q1_boundary done n={len(rows)}", flush=True)


def blind_greedy(budgets: tuple[str, ...] = ("B0", "B2")) -> None:
    """Greedy that evaluates trial subsets live (no enum_cache oracle)."""
    orig = _patch_realistic_speed_policy()
    rows: list[dict] = []
    try:
        for vehicle_key in ("eactros_600",):
            sites = list(FULL_SITE_IDS)
            empty = _eval_installed_on_panel(
                vehicle_key=vehicle_key,
                installed=set(),
                route_mode="multi",
                method_id="blind_empty",
                budget="B0",
                q=2,
            )
            for bname, nmax in [("B0", 0), ("B1", 1), ("B2", 2)]:
                if bname not in budgets:
                    continue
                t0 = time.perf_counter()
                chosen: set[str] = set()
                best_ev = empty
                remaining = set(sites)
                while remaining and len(chosen) < nmax:
                    ranked = []
                    for s in sorted(remaining):
                        trial = chosen | {s}
                        print(f"[blind_greedy] trial {sorted(trial)}", flush=True)
                        ev = _eval_installed_on_panel(
                            vehicle_key=vehicle_key,
                            installed=trial,
                            route_mode="multi",
                            method_id="blind_trial",
                            budget=bname,
                            q=2,
                        )
                        ranked.append((trial, ev))
                        print(
                            f"  ops={ev['operational_coverage']:.3f}",
                            flush=True,
                        )
                    ranked.sort(key=lambda x: _score(x[1]), reverse=True)
                    trial, ev = ranked[0]
                    if float(ev["operational_coverage"]) > float(
                        best_ev["operational_coverage"]
                    ) + 1e-12:
                        chosen = set(trial)
                        best_ev = ev
                        remaining = set(sites) - chosen
                    else:
                        break
                port = pd.read_csv(OUT / "q2_critical_portfolio.csv")
                er = port[
                    (port.vehicle_key == vehicle_key) & (port.budget.astype(str) == bname)
                ]
                e_ops = float(er.iloc[0]["E_ops"]) if not er.empty else None
                e_sites = str(er.iloc[0]["E_sites"]) if not er.empty else ""
                rows.append(
                    {
                        "vehicle_key": vehicle_key,
                        "budget": bname,
                        "blind_ops": float(best_ev["operational_coverage"]),
                        "blind_energy": float(best_ev["energy_coverage"]),
                        "blind_sites": ",".join(sorted(chosen)),
                        "E_ops_reference": e_ops,
                        "E_sites_reference": e_sites,
                        "matches_E_ops": e_ops is not None
                        and abs(float(best_ev["operational_coverage"]) - e_ops) < 1e-12,
                        "wall_sec": round(time.perf_counter() - t0, 2),
                        "selection_engine": "blind_greedy_live_eval",
                        "git_sha": SHA,
                    }
                )
                _write_csv(OUT / "blind_greedy_vs_enum.csv", rows)
                print(f"  {bname} blind={rows[-1]['blind_ops']} E_ref={e_ops}", flush=True)
    finally:
        import morocco_etruck.optimization.multiroute_placement_evaluation as mpe

        mpe.load_multiroute_pilot_config = orig
    print(f"blind_greedy done n={len(rows)}", flush=True)


def larger_instance() -> None:
    """Certification row for denser path-union / more candidates (path_union k=3 if available)."""
    rows = []
    # Baseline: 9-site full enum status from hos portfolio if present
    port = OUT / "q2_critical_portfolio.csv"
    if port.exists():
        df = pd.read_csv(port)
        for vehicle_key, gv in df.groupby("vehicle_key"):
            for _, r in gv.iterrows():
                rows.append(
                    {
                        "instance_id": f"national9_{vehicle_key}_{r.budget}",
                        "vehicle_key": vehicle_key,
                        "budget": r.budget,
                        "n_candidates": 9,
                        "n_missions": r.get("n_missions", 14),
                        "method": "E_joint_multi_enum",
                        "status": (
                            "optimal_frozen_sites_rescored"
                            if str(r.get("pipeline", "")).startswith("hos")
                            else "optimal_legacy_enum"
                        ),
                        "ops_coverage": r.get("E_ops"),
                        "certification": "full_enum_pre_hos_sites;_hos_rescore"
                        if "hos" in str(r.get("pipeline", ""))
                        else "exhaustive_enum",
                        "git_sha": SHA,
                    }
                )
    # Larger: evaluate Ball conventional vs all-9 under multi once as non-enum baseline
    orig = _patch_realistic_speed_policy()
    try:
        for vehicle_key in ("eactros_600",):
            cfg, vehicle, context, masks = _prepare_corridor(vehicle_key, q=2)
            t0 = time.perf_counter()
            # denser mask: use all arcs already in multi mask (path union as built)
            ev = evaluate_subset(
                context=context,
                cfg=cfg,
                installed=set(FULL_SITE_IDS),
                route_mode="multi",
                masks=masks,
                method_id="larger_all9_multi",
                budget_name="Ball",
                vehicle=vehicle,
                fridge_path=FRIDGE,
            )
            rows.append(
                {
                    "instance_id": f"national9_allsites_{vehicle_key}",
                    "vehicle_key": vehicle_key,
                    "budget": "Ball",
                    "n_candidates": 9,
                    "n_missions": len(context["missions"]),
                    "method": "evaluate_all_sites_multi",
                    "status": "feasible_evaluated",
                    "ops_coverage": ev["operational_coverage"],
                    "wall_sec": round(time.perf_counter() - t0, 2),
                    "certification": "not_enum;_single_full_install_eval",
                    "git_sha": SHA,
                }
            )
            # Synthetic larger candidate count marker (path alternatives already unioned)
            rows.append(
                {
                    "instance_id": f"path_union_dense_{vehicle_key}",
                    "vehicle_key": vehicle_key,
                    "budget": "B2",
                    "n_candidates": 9,
                    "n_missions": len(context["missions"]),
                    "method": "blind_greedy_reference",
                    "status": "see_blind_greedy_vs_enum.csv",
                    "ops_coverage": None,
                    "certification": "compare_blind_vs_enum_on_B2;_enum_expensive_at_2n_sites",
                    "git_sha": SHA,
                    "note": "Larger than 9 directional sites deferred; B2 blind greedy is the compute-stressed contrast",
                }
            )
    finally:
        import morocco_etruck.optimization.multiroute_placement_evaluation as mpe

        mpe.load_multiroute_pilot_config = orig

    # Merge with prior certification table shape
    cert_rows = []
    if (OUT / "q2_critical_missions.csv").exists():
        m = pd.read_csv(OUT / "q2_critical_missions.csv")
        for (vehicle_key, budget, method_id), g in m.groupby(
            ["vehicle_key", "budget", "method_id"]
        ):
            n_opt = int(
                g["status"].astype(str).str.upper().eq("OPTIMAL").sum()
                if "status" in g.columns
                else g.get("operationally_served", pd.Series(dtype=bool)).astype(bool).sum()
            )
            cert_rows.append(
                {
                    "vehicle_key": vehicle_key,
                    "budget": budget,
                    "method_id": method_id,
                    "n_missions": len(g),
                    "n_optimal": n_opt,
                    "mean_solve_sec": float(g["solve_sec"].mean())
                    if "solve_sec" in g.columns
                    else None,
                    "certification": "hos_in_search_mission_eval",
                    "git_sha": SHA,
                }
            )
    _write_csv(OUT / "solver_certification_table.csv", cert_rows)
    _write_csv(OUT / "solver_larger_instance_table.csv", rows)
    print(f"larger_instance cert={len(cert_rows)} larger={len(rows)}", flush=True)


def stability_summary() -> None:
    rows = [
        {
            "claim": "eActros_B2_E_minus_C_plus1",
            "stable_under_current_pipeline": True,
            "stable_under_hos_in_search": "see_q2_critical_portfolio.csv",
            "notes": "confounded by directional Benguerir; use ablation placement vs flex columns",
        },
        {
            "claim": "AC_15t_soc08_requires_soc10",
            "stable_under_current_pipeline": False,
            "stable_under_hos_in_search": "see_q1_boundary_refinement.csv",
            "notes": "q5 unserved / q2 served eActros; not a categorical physical limit",
        },
        {
            "claim": "flex_gains_soc80_six_cells",
            "stable_under_current_pipeline": False,
            "stable_under_hos_in_search": "see_payload_soc_frontier_q2_confirm.csv",
            "notes": "only 2 retain flex at q2 (survives_q2_flex)",
        },
        {
            "claim": "F_matches_E_at_lower_compute",
            "stable_under_current_pipeline": False,
            "stable_under_hos_in_search": "see_blind_greedy_vs_enum.csv",
            "notes": "F greedy-over-enum is not independent; blind greedy is the compute claim test",
        },
        {
            "claim": "hos_audit_only_no_post_pad",
            "stable_under_current_pipeline": False,
            "stable_under_hos_in_search": "see_q2_critical_missions.csv hos_search_audit_only",
            "notes": "Stage B acceptance; ops-true rows should be audit-only under HOS-in-search",
        },
    ]
    _write_csv(OUT / "uncertainty_stability_summary.csv", rows)
    print("stability_summary written", flush=True)


def retry_limit_reached(
    max_seconds: float = 600.0,
    *,
    method_substr: str = "E_joint",
    budgets: tuple[str, ...] = ("B2", "Ball"),
) -> None:
    """Re-solve priority LIMIT_REACHED rows with a higher wall-clock budget.

    Default focuses on E_joint at B2/Ball (headline claims). Full sweep:
    method_substr='' budgets=all.
    """
    path = OUT / "q2_critical_missions.csv"
    if not path.exists():
        print("No missions CSV — skip retry_limits", flush=True)
        return
    m = pd.read_csv(path)
    lim = m[m.status.astype(str).str.upper() == "LIMIT_REACHED"].copy()
    if method_substr:
        lim = lim[lim.method_id.astype(str).str.contains(method_substr)]
    if budgets:
        lim = lim[lim.budget.astype(str).isin(budgets)]
    if lim.empty:
        print("No LIMIT_REACHED rows in filter", flush=True)
        return
    print(
        f"[retry_limits] n={len(lim)} max_seconds={max_seconds} "
        f"filter method~{method_substr!r} budgets={budgets}",
        flush=True,
    )
    orig = _patch_realistic_speed_policy()
    updates: list[tuple[int, dict]] = []
    try:
        for idx, row in lim.iterrows():
            vehicle_key = str(row["vehicle_key"])
            od = str(row["od_id"])
            installed = _parse_sites(row.get("installed"))
            method_id = str(row["method_id"])
            route_mode = "fixed" if "fixed" in method_id.lower() or method_id.startswith(
                "B_"
            ) or method_id.startswith("C_") else "multi"
            if method_id.startswith("D_") or "multi" in method_id.lower():
                route_mode = "multi"
            if method_id.startswith("B_") or method_id.startswith("C_"):
                route_mode = "fixed"
            # Recover payload/soc from corridor def
            mdef = next(x for x in _corridor_missions() if str(x["od_id"]) == od)
            payload = float(mdef.get("cargo_payload_kg", 5300.0))
            soc = float(mdef.get("E_init_soc_frac", 0.8))
            cfg, vehicle, context, masks = _prepare_one(
                vehicle_key=vehicle_key, od_id=od, payload=payload, soc=soc, q=2
            )
            mid = context["missions"][0].id
            prep = context["prepared"][mid]
            mask = masks[mid]["short"] if route_mode == "fixed" else masks[mid]["all"]
            print(
                f"  retry {vehicle_key} {row.get('budget')} {method_id} {od} "
                f"sites={sorted(installed)} mode={route_mode}",
                flush=True,
            )
            mr = evaluate_mission_operational(
                prep=prep,
                cfg=cfg,
                installed=installed,
                mask=mask,
                vehicle=vehicle,
                fridge_path=FRIDGE,
                max_seconds=max_seconds,
                max_expansions=max(int(cfg.solver_max_expansions), 500000),
            )
            print(
                f"  -> status={mr.get('status')} ops={mr.get('operationally_served')} "
                f"audit={mr.get('hos_search_audit_only')}",
                flush=True,
            )
            updates.append((idx, mr))
    finally:
        import morocco_etruck.optimization.multiroute_placement_evaluation as mpe

        mpe.load_multiroute_pilot_config = orig

    for idx, mr in updates:
        for k, v in mr.items():
            if k in m.columns:
                m.at[idx, k] = v
        m.at[idx, "limit_retry_max_seconds"] = max_seconds
        m.at[idx, "git_sha"] = SHA
        m.at[idx, "pipeline"] = "hos_in_search_limit_retry"
    m.to_csv(path, index=False)
    # Rebuild portfolio coverages from updated missions
    cov_rows = []
    for (vehicle_key, budget), g in m.groupby(["vehicle_key", "budget"]):
        def _cov(method_substr: str, route_hint: str | None = None) -> tuple[float, float, str]:
            sub = g[g.method_id.astype(str).str.contains(method_substr)]
            if sub.empty:
                return 0.0, 0.0, ""
            ops = sub["operationally_served"].astype(str).str.lower().isin(["true", "1"]).mean()
            en = sub["energy_feasible"].astype(str).str.lower().isin(["true", "1"]).mean()
            inst = str(sub.iloc[0].get("installed") or "")
            return float(ops), float(en), inst

        b_ops, b_en, _ = _cov("B_fixed")
        c_ops, c_en, c_sites = _cov("C_fixed")
        d_ops, d_en, _ = _cov("D_multi")
        e_ops, e_en, e_sites = _cov("E_joint")
        f_ops, f_en, f_sites = _cov("F_greedy")
        cov_rows.append(
            {
                "tag": f"hos_rescore_{vehicle_key}",
                "vehicle_key": vehicle_key,
                "q": 2,
                "budget": budget,
                "B_ops": b_ops,
                "B_energy": b_en,
                "C_ops": c_ops,
                "C_energy": c_en,
                "C_sites": c_sites,
                "D_ops": d_ops,
                "D_energy": d_en,
                "E_ops": e_ops,
                "E_energy": e_en,
                "E_sites": e_sites,
                "F_ops": f_ops,
                "F_energy": f_en,
                "F_sites": f_sites,
                "E_equals_F_ops": abs(e_ops - f_ops) < 1e-12,
                "E_minus_C_ops": e_ops - c_ops,
                "n_missions": 14,
                "n_limit_reached": int(
                    (g.status.astype(str).str.upper() == "LIMIT_REACHED").sum()
                ),
                "git_sha": SHA,
                "pipeline": "hos_in_search_frozen_sites_limit_retry",
            }
        )
    _write_csv(OUT / "q2_critical_portfolio.csv", cov_rows)
    _write_csv(OUT / "q2_critical_portfolio_hos.csv", cov_rows)
    print(
        f"retry_limits done; remaining LIMIT_REACHED="
        f"{(m.status.astype(str).str.upper()=='LIMIT_REACHED').sum()}",
        flush=True,
    )


def mini_panel() -> None:
    """Frozen mini panel: B0/B2/Ball × both vehicles; assert ops => audit-only."""
    port = pd.read_csv(OUT / "q2_critical_portfolio.csv")
    miss = pd.read_csv(OUT / "q2_critical_missions.csv")
    rows = []
    for vehicle_key in ("eactros_600", "volvo_475"):
        for budget in ("B0", "B2", "Ball"):
            sub = miss[
                (miss.vehicle_key == vehicle_key)
                & (miss.budget.astype(str) == budget)
                & (miss.method_id.astype(str).str.contains("E_joint"))
            ]
            if sub.empty:
                continue
            ops = sub[sub.operationally_served.astype(str).str.lower().isin(["true", "1"])]
            audit = (
                ops["hos_search_audit_only"].astype(str).str.lower().isin(["true", "1"]).all()
                if "hos_search_audit_only" in ops.columns and len(ops)
                else None
            )
            pad = (
                (ops["hos_adjusted"].astype(str).str.lower().isin(["true", "1"]).sum() == 0)
                if "hos_adjusted" in ops.columns and len(ops)
                else None
            )
            rows.append(
                {
                    "vehicle_key": vehicle_key,
                    "budget": budget,
                    "n_missions": len(sub),
                    "n_ops_true": len(ops),
                    "all_ops_audit_only": audit,
                    "no_post_pad_on_ops_true": pad,
                    "git_sha": SHA,
                }
            )
    _write_csv(OUT / "hos_mini_panel_gate.csv", rows)
    print("mini_panel", rows, flush=True)


def headline_enum() -> None:
    """Full exhaustive A–F under HOS (slow). Uses hos-tagged cache file names."""
    # Monkeypatch cache tag via temporary wrapper
    import run_paper_scientific_results_campaign as camp

    _orig = camp._run_af_portfolio

    def _run_hos(**kwargs):
        tag = kwargs.get("tag", "q2_headline")
        if not str(tag).endswith("_hos"):
            kwargs["tag"] = f"{tag}_hos"
        return _orig(**kwargs)

    camp._run_af_portfolio = _run_hos  # type: ignore
    try:
        all_cov: list[dict] = []
        all_m: list[dict] = []
        for veh in ("eactros_600", "volvo_475"):
            cov, missions, _tr = camp._run_af_portfolio(
                cfg_path=CFG_HEADLINE,
                demand_name="corridor_eactros_equal",
                q=2,
                vehicle_key=veh,
                site_ids=list(FULL_SITE_IDS),
                tag=f"q2_headline_{veh}_hos",
            )
            for r in cov:
                r["pipeline"] = "hos_in_search_full_enum"
                r["git_sha"] = SHA
            for r in missions:
                r["pipeline"] = "hos_in_search_full_enum"
                r["git_sha"] = SHA
            all_cov.extend(cov)
            all_m.extend(missions)
            _write_csv(OUT / "q2_critical_portfolio.csv", all_cov)
            _write_csv(OUT / "q2_critical_missions.csv", all_m)
    finally:
        camp._run_af_portfolio = _orig  # type: ignore
    write_efficiency_from_missions()
    print("headline_enum complete", flush=True)


def write_manifest() -> None:
    files = sorted(
        p for p in OUT.glob("*") if p.is_file() and p.suffix in {".csv", ".json", ".md"}
    )
    payload = {
        "git_sha": SHA,
        "pipeline": "hos_in_search_stage_c",
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "files": {},
    }
    for p in files:
        if p.name == "campaign_manifest.json":
            continue
        h = __import__("hashlib").sha256(p.read_bytes()).hexdigest()
        payload["files"][p.name] = {"sha256": h, "bytes": p.stat().st_size}
    # Hash after excluding self
    out = OUT / "campaign_manifest.json"
    text = json.dumps(payload, indent=2, sort_keys=True)
    out.write_text(text, encoding="utf-8")
    # Re-hash including manifest content without self-reference loop: store content hash separately
    payload["manifest_sha256"] = __import__("hashlib").sha256(text.encode()).hexdigest()
    out.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    print(f"manifest -> {out}", flush=True)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--phase",
        default="all_fast",
        choices=[
            "archive",
            "portfolio_rescore",
            "ablation_live",
            "q1_boundary",
            "blind_greedy",
            "retry_limits",
            "larger_instance",
            "stability",
            "mini_panel",
            "headline_enum",
            "manifest",
            "report",
            "all_fast",
            "all",
            "post_portfolio",
        ],
    )
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    phase = args.phase
    if phase in ("archive", "all_fast", "all"):
        archive_pre_hos()
    if phase in ("portfolio_rescore", "all_fast", "all"):
        portfolio_rescore()
    if phase in ("retry_limits", "post_portfolio", "all_fast", "all"):
        retry_limit_reached()
    if phase in ("ablation_live", "post_portfolio", "all_fast", "all"):
        ablation_live()
    if phase in ("q1_boundary", "post_portfolio", "all_fast", "all"):
        q1_boundary()
    if phase in ("blind_greedy", "post_portfolio", "all_fast", "all"):
        blind_greedy(budgets=("B0", "B2"))
    if phase in ("larger_instance", "post_portfolio", "all_fast", "all"):
        larger_instance()
    if phase in ("stability", "post_portfolio", "all_fast", "all"):
        stability_summary()
    if phase in ("mini_panel", "post_portfolio", "all_fast", "all"):
        mini_panel()
    if phase in ("headline_enum", "all"):
        headline_enum()
    if phase in ("manifest", "post_portfolio", "all_fast", "all"):
        write_manifest()
    if phase in ("report", "post_portfolio", "all_fast", "all"):
        write_report()


if __name__ == "__main__":
    main()
