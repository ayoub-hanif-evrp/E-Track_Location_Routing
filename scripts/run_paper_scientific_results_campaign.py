#!/usr/bin/env python
"""Paper scientific results campaign — experiments over planning docs.

Phases:
  audit | q2_headline | frontier | amskroud | compare | efficiency | figures | report | all

Primary metric: operational coverage (energy + continuous replay + HOS/schedule).
Writes ONLY under results/paper_campaign/ and reports/PAPER_SCIENTIFIC_RESULTS_CAMPAIGN.md.
"""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
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
sys.path.insert(0, str(ROOT / "scripts"))

from run_final_operational_correction import (  # noqa: E402
    _score,
    evaluate_mission_operational,
    evaluate_subset,
)
from run_high_impact_completion import _scaled_vehicle_yaml  # noqa: E402
from run_high_impact_realism_sprint import (  # noqa: E402
    FRIDGE,
    ROAD_CENTS,
    VEHICLES,
    _mission_masks,
    _patch_realistic_speed_policy,
    _write_csv,
)
from morocco_etruck.energy.vehicle import load_vehicle  # noqa: E402
from morocco_etruck.optimization.multiroute_adapter import (  # noqa: E402
    load_multiroute_pilot_config,
)
from morocco_etruck.optimization.multiroute_placement import (  # noqa: E402
    load_multiroute_placement_config,
)
from morocco_etruck.optimization.multiroute_placement_evaluation import (  # noqa: E402
    prepare_multiroute_placement_context,
)

OUT = ROOT / "results/paper_campaign"
CFG_PAPER = ROOT / "configs/optimization/paper_scientific_portfolio.yaml"
CFG_HEADLINE = ROOT / "configs/optimization/multiroute_placement_corridor_portfolio.yaml"
OUT_MD = ROOT / "reports/PAPER_SCIENTIFIC_RESULTS_CAMPAIGN.md"

# Full paper frontier (no lean cuts). DEM-complete ODs only; Oujda incomplete excluded.
PAYLOADS = [5300.0, 10000.0, 15000.0]
SOCS = [0.5, 0.8, 1.0]
RESERVES_SCREEN = [0.10]
CHARGING_MODEL = "ccs_soc_taper_research_envelope"
FULL_SITE_IDS = [
    "y_settat_ca",
    "y_benguerir_ca",
    "y_amskroud_ca",
    "y_settat_ac",
    "y_benguerir_ac",
    "y_bouznika_cr",
    "y_bouznika_rc",
    "y_larache_rt",
    "y_assilah_tr",
]
FRONTIER_ODS = [
    "agadir_casa",
    "agadir_marrakech",
    "marrakech_casa",
    "casa_agadir",
    "casa_marrakech",
    "marrakech_agadir",
    "tangier_casa",
    "casa_tangier",
    "casa_rabat",
    "rabat_casa",
    "rabat_fes",
    "fes_rabat",
    "tangier_rabat",
    "rabat_tangier",
]
INFRA_LADDERS = {
    "agadir_casa": [
        ("none", frozenset()),
        ("opt1_benguerir_ac", frozenset(["y_benguerir_ac"])),
        ("opt2_benguerir_pair", frozenset(["y_benguerir_ac", "y_settat_ac"])),
        ("all_ac", frozenset(["y_benguerir_ac", "y_settat_ac"])),
    ],
    "agadir_marrakech": [
        ("none", frozenset()),  # no direction-compatible ADM attach on union
    ],
    "marrakech_casa": [
        ("none", frozenset()),
        ("opt1_benguerir_ac", frozenset(["y_benguerir_ac"])),
        ("opt2_benguerir_settat_ac", frozenset(["y_benguerir_ac", "y_settat_ac"])),
    ],
    "casa_marrakech": [
        ("none", frozenset()),
        ("opt1_settat_ca", frozenset(["y_settat_ca"])),
        ("opt1_benguerir_ca", frozenset(["y_benguerir_ca"])),
        ("opt2_settat_benguerir", frozenset(["y_settat_ca", "y_benguerir_ca"])),
        ("with_amskroud", frozenset(["y_settat_ca", "y_benguerir_ca", "y_amskroud_ca"])),
    ],
    "casa_agadir": [
        ("none", frozenset()),
        ("opt1_benguerir_ca", frozenset(["y_benguerir_ca"])),
        ("opt2_settat_benguerir", frozenset(["y_settat_ca", "y_benguerir_ca"])),
        ("with_amskroud", frozenset(["y_settat_ca", "y_benguerir_ca", "y_amskroud_ca"])),
    ],
    "marrakech_agadir": [
        ("none", frozenset()),
        ("amskroud_only", frozenset(["y_amskroud_ca"])),
        ("with_amskroud_settat", frozenset(["y_amskroud_ca", "y_settat_ca"])),
    ],
    "tangier_casa": [
        ("none", frozenset()),
        ("opt1_assilah", frozenset(["y_assilah_tr"])),
        ("opt1_bouznika_rc", frozenset(["y_bouznika_rc"])),
        ("opt2_assilah_bouznika", frozenset(["y_assilah_tr", "y_bouznika_rc"])),
    ],
    "casa_tangier": [
        ("none", frozenset()),
        ("opt1_bouznika_cr", frozenset(["y_bouznika_cr"])),
        ("opt1_larache", frozenset(["y_larache_rt"])),
        ("opt2_bouznika_larache", frozenset(["y_bouznika_cr", "y_larache_rt"])),
    ],
    "casa_rabat": [
        ("none", frozenset()),
        ("opt1_bouznika_cr", frozenset(["y_bouznika_cr"])),
    ],
    "rabat_casa": [
        ("none", frozenset()),
        ("opt1_bouznika_rc", frozenset(["y_bouznika_rc"])),
    ],
    "rabat_fes": [("none", frozenset())],
    "fes_rabat": [("none", frozenset())],
    "tangier_rabat": [
        ("none", frozenset()),
        ("opt1_assilah", frozenset(["y_assilah_tr"])),
    ],
    "rabat_tangier": [
        ("none", frozenset()),
        ("opt1_larache", frozenset(["y_larache_rt"])),
    ],
}


def _git_sha() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip()
    except Exception:  # noqa: BLE001
        return "unknown"


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest() if p.exists() else ""


def freeze_registry() -> Path:
    OUT.mkdir(parents=True, exist_ok=True)
    rows = []
    # Frontier cells
    for veh in VEHICLES:
        for od in FRONTIER_ODS:
            for payload in PAYLOADS:
                for soc in SOCS:
                    for ladder_name, sites in INFRA_LADDERS[od]:
                        rows.append(
                            {
                                "cell_family": "frontier",
                                "vehicle_key": veh,
                                "od_id": od,
                                "payload_kg": payload,
                                "soc_frac": soc,
                                "reserve": 0.10,
                                "infra_label": ladder_name,
                                "n_sites": len(sites),
                                "installed": ",".join(sorted(sites)),
                                "route_mode": "multi",
                                "q_screen": 5,
                                "q_confirm": 2,
                                "frozen_before_solve": True,
                                "git_sha": _git_sha(),
                            }
                        )
    # Headline q2
    for veh in VEHICLES:
        rows.append(
            {
                "cell_family": "q2_headline",
                "vehicle_key": veh,
                "od_id": "portfolio_3",
                "payload_kg": 5300.0,
                "soc_frac": "mixed_headline",
                "reserve": 0.10,
                "infra_label": "A_F_budgets",
                "n_sites": "",
                "installed": "",
                "route_mode": "A_F",
                "q_screen": 2,
                "q_confirm": 2,
                "frozen_before_solve": True,
                "git_sha": _git_sha(),
            }
        )
    path = OUT / "scenario_registry_frozen.csv"
    _write_csv(path, rows)
    print("Froze", path, "n=", len(rows), flush=True)
    return path


def audit_dem_and_sites() -> pd.DataFrame:
    """Confirm dem_complete and Amskroud on-union attach for each OD."""
    OUT.mkdir(parents=True, exist_ok=True)
    orig = _patch_realistic_speed_policy()
    rows = []
    try:
        cfg = load_multiroute_placement_config(CFG_PAPER, root=ROOT)
        # Build a temporary demand with one mission per OD at light/SOC0.8
        demand = {
            "note": "DEM audit only",
            "missions": [],
        }
        ods = list(FRONTIER_ODS)
        for od in ods:
            demand["missions"].append(
                {
                    "id": f"audit_{od}",
                    "od_id": od,
                    "weight": 1.0,
                    "E_truck_init": 0,
                    "E_init_soc_frac": 0.8,
                    "refrigeration_on": True,
                    "terrain_mode": "dem",
                    "weather_id": "cool",
                    "gcm": "light",
                    "cargo_payload_kg": 5300.0,
                }
            )
        with tempfile.TemporaryDirectory() as td:
            tdir = Path(td)
            cfg_path = tdir / "audit_cfg.yaml"
            raw = yaml.safe_load(CFG_PAPER.read_text(encoding="utf-8"))
            raw["demand_scenarios"] = {"audit_all_ods": demand}
            cfg_path.write_text(yaml.safe_dump(raw), encoding="utf-8")
            cfg = load_multiroute_placement_config(cfg_path, root=ROOT)
            vpath = VEHICLES["eactros_600"]
            context = prepare_multiroute_placement_context(
                cfg,
                root=ROOT,
                demand_name="audit_all_ods",
                energy_quantum_kwh=5,
                objective_mode="enroute_incremental_cost",
                vehicle_yaml=vpath,
                road_cost_per_km=ROAD_CENTS,
                fridge_yaml=FRIDGE,
                charger_power_kw=350.0,
                max_alternatives_for_union=2,
            )
            for m in context["missions"]:
                prep = context["prepared"][m.id]
                ctx = prep.ctx
                st = getattr(prep.template, "stations", {}) or {}
                keys = sorted(str(k) for k in (st.keys() if isinstance(st, dict) else st))
                amsk_on = any("amskroud_ca" == k for k in keys)
                rows.append(
                    {
                        "od_id": m.od_id,
                        "dem_complete": bool(getattr(ctx, "dem_complete", False)),
                        "terrain_mode": getattr(ctx, "terrain_mode", None),
                        "n_arcs": len(getattr(ctx, "arcs", []) or getattr(prep.template, "arcs", []) or []),
                        "station_keys_on_union": ",".join(keys),
                        "amskroud_ca_on_union": amsk_on,
                        "serviceability": context.get("serviceability"),
                        "git_sha": _git_sha(),
                        "note": "DEM recovered for marrakech_casa/agadir_marrakech via COP-DEM GLO-30 on verified OSM macros",
                    }
                )
                print(
                    f"AUDIT {m.od_id}: dem_complete={rows[-1]['dem_complete']} "
                    f"amsk_on_union={amsk_on} stations={keys}",
                    flush=True,
                )
    finally:
        if orig is not None:
            # restore patch if helper returns previous
            pass
    df = pd.DataFrame(rows)
    _write_csv(OUT / "od_dem_site_audit.csv", rows)
    return df


def _run_af_portfolio(
    *,
    cfg_path: Path,
    demand_name: str,
    q: int,
    vehicle_key: str,
    site_ids: list[str] | None = None,
    tag: str,
) -> tuple[list[dict], list[dict], list[dict]]:
    """Exhaustive E + greedy-over-enum-scores F + C/D/B baselines.

    F is NOT a blind independent greedy: each trial looks up precomputed
    exhaustive subset evaluations (enum_cache). Do not claim compute savings vs E.
    """
    orig = _patch_realistic_speed_policy()
    cov_curve: list[dict] = []
    mission_flat: list[dict] = []
    traces: list[dict] = []
    try:
        cfg = load_multiroute_placement_config(cfg_path, root=ROOT)
        vpath = VEHICLES[vehicle_key]
        vehicle = load_vehicle(vpath)
        context = prepare_multiroute_placement_context(
            cfg,
            root=ROOT,
            demand_name=demand_name,
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
        sites = site_ids or [s.id for s in cfg.sites]
        print(f"[{tag}] sites={sites} missions={len(context['missions'])} q={q}", flush=True)

        import pickle

        enum_cache: dict[frozenset, dict] = {}
        cache_path = OUT / f"_enum_cache_{tag}.pkl"
        if cache_path.exists():
            enum_cache = pickle.loads(cache_path.read_bytes())
            print(f"[{tag}] Loaded enum cache n={len(enum_cache)} from {cache_path}", flush=True)
        for r in range(0, len(sites) + 1):
            for combo in itertools.combinations(sites, r):
                key = frozenset(combo)
                if key in enum_cache:
                    continue
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
                    f"[{tag}] ENUM {sorted(combo) or ['∅']}: "
                    f"ops={ev['operational_coverage']:.3f} energy={ev['energy_coverage']:.3f}",
                    flush=True,
                )
                if len(enum_cache) % 16 == 0:
                    cache_path.write_bytes(pickle.dumps(enum_cache))
        cache_path.write_bytes(pickle.dumps(enum_cache))
        print(f"[{tag}] Saved enum cache n={len(enum_cache)}", flush=True)

        fixed_cache: dict[frozenset, dict] = {}

        def best_under(nmax: int | None, route_mode: str, method_id: str, bname: str):
            best = None
            for key, ev0 in enum_cache.items():
                if nmax is not None and len(key) > nmax:
                    continue
                if route_mode == "fixed":
                    # Evaluate each subset's fixed-route portfolio at most once.
                    if key not in fixed_cache:
                        fixed_cache[key] = evaluate_subset(
                            context=context,
                            cfg=cfg,
                            installed=set(key),
                            route_mode="fixed",
                            masks=masks,
                            method_id="fixed_cache",
                            budget_name="all_subsets",
                            vehicle=vehicle,
                            fridge_path=FRIDGE,
                        )
                        print(
                            f"[{tag}] FIXED {sorted(key) or ['∅']}: "
                            f"ops={fixed_cache[key]['operational_coverage']:.3f}",
                            flush=True,
                        )
                    cand = dict(fixed_cache[key])
                    cand["method_id"] = method_id
                    cand["budget_name"] = bname
                    cand["selection_engine"] = "exhaustive_enumeration"
                else:
                    cand = dict(ev0)
                    cand["method_id"] = method_id
                    cand["budget_name"] = bname
                    cand["selection_engine"] = "exhaustive_enumeration"
                if best is None or _score(cand) > _score(best):
                    best = cand
            return best

        def greedy(nmax: int | None, bname: str):
            chosen: set[str] = set()
            best_ev = enum_cache[frozenset()]
            remaining = set(sites)
            while remaining and (nmax is None or len(chosen) < nmax):
                improved = False
                ranked = []
                for s in sorted(remaining):
                    trial = frozenset(chosen | {s})
                    if trial not in enum_cache:
                        continue
                    ranked.append((trial, enum_cache[trial]))
                ranked.sort(key=lambda x: _score(x[1]), reverse=True)
                if not ranked:
                    break
                trial, ev = ranked[0]
                if _score(ev) > _score(best_ev) or (
                    _score(ev)[:2] == _score(best_ev)[:2] and len(trial) <= len(chosen)
                ):
                    # accept if ops/energy improve
                    if float(ev["operational_coverage"]) > float(
                        best_ev["operational_coverage"]
                    ) + 1e-12 or (
                        abs(
                            float(ev["operational_coverage"])
                            - float(best_ev["operational_coverage"])
                        )
                        < 1e-12
                        and float(ev["energy_coverage"])
                        > float(best_ev["energy_coverage"]) + 1e-12
                    ):
                        chosen = set(trial)
                        best_ev = ev
                        remaining -= chosen
                        remaining = set(sites) - chosen
                        improved = True
                        # early stop if full ops coverage
                        if float(best_ev["operational_coverage"]) >= 1.0 - 1e-12:
                            break
                    else:
                        break
                else:
                    break
                if not improved:
                    break
            out = dict(best_ev)
            out.update(
                method_id="F_greedy_multi",
                budget_name=bname,
                installed=",".join(sorted(chosen)),
                n_sites=len(chosen),
                selection_engine="greedy_over_exhaustive_enum_scores",
            )
            # re-eval to attach mission rows under method id
            return evaluate_subset(
                context=context,
                cfg=cfg,
                installed=chosen,
                route_mode="multi",
                masks=masks,
                method_id="F_greedy_multi",
                budget_name=bname,
                vehicle=vehicle,
                fridge_path=FRIDGE,
            )

        conventional_order = [
            s
            for s in [
                "y_settat_ca",
                "y_settat_ac",
                "y_benguerir_ca",
                "y_benguerir_ac",
                "y_amskroud_ca",
            ]
            if s in sites
        ]
        budget_ns = [("B0", 0), ("B1", 1), ("B2", 2), ("B3", 3), ("Ball", None)]

        for bname, nmax in budget_ns:
            if nmax is None:
                conv = set(conventional_order)
            else:
                conv = set(conventional_order[: int(nmax)])

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
            c = best_under(nmax, "fixed", "C_fixed_optimized", bname)
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
            e = best_under(nmax, "multi", "E_joint_multi_enum", bname)
            f = greedy(nmax, bname)

            row = {
                "tag": tag,
                "vehicle_key": vehicle_key,
                "q": q,
                "budget": bname,
                "max_sites": nmax if nmax is not None else len(sites),
                "B_ops": b["operational_coverage"],
                "B_energy": b["energy_coverage"],
                "C_ops": c["operational_coverage"],
                "C_energy": c["energy_coverage"],
                "C_sites": c["installed"],
                "D_ops": d["operational_coverage"],
                "D_energy": d["energy_coverage"],
                "E_ops": e["operational_coverage"],
                "E_energy": e["energy_coverage"],
                "E_sites": e["installed"],
                "F_ops": f["operational_coverage"],
                "F_energy": f["energy_coverage"],
                "F_sites": f["installed"],
                "E_equals_F_ops": abs(float(e["operational_coverage"]) - float(f["operational_coverage"]))
                < 1e-9,
                "E_minus_C_ops": float(e["operational_coverage"]) - float(c["operational_coverage"]),
                "n_missions": e["n_missions"],
                "git_sha": _git_sha(),
            }
            cov_curve.append(row)
            print(
                f"[{tag}] {bname}: C_ops={row['C_ops']:.3f} E_ops={row['E_ops']:.3f} "
                f"F_ops={row['F_ops']:.3f} E-C={row['E_minus_C_ops']:.3f} E=F={row['E_equals_F_ops']}",
                flush=True,
            )
            for method_ev in (b, c, d, e, f):
                for mr in method_ev.get("mission_rows") or []:
                    flat = {
                        "tag": tag,
                        "vehicle_key": vehicle_key,
                        "q": q,
                        "budget": bname,
                        "method_id": method_ev["method_id"],
                        "installed": method_ev["installed"],
                        **{
                            k: v
                            for k, v in mr.items()
                            if k != "action_trace_json"
                        },
                    }
                    mission_flat.append(flat)
                    if mr.get("operationally_served") and mr.get("action_trace_json"):
                        try:
                            acts = json.loads(mr["action_trace_json"])
                        except Exception:  # noqa: BLE001
                            acts = []
                        for a in acts:
                            traces.append(
                                {
                                    "tag": tag,
                                    "vehicle_key": vehicle_key,
                                    "q": q,
                                    "budget": bname,
                                    "method_id": method_ev["method_id"],
                                    "od_id": mr.get("od_id"),
                                    "installed": method_ev["installed"],
                                    **{k: a.get(k) for k in (
                                        "action_type",
                                        "dt_s",
                                        "node",
                                        "arc_id",
                                        "soc_before",
                                        "soc_after",
                                        "hos_pad",
                                        "t_start_s",
                                        "t_end_s",
                                    )},
                                }
                            )
        return cov_curve, mission_flat, traces
    finally:
        pass


def run_q2_headline() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    all_cov: list[dict] = []
    all_m: list[dict] = []
    for veh in ("eactros_600", "volvo_475"):
        cov, missions, _tr = _run_af_portfolio(
            cfg_path=CFG_HEADLINE,
            demand_name="corridor_eactros_equal",
            q=2,
            vehicle_key=veh,
            site_ids=list(FULL_SITE_IDS),
            tag=f"q2_headline_{veh}",
        )
        all_cov.extend(cov)
        all_m.extend(missions)
    _write_csv(OUT / "q2_critical_portfolio.csv", all_cov)
    _write_csv(OUT / "q2_critical_missions.csv", all_m)


def _temp_demand_cfg(od_id: str, payload: float, soc: float) -> Path:
    raw = yaml.safe_load(CFG_PAPER.read_text(encoding="utf-8"))
    mid = f"F_{od_id}_p{int(payload)}_s{int(soc*100)}"
    raw["demand_scenarios"] = {
        "frontier_cell": {
            "note": "frontier cell",
            "missions": [
                {
                    "id": mid,
                    "od_id": od_id,
                    "weight": 1.0,
                    "E_truck_init": 0,
                    "E_init_soc_frac": float(soc),
                    "refrigeration_on": True,
                    "terrain_mode": "dem",
                    "weather_id": "cool",
                    "gcm": "light",
                    "cargo_payload_kg": float(payload),
                    "commodity": "firm_ripe_fresh_tomatoes",
                }
            ],
        }
    }
    td = OUT / "_tmp_cfgs"
    td.mkdir(parents=True, exist_ok=True)
    path = td / f"{mid}.yaml"
    path.write_text(yaml.safe_dump(raw), encoding="utf-8")
    return path


def run_frontier(
    *,
    q: int = 5,
    confirm_q: int = 2,
    vehicles: tuple[str, ...] = ("eactros_600", "volvo_475"),
    confirm_mode: str = "decisive",
    append: bool = True,
) -> None:
    """Screen frontier at q; optionally confirm decisive cells at confirm_q.

    confirm_mode:
      skip — no q=2 confirms
      decisive — flexibility gains + northbound 15t + SOC>=0.8 best ladder only
      full — previous broad confirm set (slow)
    """
    OUT.mkdir(parents=True, exist_ok=True)
    out_path = OUT / "payload_soc_frontier.csv"
    rows: list[dict] = []
    if append and out_path.exists():
        prev = pd.read_csv(out_path).to_dict(orient="records")
        # Drop vehicles being re-run so we can refresh them
        rows = [r for r in prev if str(r.get("vehicle_key")) not in set(vehicles)]
        print(f"Append mode: kept {len(rows)} prior rows; refreshing {vehicles}", flush=True)

    orig = _patch_realistic_speed_policy()
    try:
        for vehicle_key in vehicles:
            vpath = VEHICLES[vehicle_key]
            vehicle = load_vehicle(vpath)
            for od in FRONTIER_ODS:
                for payload in PAYLOADS:
                    for soc in SOCS:
                        cfg_path = _temp_demand_cfg(od, payload, soc)
                        cfg = load_multiroute_placement_config(cfg_path, root=ROOT)
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
                        )
                        pilot = load_multiroute_pilot_config(
                            cfg.multiroute_pilot_path, root=ROOT
                        )
                        path_rows = pd.read_csv(pilot.path_alternatives_csv).to_dict(
                            orient="records"
                        )
                        masks = _mission_masks(context, path_rows)
                        prep = context["prepared"][context["missions"][0].id]
                        dem_ok = bool(getattr(prep.ctx, "dem_complete", False))
                        for ladder_name, sites in INFRA_LADDERS[od]:
                            mr = evaluate_mission_operational(
                                prep=prep,
                                cfg=cfg,
                                installed=set(sites),
                                mask=masks[context["missions"][0].id]["all"],
                                vehicle=vehicle,
                                fridge_path=FRIDGE,
                                max_seconds=cfg.solver_max_seconds,
                                max_expansions=cfg.solver_max_expansions,
                            )
                            fr = evaluate_mission_operational(
                                prep=prep,
                                cfg=cfg,
                                installed=set(sites),
                                mask=masks[context["missions"][0].id]["short"],
                                vehicle=vehicle,
                                fridge_path=FRIDGE,
                                max_seconds=cfg.solver_max_seconds,
                                max_expansions=cfg.solver_max_expansions,
                            )
                            row = {
                                "vehicle_key": vehicle_key,
                                "od_id": od,
                                "payload_kg": payload,
                                "soc_frac": soc,
                                "q": q,
                                "dem_complete": dem_ok,
                                "infra_label": ladder_name,
                                "installed": ",".join(sorted(sites)),
                                "n_sites": len(sites),
                                "multi_ops": bool(mr.get("operationally_served")),
                                "multi_energy": bool(mr.get("energy_feasible")),
                                "multi_schedule": bool(mr.get("schedule_valid")),
                                "multi_min_soc": mr.get("min_soc"),
                                "multi_arrival_soc": mr.get("arrival_soc"),
                                "multi_road_km": mr.get("road_km"),
                                "multi_drive_min": mr.get("drive_min_phys"),
                                "multi_charge_min": mr.get("charge_min_phys"),
                                "multi_wait_min": mr.get("wait_min_phys"),
                                "multi_hos_pad_min": mr.get("pad_duration_min"),
                                "fixed_ops": bool(fr.get("operationally_served")),
                                "fixed_energy": bool(fr.get("energy_feasible")),
                                "fixed_schedule": bool(fr.get("schedule_valid")),
                                "fixed_min_soc": fr.get("min_soc"),
                                "fixed_road_km": fr.get("road_km"),
                                "flexibility_ops_gain": bool(mr.get("operationally_served"))
                                and not bool(fr.get("operationally_served")),
                                "git_sha": _git_sha(),
                            }
                            rows.append(row)
                            print(
                                f"FRONTIER {vehicle_key} {od} p={payload} soc={soc} "
                                f"{ladder_name}: multi_ops={row['multi_ops']} "
                                f"fixed_ops={row['fixed_ops']} flex={row['flexibility_ops_gain']}",
                                flush=True,
                            )
                            _write_csv(out_path, rows)
        _write_csv(out_path, rows)

        if confirm_mode == "skip":
            print("Skipping q=2 confirms (confirm_mode=skip)", flush=True)
            return

        confirm_path = OUT / "payload_soc_frontier_q2_confirm.csv"
        confirm_rows: list[dict] = []
        if confirm_path.exists():
            confirm_rows = pd.read_csv(confirm_path).to_dict(orient="records")
        done = {
            (
                str(r.get("vehicle_key")),
                str(r.get("od_id")),
                float(r.get("payload_kg")),
                float(r.get("soc_frac")),
                str(r.get("infra_label")),
            )
            for r in confirm_rows
        }

        # Prefer best multi ladder per (veh,od,payload,soc) for decisive confirms
        df_all = pd.DataFrame(rows)
        for vehicle_key in vehicles:
            sub_v = df_all[df_all.vehicle_key == vehicle_key]
            for _, g in sub_v.groupby(["od_id", "payload_kg", "soc_frac"]):
                g = g.copy()
                # always confirm flexibility-gain rows
                candidates = g[g.flexibility_ops_gain == True]  # noqa: E712
                # northbound 15t: all ladders (infrastructure rescue question)
                if (
                    str(g.iloc[0]["od_id"]) == "agadir_casa"
                    and float(g.iloc[0]["payload_kg"]) == 15000.0
                ):
                    candidates = pd.concat([candidates, g], ignore_index=True)
                # SOC>=0.8: confirm best multi ladder only (min sites among multi_ops True, else none)
                if float(g.iloc[0]["soc_frac"]) >= 0.8:
                    ok = g[g.multi_ops == True]  # noqa: E712
                    if len(ok):
                        best = ok.sort_values(["n_sites", "infra_label"]).iloc[0]
                        candidates = pd.concat([candidates, best.to_frame().T], ignore_index=True)
                    else:
                        none_row = g[g.n_sites == 0]
                        if len(none_row):
                            candidates = pd.concat(
                                [candidates, none_row.iloc[[0]]], ignore_index=True
                            )
                if confirm_mode == "full":
                    candidates = g
                # unique
                candidates = candidates.drop_duplicates(
                    subset=["vehicle_key", "od_id", "payload_kg", "soc_frac", "infra_label"]
                )
                for _, r in candidates.iterrows():
                    key = (
                        str(r["vehicle_key"]),
                        str(r["od_id"]),
                        float(r["payload_kg"]),
                        float(r["soc_frac"]),
                        str(r["infra_label"]),
                    )
                    if key in done:
                        continue
                    cfg_path = _temp_demand_cfg(
                        str(r["od_id"]), float(r["payload_kg"]), float(r["soc_frac"])
                    )
                    cfg = load_multiroute_placement_config(cfg_path, root=ROOT)
                    vpath = VEHICLES[str(r["vehicle_key"])]
                    vehicle = load_vehicle(vpath)
                    context = prepare_multiroute_placement_context(
                        cfg,
                        root=ROOT,
                        demand_name="frontier_cell",
                        energy_quantum_kwh=confirm_q,
                        objective_mode="enroute_incremental_cost",
                        vehicle_yaml=vpath,
                        road_cost_per_km=ROAD_CENTS,
                        fridge_yaml=FRIDGE,
                        charger_power_kw=350.0,
                        max_alternatives_for_union=2,
                    )
                    pilot = load_multiroute_pilot_config(
                        cfg.multiroute_pilot_path, root=ROOT
                    )
                    path_rows = pd.read_csv(pilot.path_alternatives_csv).to_dict(
                        orient="records"
                    )
                    masks = _mission_masks(context, path_rows)
                    prep = context["prepared"][context["missions"][0].id]
                    sites = set(str(r["installed"]).split(",")) if r["installed"] else set()
                    sites = {s for s in sites if s and s != "nan"}
                    mr = evaluate_mission_operational(
                        prep=prep,
                        cfg=cfg,
                        installed=sites,
                        mask=masks[context["missions"][0].id]["all"],
                        vehicle=vehicle,
                        fridge_path=FRIDGE,
                        max_seconds=cfg.solver_max_seconds,
                        max_expansions=cfg.solver_max_expansions,
                    )
                    fr = evaluate_mission_operational(
                        prep=prep,
                        cfg=cfg,
                        installed=sites,
                        mask=masks[context["missions"][0].id]["short"],
                        vehicle=vehicle,
                        fridge_path=FRIDGE,
                        max_seconds=cfg.solver_max_seconds,
                        max_expansions=cfg.solver_max_expansions,
                    )
                    crec = {
                        "vehicle_key": str(r["vehicle_key"]),
                        "od_id": str(r["od_id"]),
                        "payload_kg": float(r["payload_kg"]),
                        "soc_frac": float(r["soc_frac"]),
                        "infra_label": str(r["infra_label"]),
                        "installed": str(r["installed"]),
                        "n_sites": int(r["n_sites"]),
                        "q": confirm_q,
                        "multi_ops_q5": bool(r["multi_ops"]),
                        "fixed_ops_q5": bool(r["fixed_ops"]),
                        "multi_ops": bool(mr.get("operationally_served")),
                        "fixed_ops": bool(fr.get("operationally_served")),
                        "flexibility_ops_gain": bool(mr.get("operationally_served"))
                        and not bool(fr.get("operationally_served")),
                        "flexibility_ops_gain_q5": bool(r["multi_ops"])
                        and not bool(r["fixed_ops"]),
                        "multi_min_soc": mr.get("min_soc"),
                        "survives_q2_multi": bool(mr.get("operationally_served"))
                        == bool(r["multi_ops"]),
                        "survives_q2_fixed": bool(fr.get("operationally_served"))
                        == bool(r["fixed_ops"]),
                        "survives_q2_flex": (
                            bool(mr.get("operationally_served"))
                            and not bool(fr.get("operationally_served"))
                        )
                        == (
                            bool(r["multi_ops"]) and not bool(r["fixed_ops"])
                        ),
                        "survives_q2": bool(mr.get("operationally_served"))
                        == bool(r["multi_ops"]),
                        "git_sha": _git_sha(),
                    }
                    confirm_rows.append(crec)
                    done.add(key)
                    _write_csv(confirm_path, confirm_rows)
                    print(
                        f"CONFIRM q={confirm_q} {crec['vehicle_key']} {crec['od_id']} "
                        f"p={crec['payload_kg']} soc={crec['soc_frac']} {crec['infra_label']}: "
                        f"multi {crec['multi_ops_q5']}->{crec['multi_ops']}",
                        flush=True,
                    )
        _write_csv(OUT / "payload_soc_frontier_q2_confirm.csv", confirm_rows)
    finally:
        pass


def run_amskroud_value() -> None:
    """Compare CA southbound missions with/without Amskroud when on-union."""
    OUT.mkdir(parents=True, exist_ok=True)
    rows = []
    audit = pd.read_csv(OUT / "od_dem_site_audit.csv") if (OUT / "od_dem_site_audit.csv").exists() else None
    orig = _patch_realistic_speed_policy()
    try:
        for od in ("casa_agadir", "casa_marrakech", "marrakech_agadir"):
            on_union = True
            if audit is not None and len(audit):
                sub = audit[audit.od_id == od]
                if len(sub):
                    on_union = bool(sub.iloc[0]["amskroud_ca_on_union"])
            for vehicle_key in ("eactros_600",):
                for payload, soc in ((5300.0, 0.8), (10000.0, 0.8), (5300.0, 0.5)):
                    cfg_path = _temp_demand_cfg(od, payload, soc)
                    cfg = load_multiroute_placement_config(cfg_path, root=ROOT)
                    vpath = VEHICLES[vehicle_key]
                    vehicle = load_vehicle(vpath)
                    context = prepare_multiroute_placement_context(
                        cfg,
                        root=ROOT,
                        demand_name="frontier_cell",
                        energy_quantum_kwh=5,
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
                    prep = context["prepared"][context["missions"][0].id]
                    base = frozenset(["y_settat_ca", "y_benguerir_ca"])
                    with_a = frozenset(["y_settat_ca", "y_benguerir_ca", "y_amskroud_ca"])
                    for label, sites in (("without_amskroud", base), ("with_amskroud", with_a)):
                        if label == "with_amskroud" and not on_union:
                            rows.append(
                                {
                                    "od_id": od,
                                    "vehicle_key": vehicle_key,
                                    "payload_kg": payload,
                                    "soc_frac": soc,
                                    "label": label,
                                    "amskroud_on_union": on_union,
                                    "ops": False,
                                    "note": "skipped_value_claim_site_not_on_path_union",
                                }
                            )
                            continue
                        mr = evaluate_mission_operational(
                            prep=prep,
                            cfg=cfg,
                            installed=set(sites),
                            mask=masks[context["missions"][0].id]["all"],
                            vehicle=vehicle,
                            fridge_path=FRIDGE,
                            max_seconds=cfg.solver_max_seconds,
                            max_expansions=cfg.solver_max_expansions,
                        )
                        rows.append(
                            {
                                "od_id": od,
                                "vehicle_key": vehicle_key,
                                "payload_kg": payload,
                                "soc_frac": soc,
                                "label": label,
                                "amskroud_on_union": on_union,
                                "installed": ",".join(sorted(sites)),
                                "ops": bool(mr.get("operationally_served")),
                                "energy": bool(mr.get("energy_feasible")),
                                "min_soc": mr.get("min_soc"),
                                "charge_min": mr.get("charge_min_phys"),
                                "road_km": mr.get("road_km"),
                                "note": "counted_only_if_on_union",
                                "git_sha": _git_sha(),
                            }
                        )
                        print(
                            f"AMSK {od} {label} p={payload} soc={soc}: ops={rows[-1]['ops']}",
                            flush=True,
                        )
    finally:
        import morocco_etruck.optimization.multiroute_placement_evaluation as mpe

        mpe.load_multiroute_pilot_config = orig
    _write_csv(OUT / "amskroud_ca_value.csv", rows)


def run_compare_expanded(
    *,
    vehicles: tuple[str, ...] = ("eactros_600",),
    qs: tuple[int, ...] = (5, 2),
) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    out_cov = OUT / "method_comparison_AF.csv"
    out_m = OUT / "method_comparison_missions.csv"
    all_cov: list[dict] = []
    all_m: list[dict] = []
    if out_cov.exists():
        all_cov = pd.read_csv(out_cov).to_dict(orient="records")
    if out_m.exists():
        all_m = pd.read_csv(out_m).to_dict(orient="records")
    for q in qs:
        for veh in vehicles:
            tag = f"expanded_depot_q{q}_{veh}"
            if any(str(r.get("tag")) == tag for r in all_cov):
                print(f"Skip existing compare tag {tag}", flush=True)
                continue
            cov, missions, _ = _run_af_portfolio(
                cfg_path=CFG_PAPER,
                demand_name="realistic_depot_soc08_p5300",
                q=q,
                vehicle_key=veh,
                site_ids=list(FULL_SITE_IDS),
                tag=tag,
            )
            all_cov.extend(cov)
            all_m.extend(missions)
            _write_csv(out_cov, all_cov)
            _write_csv(out_m, all_m)
    _write_csv(out_cov, all_cov)
    _write_csv(out_m, all_m)


def run_robustness_matrix() -> None:
    """Pre-registered moderate robustness on flagship northbound + Marrakech flex OD."""
    OUT.mkdir(parents=True, exist_ok=True)
    from run_high_impact_completion import _scaled_vehicle_yaml

    cells = [
        {"id": "base", "payload": 5300.0, "soc": 0.8, "reserve": 0.10, "chg": 350.0, "weather": "cool", "cd": 1.0, "crr": 1.0},
        {"id": "reserve15", "payload": 5300.0, "soc": 0.8, "reserve": 0.15, "chg": 350.0, "weather": "cool", "cd": 1.0, "crr": 1.0},
        {"id": "reserve20", "payload": 5300.0, "soc": 0.8, "reserve": 0.20, "chg": 350.0, "weather": "cool", "cd": 1.0, "crr": 1.0},
        {"id": "chg250", "payload": 5300.0, "soc": 0.8, "reserve": 0.10, "chg": 250.0, "weather": "cool", "cd": 1.0, "crr": 1.0},
        {"id": "chg150", "payload": 5300.0, "soc": 0.8, "reserve": 0.10, "chg": 150.0, "weather": "cool", "cd": 1.0, "crr": 1.0},
        {"id": "hot", "payload": 5300.0, "soc": 0.8, "reserve": 0.10, "chg": 350.0, "weather": "hot", "cd": 1.0, "crr": 1.0},
        {"id": "aero110", "payload": 5300.0, "soc": 0.8, "reserve": 0.10, "chg": 350.0, "weather": "cool", "cd": 1.10, "crr": 1.0},
        {"id": "roll110", "payload": 5300.0, "soc": 0.8, "reserve": 0.10, "chg": 350.0, "weather": "cool", "cd": 1.0, "crr": 1.10},
        {"id": "p10t", "payload": 10000.0, "soc": 0.8, "reserve": 0.10, "chg": 350.0, "weather": "cool", "cd": 1.0, "crr": 1.0},
        {"id": "p15t", "payload": 15000.0, "soc": 0.8, "reserve": 0.10, "chg": 350.0, "weather": "cool", "cd": 1.0, "crr": 1.0},
        {"id": "p15t_soc10", "payload": 15000.0, "soc": 1.0, "reserve": 0.10, "chg": 350.0, "weather": "cool", "cd": 1.0, "crr": 1.0},
    ]
    targets = [
        ("agadir_casa", frozenset(["y_benguerir_ac"]), "multi"),
        ("agadir_casa", frozenset(["y_benguerir_ac", "y_settat_ac"]), "multi"),
        ("casa_marrakech", frozenset(["y_settat_ca"]), "multi"),
        ("casa_marrakech", frozenset(["y_settat_ca"]), "fixed"),
    ]
    rows: list[dict] = []
    out_path = OUT / "robustness_matrix.csv"
    vehicle_key = "eactros_600"
    base_v = VEHICLES[vehicle_key]
    orig = _patch_realistic_speed_policy()
    try:
        with tempfile.TemporaryDirectory() as td:
            tdir = Path(td)
            for cell in cells:
                vpath = _scaled_vehicle_yaml(
                    base_v,
                    cd_scale=float(cell["cd"]),
                    crr_scale=float(cell["crr"]),
                    reserve=float(cell["reserve"]),
                    tmp=tdir,
                )
                vehicle = load_vehicle(vpath)
                for od, sites, route_mode in targets:
                    cfg_path = _temp_demand_cfg(od, float(cell["payload"]), float(cell["soc"]))
                    # patch weather into temp cfg
                    raw = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))
                    for m in raw["demand_scenarios"]["frontier_cell"]["missions"]:
                        m["weather_id"] = cell["weather"]
                    cfg_path.write_text(yaml.safe_dump(raw), encoding="utf-8")
                    cfg = load_multiroute_placement_config(cfg_path, root=ROOT)
                    for q in (5, 2):
                        context = prepare_multiroute_placement_context(
                            cfg,
                            root=ROOT,
                            demand_name="frontier_cell",
                            energy_quantum_kwh=q,
                            objective_mode="enroute_incremental_cost",
                            vehicle_yaml=vpath,
                            road_cost_per_km=ROAD_CENTS,
                            fridge_yaml=FRIDGE,
                            charger_power_kw=float(cell["chg"]),
                            max_alternatives_for_union=2,
                        )
                        pilot = load_multiroute_pilot_config(cfg.multiroute_pilot_path, root=ROOT)
                        path_rows = pd.read_csv(pilot.path_alternatives_csv).to_dict(
                            orient="records"
                        )
                        masks = _mission_masks(context, path_rows)
                        prep = context["prepared"][context["missions"][0].id]
                        mid = context["missions"][0].id
                        mask = masks[mid]["short"] if route_mode == "fixed" else masks[mid]["all"]
                        mr = evaluate_mission_operational(
                            prep=prep,
                            cfg=cfg,
                            installed=set(sites),
                            mask=mask,
                            vehicle=vehicle,
                            fridge_path=FRIDGE,
                            max_seconds=cfg.solver_max_seconds,
                            max_expansions=cfg.solver_max_expansions,
                        )
                        rows.append(
                            {
                                "cell_id": cell["id"],
                                "vehicle_key": vehicle_key,
                                "od_id": od,
                                "route_mode": route_mode,
                                "q": q,
                                "payload_kg": cell["payload"],
                                "soc_frac": cell["soc"],
                                "reserve": cell["reserve"],
                                "charger_kw": cell["chg"],
                                "weather_id": cell["weather"],
                                "cd_scale": cell["cd"],
                                "crr_scale": cell["crr"],
                                "installed": ",".join(sorted(sites)),
                                "ops": bool(mr.get("operationally_served")),
                                "energy": bool(mr.get("energy_feasible")),
                                "schedule": bool(mr.get("schedule_valid")),
                                "min_soc": mr.get("min_soc"),
                                "charge_min": mr.get("charge_min_phys"),
                                "wait_min": mr.get("wait_min_phys"),
                                "road_km": mr.get("road_km"),
                                "git_sha": _git_sha(),
                            }
                        )
                        print(
                            f"ROB {cell['id']} q={q} {od} {route_mode}: ops={rows[-1]['ops']} "
                            f"energy={rows[-1]['energy']}",
                            flush=True,
                        )
                        _write_csv(out_path, rows)
    finally:
        import morocco_etruck.optimization.multiroute_placement_evaluation as mpe

        mpe.load_multiroute_pilot_config = orig
    _write_csv(out_path, rows)




def run_placement_flexibility_ablation() -> None:
    """Decompose C vs E B2 gap into placement vs route-flexibility effects.

    Uses committed q2_critical_missions.csv site sets; re-evaluates cross masks
    when physics stack is available. Always writes a mission-level decomposition
    from saved C/E outcomes plus optional cross rows.
    """
    OUT.mkdir(parents=True, exist_ok=True)
    missions_path = OUT / "q2_critical_missions.csv"
    if not missions_path.exists():
        print("No q2_critical_missions.csv — skip ablation", flush=True)
        return
    m = pd.read_csv(missions_path)
    rows: list[dict] = []
    for vehicle_key, gv in m.groupby("vehicle_key"):
        for budget, gb in gv.groupby("budget"):
            c = gb[gb.method_id.astype(str).str.contains("C_fixed")]
            e = gb[gb.method_id.astype(str).str.contains("E_joint")]
            if c.empty or e.empty:
                continue
            c_sites = str(c.iloc[0].get("installed") or "")
            e_sites = str(e.iloc[0].get("installed") or "")
            # Mission-level saved outcomes
            for od in sorted(set(c.od_id.astype(str)) | set(e.od_id.astype(str))):
                crow = c[c.od_id.astype(str) == od]
                erow = e[e.od_id.astype(str) == od]
                if crow.empty or erow.empty:
                    continue
                c_ops = str(crow.iloc[0].get("operationally_served")).lower() in {"true", "1"}
                e_ops = str(erow.iloc[0].get("operationally_served")).lower() in {"true", "1"}
                rows.append(
                    {
                        "vehicle_key": vehicle_key,
                        "budget": budget,
                        "od_id": od,
                        "C_sites": c_sites,
                        "E_sites": e_sites,
                        "sites_differ": c_sites != e_sites,
                        "C_ops_on_C_sites_fixed": c_ops,
                        "E_ops_on_E_sites_multi": e_ops,
                        "delta_E_minus_C": int(e_ops) - int(c_ops),
                        "note": (
                            "placement_and_flexibility_confounded"
                            if c_sites != e_sites
                            else "same_sites"
                        ),
                        "git_sha": _git_sha(),
                    }
                )
    out = OUT / "placement_flexibility_ablation.csv"
    _write_csv(out, rows)
    # Summary: eActros B2
    sub = [r for r in rows if r["vehicle_key"] == "eactros_600" and str(r["budget"]) == "B2"]
    gained = [r for r in sub if r["delta_E_minus_C"] > 0]
    lost = [r for r in sub if r["delta_E_minus_C"] < 0]
    print(
        "Ablation eActros B2: sites_differ=%s gained=%s lost=%s"
        % (
            sum(r["sites_differ"] for r in sub),
            [r["od_id"] for r in gained],
            [r["od_id"] for r in lost],
        ),
        flush=True,
    )


def write_efficiency_from_missions() -> None:
    path = OUT / "method_comparison_missions.csv"
    q2 = OUT / "q2_critical_missions.csv"
    frames = []
    for p in (path, q2):
        if p.exists():
            frames.append(pd.read_csv(p))
    if not frames:
        return
    m = pd.concat(frames, ignore_index=True)
    # Matched feasible C vs E at same budget
    rows = []
    for (tag, budget, veh, q, od), g in m.groupby(
        ["tag", "budget", "vehicle_key", "q", "od_id"]
    ):
        c = g[g.method_id.str.contains("C_fixed")]
        e = g[g.method_id.str.contains("E_joint")]
        if c.empty or e.empty:
            continue
        c0, e0 = c.iloc[0], e.iloc[0]
        c_ops = str(c0.get("operationally_served")).lower() in {"true", "1"}
        e_ops = str(e0.get("operationally_served")).lower() in {"true", "1"}
        row = {
            "tag": tag,
            "budget": budget,
            "vehicle_key": veh,
            "q": q,
            "od_id": od,
            "C_ops": c_ops,
            "E_ops": e_ops,
            "comparison_type": (
                "matched_time"
                if c_ops and e_ops
                else ("serviceability_gain" if e_ops and not c_ops else "neither_or_C_only")
            ),
            "C_road_km": c0.get("road_km"),
            "E_road_km": e0.get("road_km"),
            "C_drive_min": c0.get("drive_min_phys"),
            "E_drive_min": e0.get("drive_min_phys"),
            "C_charge_min": c0.get("charge_min_phys"),
            "E_charge_min": e0.get("charge_min_phys"),
            "C_wait_min": c0.get("wait_min_phys"),
            "E_wait_min": e0.get("wait_min_phys"),
            "C_min_soc": c0.get("min_soc"),
            "E_min_soc": e0.get("min_soc"),
            "E_hos_pad_min": e0.get("pad_duration_min"),
        }
        if c_ops and e_ops:
            try:
                row["delta_trip_min"] = (
                    float(e0.get("drive_min_phys") or 0)
                    + float(e0.get("charge_min_phys") or 0)
                    + float(e0.get("wait_min_phys") or 0)
                ) - (
                    float(c0.get("drive_min_phys") or 0)
                    + float(c0.get("charge_min_phys") or 0)
                    + float(c0.get("wait_min_phys") or 0)
                )
                row["delta_km"] = float(e0.get("road_km") or 0) - float(c0.get("road_km") or 0)
            except Exception:  # noqa: BLE001
                row["delta_trip_min"] = None
                row["delta_km"] = None
        rows.append(row)
    _write_csv(OUT / "operational_efficiency.csv", rows)


def write_figures() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    figdir = OUT / "figures"
    figdir.mkdir(parents=True, exist_ok=True)
    paper_fig = ROOT / "paper" / "figures"
    paper_fig.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []

    def _save(fig, name: str) -> None:
        p1 = figdir / name
        fig.savefig(p1, dpi=150)
        p2 = paper_fig / name
        fig.savefig(p2, dpi=150)
        written.append(p1)
        plt.close(fig)

    q2 = OUT / "q2_critical_portfolio.csv"
    if q2.exists():
        df = pd.read_csv(q2)
        for veh, g in df.groupby("vehicle_key"):
            fig, ax = plt.subplots(figsize=(8, 4.5))
            x = list(range(len(g)))
            for col, lab, sty in [
                ("C_ops", "C fixed+opt", "s--"),
                ("E_ops", "E joint enum", "o-"),
                ("F_ops", "F greedy", "^-"),
            ]:
                ax.plot(x, g[col], sty, label=lab)
            ax.set_xticks(x)
            ax.set_xticklabels(list(g["budget"]))
            ax.set_ylim(-0.05, 1.05)
            ax.set_ylabel("Operational coverage")
            ax.set_title(f"Ops coverage vs budget (q=2, {veh}, SOC taper)")
            ax.legend()
            ax.grid(True, alpha=0.3)
            fig.tight_layout()
            _save(fig, f"fig1_coverage_vs_budget_{veh}.png")

    fr = OUT / "payload_soc_frontier.csv"
    if fr.exists():
        df = pd.read_csv(fr)
        for veh in df.vehicle_key.unique():
            for od in sorted(df.od_id.unique()):
                sub = df[(df.vehicle_key == veh) & (df.od_id == od)]
                if sub.empty:
                    continue
                pivot = (
                    sub.groupby(["payload_kg", "soc_frac"])["multi_ops"]
                    .max()
                    .unstack("soc_frac")
                    .reindex(index=PAYLOADS, columns=SOCS)
                    .astype(float)
                )
                fig, ax = plt.subplots(figsize=(6.5, 4.2))
                im = ax.imshow(pivot.values, aspect="auto", cmap="RdYlGn", vmin=0, vmax=1)
                ax.set_xticks(range(len(SOCS)))
                ax.set_xticklabels([f"{int(s*100)}%" for s in SOCS])
                ax.set_yticks(range(len(PAYLOADS)))
                ax.set_yticklabels([f"{p/1000:.1f}t" for p in PAYLOADS])
                ax.set_xlabel("Departure SOC")
                ax.set_ylabel("Payload")
                ax.set_title(f"Multi-route ops feasibility ({veh}, {od})")
                for i in range(pivot.shape[0]):
                    for j in range(pivot.shape[1]):
                        val = pivot.values[i, j]
                        if pd.isna(val):
                            continue
                        ax.text(j, i, "Y" if val >= 0.5 else "N", ha="center", va="center")
                fig.colorbar(im, ax=ax, fraction=0.046)
                fig.tight_layout()
                _save(fig, f"fig2_payload_soc_{veh}_{od}.png")

    eff = OUT / "operational_efficiency.csv"
    if eff.exists():
        df = pd.read_csv(eff)
        gain = df[df.comparison_type == "serviceability_gain"]
        matched = df[df.comparison_type == "matched_time"]
        fig, ax = plt.subplots(figsize=(7, 4))
        ax.bar(
            ["serviceability_gain\n(E yes, C no)", "matched_time\nboth feasible"],
            [len(gain), len(matched)],
            color=["#2c7bb6", "#fdae61"],
        )
        ax.set_ylabel("Mission comparisons (count)")
        ax.set_title("Route flexibility / joint benefit types")
        fig.tight_layout()
        _save(fig, "fig3_flexibility_and_time.png")

    if fr.exists():
        df = pd.read_csv(fr)
        sub = df[(df.soc_frac >= 0.8) & (df.vehicle_key == "eactros_600")]
        if not sub.empty:
            g = sub.groupby("n_sites")["multi_ops"].mean()
            fig, ax = plt.subplots(figsize=(6.5, 4))
            ax.plot(g.index, g.values, "o-", color="#1a9641")
            ax.set_xlabel("Installed sites (ladder)")
            ax.set_ylabel("Share ops-feasible cells")
            ax.set_ylim(-0.05, 1.05)
            ax.set_title("Infrastructure vs ops feasibility (eActros, SOC≥80%)")
            ax.grid(True, alpha=0.3)
            fig.tight_layout()
            _save(fig, "fig4_infra_robustness.png")

    rob = OUT / "robustness_matrix.csv"
    if rob.exists():
        df = pd.read_csv(rob)
        if "ops" in df.columns and "cell_id" in df.columns:
            pivot_src = df.copy()
            if "od_id" in pivot_src.columns:
                heat = (
                    pivot_src.groupby(["cell_id", "od_id"])["ops"]
                    .max()
                    .unstack("od_id")
                    .astype(float)
                )
                fig, ax = plt.subplots(figsize=(8, 5))
                im = ax.imshow(heat.values, aspect="auto", cmap="RdYlGn", vmin=0, vmax=1)
                ax.set_xticks(range(heat.shape[1]))
                ax.set_xticklabels(list(heat.columns), rotation=45, ha="right")
                ax.set_yticks(range(heat.shape[0]))
                ax.set_yticklabels(list(heat.index))
                ax.set_title("Robustness matrix (ops)")
                fig.colorbar(im, ax=ax, fraction=0.046)
                fig.tight_layout()
                _save(fig, "fig5_robustness_heatmap.png")

    print(f"Wrote {len(written)} figures to {figdir} and {paper_fig}", flush=True)


def write_report() -> None:
    lines = [
        "# PAPER_SCIENTIFIC_RESULTS_CAMPAIGN",
        "",
        f"Git SHA: `{_git_sha()}`",
        "",
        "Primary metric: **operational coverage** (energy + continuous replay + schedule/HOS).",
        "Chargers are hypothetical. Scenario counts are not Moroccan traffic samples.",
        "",
    ]
    # DEM audit
    audit_p = OUT / "od_dem_site_audit.csv"
    if audit_p.exists():
        a = pd.read_csv(audit_p)
        lines += ["## DEM / site audit", ""]
        for _, r in a.iterrows():
            lines.append(
                f"- `{r.od_id}`: dem_complete={r.dem_complete}, "
                f"amskroud_on_union={r.amskroud_ca_on_union}"
            )
        lines.append("")

    q2p = OUT / "q2_critical_portfolio.csv"
    if q2p.exists():
        df = pd.read_csv(q2p)
        lines += ["## 1–2. Strongest findings & E vs C vs F (q=2 headline)", ""]
        for veh, g in df.groupby("vehicle_key"):
            lines.append(f"### {veh}")
            lines.append("| budget | C_ops | E_ops | F_ops | E−C | E=F | E_sites |")
            lines.append("|---|---:|---:|---:|---:|---|---|")
            for _, r in g.iterrows():
                lines.append(
                    f"| {r.budget} | {r.C_ops:.2f} | {r.E_ops:.2f} | {r.F_ops:.2f} | "
                    f"{r.E_minus_C_ops:.2f} | {r.E_equals_F_ops} | {r.E_sites} |"
                )
            b2 = g[g.budget == "B2"]
            if len(b2):
                r = b2.iloc[0]
                lines.append(
                    f"- B2 denominator n_missions={int(r.n_missions)}: "
                    f"E serves {r.E_ops*r.n_missions:.0f}/{int(r.n_missions)}, "
                    f"C serves {r.C_ops*r.n_missions:.0f}/{int(r.n_missions)}."
                )
            lines.append("")

    frp = OUT / "payload_soc_frontier.csv"
    if frp.exists():
        df = pd.read_csv(frp)
        lines += ["## 3. Payload × SOC frontier (does it hold under realistic dispatch?)", ""]
        # Summary: for each veh/od/payload/soc, whether any infra makes multi ops True
        summ = (
            df.groupby(["vehicle_key", "od_id", "payload_kg", "soc_frac"])
            .agg(multi_any=("multi_ops", "max"), fixed_any=("fixed_ops", "max"), flex=("flexibility_ops_gain", "max"))
            .reset_index()
        )
        lines.append("| vehicle | od | payload_t | soc | multi_any | fixed_any | flex_gain |")
        lines.append("|---|---|---:|---:|---|---|---|")
        for _, r in summ.iterrows():
            lines.append(
                f"| {r.vehicle_key} | {r.od_id} | {r.payload_kg/1000:.1f} | {r.soc_frac:.1f} | "
                f"{bool(r.multi_any)} | {bool(r.fixed_any)} | {bool(r.flex)} |"
            )
        lines.append("")
        # Count flex gains at SOC>=0.8
        flex80 = summ[(summ.soc_frac >= 0.8) & (summ.flex)]
        conf_p = OUT / "payload_soc_frontier_q2_confirm.csv"
        flex_note = (
            f"- Flexibility ops-gains at SOC≥80% (q=5 screen): **{len(flex80)}** cells "
            f"(denominator {len(summ[summ.soc_frac >= 0.8])} veh×od×payload×soc summaries)."
        )
        if conf_p.exists():
            conf = pd.read_csv(conf_p)
            if "survives_q2_flex" in conf.columns:
                u = (
                    conf[(conf.soc_frac >= 0.8) & (conf.flexibility_ops_gain == True)]  # noqa: E712
                    .groupby(["vehicle_key", "od_id", "payload_kg", "soc_frac"])
                    .size()
                    .reset_index()
                )
                flex_note += (
                    f" Retained flex advantage at q=2 (`survives_q2_flex` / flex True): "
                    f"**{len(u)}** unique scenarios (not {len(flex80)})."
                )
            flip_p = OUT / "q_resolution_flip_inventory.csv"
            if flip_p.exists():
                flips = pd.read_csv(flip_p)
                flex_note += f" q-resolution flips logged: **{len(flips)}** rows."
        lines.append(flex_note)
        lines.append(
            "- Agadir→Casablanca 15 t / SOC 0.8 is **discretization-sensitive**: "
            "unserved at q=5 ladders but eActros served at q=2 with Benguerir AC "
            "(min SOC≈0.107). Do not treat SOC=1.0 as a categorical physical requirement "
            "pending HOS-in-search re-run."
        )
        lines.append("")

    amsk = OUT / "amskroud_ca_value.csv"
    if amsk.exists():
        a = pd.read_csv(amsk)
        lines += ["## 4. Infrastructure required / Amskroud CA value", ""]
        for od, g in a.groupby("od_id"):
            on = bool(g.iloc[0].get("amskroud_on_union"))
            lines.append(f"- `{od}`: amskroud_on_union={on}")
            if on:
                for (p, s), gg in g.groupby(["payload_kg", "soc_frac"]):
                    wo = gg[gg.label == "without_amskroud"]
                    wi = gg[gg.label == "with_amskroud"]
                    if len(wo) and len(wi):
                        lines.append(
                            f"  - p={p} soc={s}: without={bool(wo.iloc[0].ops)} "
                            f"with={bool(wi.iloc[0].ops)}"
                        )
        lines.append("")

    eff = OUT / "operational_efficiency.csv"
    if eff.exists():
        e = pd.read_csv(eff)
        lines += ["## 5. Charging / rest / time credibility", ""]
        lines.append(
            f"- Matched-time comparisons (both C and E ops-feasible): **{len(e[e.comparison_type=='matched_time'])}**"
        )
        lines.append(
            f"- Serviceability-only gains (E yes, C no): **{len(e[e.comparison_type=='serviceability_gain'])}**"
        )
        mt = e[e.comparison_type == "matched_time"]
        if len(mt) and "delta_trip_min" in mt.columns:
            lines.append(
                f"- Matched Δtrip_min median={mt['delta_trip_min'].median():.2f} "
                f"(positive ⇒ E slower)."
            )
        lines.append("")

    lines += [
        "## 6–7. Generalization & strength vs prior 3-mission pilot",
        "",
        "- Headline q=2 confirms whether prior B2 claims survive finer energy grid.",
        "- Frontier expands evidence across payload×SOC; unique ODs separated from scenario rows.",
        "- DEM recovery for `marrakech_casa` / `agadir_marrakech` succeeded via COP-DEM on verified OSM macros.",
        "",
        "## 8. Remaining barriers to journal submission",
        "",
        "- No observed OD truck counts / charger availability / grid capacity.",
        "- Axle-law compliance unverified; HGV access at ADM sites unknown.",
        "- CCS taper is a research envelope, not OEM-measured curves.",
        "- Equal / illustrative weights ≠ traffic sample.",
        "- If heavy-payload cells remain unserved, that is a physical/operating finding—not a solver bug.",
        "",
        "## Artifacts",
        "",
        f"- Directory: `{OUT.as_posix()}`",
        f"- Figures: `{(OUT / 'figures').as_posix()}`",
        "",
        "## Answers checklist",
        "",
        "1. Strongest three positive findings: see q=2 B2 E−C gaps and frontier flexibility cells above.",
        "2. vs optimized fixed (C) and greedy (F): tables above; ties reported when E=F.",
        "3. Realistic SOC/payload: frontier section.",
        "4. Infrastructure required: E_sites columns + Amskroud section.",
        "5. Charging/rest credibility: efficiency section + HOS pads in mission CSVs.",
        "6. General vs case-specific: compare headline vs frontier vs expanded depot panel.",
        "7. Stronger than 3-mission? Only if frontier + expanded OD panel add mechanism-separated gains.",
        "8. Barriers: listed above.",
        "",
    ]
    OUT_MD.write_text("\n".join(lines), encoding="utf-8")
    print("Wrote", OUT_MD, flush=True)

    # manifest
    files = {}
    for p in OUT.rglob("*"):
        if p.is_file() and p.suffix in {".csv", ".png", ".json", ".md"}:
            rel = str(p.relative_to(ROOT)).replace("\\", "/")
            if p.name == "campaign_manifest.json":
                continue  # avoid self-hash of previous manifest
            files[rel] = _sha(p)
    if OUT_MD.exists():
        files["reports/PAPER_SCIENTIFIC_RESULTS_CAMPAIGN.md"] = _sha(OUT_MD)
    (OUT / "campaign_manifest.json").write_text(
        json.dumps(
            {
                "git_sha": _git_sha(),
                "created": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "files_sha256": files,
            },
            indent=2,
        ),
        encoding="utf-8",
    )


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--phase",
        default="all",
        choices=[
            "freeze",
            "audit",
            "q2_headline",
            "frontier",
            "amskroud",
            "compare",
            "robustness",
            "ablation",
            "efficiency",
            "figures",
            "report",
            "all",
        ],
    )
    ap.add_argument(
        "--vehicles",
        default="eactros_600,volvo_475",
        help="Comma-separated vehicle keys for frontier/compare phases",
    )
    ap.add_argument(
        "--confirm-mode",
        default="decisive",
        choices=["skip", "decisive", "full"],
        help="q=2 frontier confirm policy",
    )
    ap.add_argument(
        "--confirm-only",
        action="store_true",
        help="Run only q=2 confirms from existing frontier CSV (no re-screen)",
    )
    ap.add_argument(
        "--compare-qs",
        default="5,2",
        help="Comma-separated q values for expanded A-F compare",
    )
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    vehicles = tuple(v.strip() for v in args.vehicles.split(",") if v.strip())
    compare_qs = tuple(int(x) for x in args.compare_qs.split(",") if x.strip())

    if args.phase in ("freeze", "all"):
        freeze_registry()
    if args.phase in ("audit", "all"):
        audit_dem_and_sites()
    if args.phase in ("q2_headline", "all"):
        run_q2_headline()
    if args.phase in ("frontier", "all"):
        if args.confirm_only:
            # Reuse confirm logic by loading existing rows and skipping screen.
            out_path = OUT / "payload_soc_frontier.csv"
            if not out_path.exists():
                raise SystemExit("No frontier CSV for --confirm-only")
            # Monkey-patch: call confirm path via run_frontier with empty vehicle screen
            # by temporarily swapping FRONTIER body — instead, invoke confirm directly:
            import types

            rows = pd.read_csv(out_path).to_dict(orient="records")
            # Filter to requested vehicles
            rows = [r for r in rows if str(r.get("vehicle_key")) in set(vehicles)]
            # Build a tiny wrapper using run_frontier confirm section by setting confirm_mode
            # and vehicles but short-circuit screen with preloaded rows:
            def _confirm_only():
                confirm_path = OUT / "payload_soc_frontier_q2_confirm.csv"
                confirm_rows: list[dict] = []
                if confirm_path.exists():
                    confirm_rows = pd.read_csv(confirm_path).to_dict(orient="records")
                done = {
                    (
                        str(r.get("vehicle_key")),
                        str(r.get("od_id")),
                        float(r.get("payload_kg")),
                        float(r.get("soc_frac")),
                        str(r.get("infra_label")),
                    )
                    for r in confirm_rows
                }
                df_all = pd.DataFrame(rows)
                confirm_q = 2
                orig_sp = _patch_realistic_speed_policy()
                try:
                    for vehicle_key in vehicles:
                        sub_v = df_all[df_all.vehicle_key == vehicle_key]
                        if sub_v.empty:
                            continue
                        for _, g in sub_v.groupby(["od_id", "payload_kg", "soc_frac"]):
                            candidates = g[g.flexibility_ops_gain == True]  # noqa: E712
                            if (
                                str(g.iloc[0]["od_id"]) == "agadir_casa"
                                and float(g.iloc[0]["payload_kg"]) == 15000.0
                            ):
                                candidates = pd.concat([candidates, g], ignore_index=True)
                            if float(g.iloc[0]["soc_frac"]) >= 0.8:
                                ok = g[g.multi_ops == True]  # noqa: E712
                                if len(ok):
                                    best = ok.sort_values(["n_sites", "infra_label"]).iloc[0]
                                    candidates = pd.concat(
                                        [candidates, best.to_frame().T], ignore_index=True
                                    )
                                else:
                                    none_row = g[g.n_sites == 0]
                                    if len(none_row):
                                        candidates = pd.concat(
                                            [candidates, none_row.iloc[[0]]], ignore_index=True
                                        )
                            if args.confirm_mode == "full":
                                candidates = g
                            candidates = candidates.drop_duplicates(
                                subset=[
                                    "vehicle_key",
                                    "od_id",
                                    "payload_kg",
                                    "soc_frac",
                                    "infra_label",
                                ]
                            )
                            for _, r in candidates.iterrows():
                                key = (
                                    str(r["vehicle_key"]),
                                    str(r["od_id"]),
                                    float(r["payload_kg"]),
                                    float(r["soc_frac"]),
                                    str(r["infra_label"]),
                                )
                                if key in done:
                                    continue
                                cfg_path = _temp_demand_cfg(
                                    str(r["od_id"]), float(r["payload_kg"]), float(r["soc_frac"])
                                )
                                cfg = load_multiroute_placement_config(cfg_path, root=ROOT)
                                vpath = VEHICLES[str(r["vehicle_key"])]
                                vehicle = load_vehicle(vpath)
                                context = prepare_multiroute_placement_context(
                                    cfg,
                                    root=ROOT,
                                    demand_name="frontier_cell",
                                    energy_quantum_kwh=confirm_q,
                                    objective_mode="enroute_incremental_cost",
                                    vehicle_yaml=vpath,
                                    road_cost_per_km=ROAD_CENTS,
                                    fridge_yaml=FRIDGE,
                                    charger_power_kw=350.0,
                                    max_alternatives_for_union=2,
                                )
                                pilot = load_multiroute_pilot_config(
                                    cfg.multiroute_pilot_path, root=ROOT
                                )
                                path_rows = pd.read_csv(pilot.path_alternatives_csv).to_dict(
                                    orient="records"
                                )
                                masks = _mission_masks(context, path_rows)
                                prep = context["prepared"][context["missions"][0].id]
                                sites = (
                                    set(str(r["installed"]).split(","))
                                    if r["installed"]
                                    else set()
                                )
                                sites = {s for s in sites if s and s != "nan"}
                                mr = evaluate_mission_operational(
                                    prep=prep,
                                    cfg=cfg,
                                    installed=sites,
                                    mask=masks[context["missions"][0].id]["all"],
                                    vehicle=vehicle,
                                    fridge_path=FRIDGE,
                                    max_seconds=cfg.solver_max_seconds,
                                    max_expansions=cfg.solver_max_expansions,
                                )
                                fr = evaluate_mission_operational(
                                    prep=prep,
                                    cfg=cfg,
                                    installed=sites,
                                    mask=masks[context["missions"][0].id]["short"],
                                    vehicle=vehicle,
                                    fridge_path=FRIDGE,
                                    max_seconds=cfg.solver_max_seconds,
                                    max_expansions=cfg.solver_max_expansions,
                                )
                                crec = {
                                    "vehicle_key": str(r["vehicle_key"]),
                                    "od_id": str(r["od_id"]),
                                    "payload_kg": float(r["payload_kg"]),
                                    "soc_frac": float(r["soc_frac"]),
                                    "infra_label": str(r["infra_label"]),
                                    "installed": str(r["installed"]),
                                    "n_sites": int(r["n_sites"]),
                                    "q": confirm_q,
                                    "multi_ops_q5": bool(r["multi_ops"]),
                                    "fixed_ops_q5": bool(r["fixed_ops"]),
                                    "multi_ops": bool(mr.get("operationally_served")),
                                    "fixed_ops": bool(fr.get("operationally_served")),
                                    "flexibility_ops_gain": bool(mr.get("operationally_served"))
                                    and not bool(fr.get("operationally_served")),
                                    "flexibility_ops_gain_q5": bool(r["multi_ops"])
                                    and not bool(r["fixed_ops"]),
                                    "multi_min_soc": mr.get("min_soc"),
                                    "survives_q2_multi": bool(mr.get("operationally_served"))
                                    == bool(r["multi_ops"]),
                                    "survives_q2_fixed": bool(fr.get("operationally_served"))
                                    == bool(r["fixed_ops"]),
                                    "survives_q2_flex": (
                                        bool(mr.get("operationally_served"))
                                        and not bool(fr.get("operationally_served"))
                                    )
                                    == (
                                        bool(r["multi_ops"]) and not bool(r["fixed_ops"])
                                    ),
                                    "survives_q2": bool(mr.get("operationally_served"))
                                    == bool(r["multi_ops"]),
                                    "git_sha": _git_sha(),
                                }
                                confirm_rows.append(crec)
                                done.add(key)
                                _write_csv(confirm_path, confirm_rows)
                                print(
                                    f"CONFIRM q={confirm_q} {crec['vehicle_key']} {crec['od_id']} "
                                    f"p={crec['payload_kg']} soc={crec['soc_frac']} {crec['infra_label']}: "
                                    f"multi {crec['multi_ops_q5']}->{crec['multi_ops']}",
                                    flush=True,
                                )
                finally:
                    import morocco_etruck.optimization.multiroute_placement_evaluation as mpe

                    mpe.load_multiroute_pilot_config = orig_sp
                _write_csv(confirm_path, confirm_rows)
                print("Confirm-only done; rows=", len(confirm_rows), flush=True)

            _confirm_only()
        else:
            run_frontier(
                q=5,
                confirm_q=2,
                vehicles=vehicles,
                confirm_mode=args.confirm_mode,
                append=True,
            )
    if args.phase in ("amskroud", "all"):
        run_amskroud_value()
    if args.phase in ("compare", "all"):
        run_compare_expanded(vehicles=vehicles, qs=compare_qs)
    if args.phase in ("robustness", "all"):
        run_robustness_matrix()
    if args.phase in ("ablation", "all"):
        run_placement_flexibility_ablation()
    if args.phase in ("efficiency", "all", "compare", "q2_headline"):
        write_efficiency_from_missions()
    if args.phase in ("figures", "all"):
        write_figures()
    if args.phase in ("report", "all"):
        # Always regenerate from current paper_campaign numerics after constant-power wipe.
        write_report()


if __name__ == "__main__":
    main()
