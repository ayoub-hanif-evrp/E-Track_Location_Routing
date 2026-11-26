#!/usr/bin/env python3
"""Task 8.5 — Controlled DEM-aware vs flat-road comparison.

Identical missions/vehicle/payload/SOC/infra; only terrain_mode differs.
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import run_stage_c_hos_national as stage_c  # noqa: E402
from run_final_operational_correction import evaluate_mission_operational  # noqa: E402
from run_paper_scientific_results_campaign import FRIDGE  # noqa: E402
from morocco_etruck.optimization.multiroute_placement import (  # noqa: E402
    load_multiroute_placement_config,
)
from morocco_etruck.energy.vehicle import load_vehicle  # noqa: E402
from morocco_etruck.optimization.multiroute_placement_evaluation import (  # noqa: E402
    prepare_multiroute_placement_context,
)
from run_high_impact_realism_sprint import ROAD_CENTS, VEHICLES  # noqa: E402

OUT = ROOT / "results/final_evidence/experiments/dem_vs_flat"

# Representative mountainous vs flatter corridors
CELLS = [
    ("casa_agadir", 5300.0, 0.5, {"y_benguerir_ca"}),  # long southbound, stressed
    ("casa_marrakech", 5300.0, 0.5, {"y_benguerir_ca"}),
    ("rabat_fes", 5300.0, 0.8, set()),  # inland grades
    ("casa_rabat", 5300.0, 0.8, set()),  # relatively flat coastal
]


def _git_sha() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT).decode().strip()
    except Exception:  # noqa: BLE001
        return "unknown"


def _eval(od: str, payload: float, soc: float, terrain: str, installed: set[str]) -> dict:
    raw = yaml.safe_load(stage_c.CFG_HEADLINE.read_text(encoding="utf-8"))
    with tempfile.TemporaryDirectory() as td:
        tdir = Path(td)
        cfg_path = tdir / "cell.yaml"
        demand = {
            "note": "dem_vs_flat",
            "missions": [
                {
                    "id": f"df_{od}_{terrain}",
                    "od_id": od,
                    "weight": 1.0,
                    "E_truck_init": 0,
                    "E_init_soc_frac": soc,
                    "refrigeration_on": True,
                    "terrain_mode": terrain,
                    "weather_id": "cool",
                    "gcm": "light",
                    "cargo_payload_kg": payload,
                }
            ],
        }
        raw["demand_scenarios"] = {"dem_vs_flat": demand}
        cfg_path.write_text(yaml.safe_dump(raw), encoding="utf-8")
        cfg = load_multiroute_placement_config(cfg_path, root=ROOT)
        vpath = VEHICLES["eactros_600"]
        vehicle = load_vehicle(vpath)
        context = prepare_multiroute_placement_context(
            cfg,
            root=ROOT,
            demand_name="dem_vs_flat",
            energy_quantum_kwh=2,
            objective_mode="enroute_incremental_cost",
            vehicle_yaml=vpath,
            road_cost_per_km=ROAD_CENTS,
            fridge_yaml=FRIDGE,
            charger_power_kw=350.0,
            max_alternatives_for_union=2,
            probe_serviceability=False,
        )
        mid = context["missions"][0].id
        prep = context["prepared"][mid]
        mr = evaluate_mission_operational(
            prep=prep,
            cfg=cfg,
            installed=set(installed),
            mask=frozenset(stage_c._mission_masks(context, pd.read_csv(
                __import__("morocco_etruck.optimization.multiroute_adapter", fromlist=["load_multiroute_pilot_config"]).load_multiroute_pilot_config(
                    cfg.multiroute_pilot_path, root=ROOT
                ).path_alternatives_csv
            ).to_dict(orient="records"))[mid]["all"]),
            vehicle=vehicle,
            fridge_path=FRIDGE,
            max_seconds=600.0,
            max_expansions=2_000_000,
            include_energy_only=True,
        )
        # Simpler mask: use all arcs from prepared template
        # The above is fragile; rebuild masks properly
        return mr, context, mid


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    orig = stage_c._patch_realistic_speed_policy()
    rows = []
    try:
        for od, payload, soc, installed in CELLS:
            for terrain in ("dem", "flat"):
                print(f"[demflat] {od} terrain={terrain} soc={soc}", flush=True)
                cfg, vehicle, context, masks = stage_c._prepare_one(
                    vehicle_key="eactros_600", od_id=od, payload=payload, soc=soc, q=2
                )
                # Override terrain by re-prepare with temp cfg when flat
                if terrain == "flat":
                    # Use prepare_one then note: stage_c prepare uses YAML terrain dem.
                    # Re-run via temp demand with flat.
                    raw = yaml.safe_load(stage_c.CFG_HEADLINE.read_text(encoding="utf-8"))
                    with tempfile.TemporaryDirectory() as td:
                        tdir = Path(td)
                        cfg_path = tdir / "flat.yaml"
                        raw["demand_scenarios"] = {
                            "cell": {
                                "note": "flat",
                                "missions": [
                                    {
                                        "id": f"flat_{od}",
                                        "od_id": od,
                                        "weight": 1.0,
                                        "E_truck_init": 0,
                                        "E_init_soc_frac": soc,
                                        "refrigeration_on": True,
                                        "terrain_mode": "flat",
                                        "weather_id": "cool",
                                        "gcm": "light",
                                        "cargo_payload_kg": payload,
                                    }
                                ],
                            }
                        }
                        cfg_path.write_text(yaml.safe_dump(raw), encoding="utf-8")
                        cfg = load_multiroute_placement_config(cfg_path, root=ROOT)
                        vpath = VEHICLES["eactros_600"]
                        vehicle = load_vehicle(vpath)
                        context = prepare_multiroute_placement_context(
                            cfg,
                            root=ROOT,
                            demand_name="cell",
                            energy_quantum_kwh=2,
                            objective_mode="enroute_incremental_cost",
                            vehicle_yaml=vpath,
                            road_cost_per_km=ROAD_CENTS,
                            fridge_yaml=FRIDGE,
                            charger_power_kw=350.0,
                            max_alternatives_for_union=2,
                            probe_serviceability=False,
                        )
                        mid = context["missions"][0].id
                        prep = context["prepared"][mid]
                        pilot = __import__(
                            "morocco_etruck.optimization.multiroute_adapter",
                            fromlist=["load_multiroute_pilot_config"],
                        ).load_multiroute_pilot_config(cfg.multiroute_pilot_path, root=ROOT)
                        path_rows = pd.read_csv(pilot.path_alternatives_csv).to_dict(orient="records")
                        masks = stage_c._mission_masks(context, path_rows)
                        mr = evaluate_mission_operational(
                            prep=prep,
                            cfg=cfg,
                            installed=set(installed),
                            mask=frozenset(masks[mid]["all"]),
                            vehicle=vehicle,
                            fridge_path=FRIDGE,
                            max_seconds=600.0,
                            max_expansions=2_000_000,
                            include_energy_only=True,
                        )
                else:
                    mid = context["missions"][0].id
                    prep = context["prepared"][mid]
                    mr = evaluate_mission_operational(
                        prep=prep,
                        cfg=cfg,
                        installed=set(installed),
                        mask=frozenset(masks[mid]["all"]),
                        vehicle=vehicle,
                        fridge_path=FRIDGE,
                        max_seconds=600.0,
                        max_expansions=2_000_000,
                        include_energy_only=True,
                    )
                row = dict(mr)
                # Energy from trace
                tr = row.get("action_trace_json")
                et = ea = er = eg = None
                if tr:
                    actions = json.loads(tr) if isinstance(tr, str) else tr
                    et = sum(float(a.get("E_traction_kwh") or 0) for a in actions)
                    ea = sum(float(a.get("E_aux_kwh") or 0) for a in actions)
                    er = sum(float(a.get("E_refrig_kwh") or 0) for a in actions)
                    eg = sum(float(a.get("E_regen_credit_kwh") or 0) for a in actions)
                row.update(
                    {
                        "od_id": od,
                        "payload_kg": payload,
                        "soc_frac": soc,
                        "terrain_mode": terrain,
                        "installed": ",".join(sorted(installed)),
                        "E_traction_kwh": et,
                        "E_aux_kwh": ea,
                        "E_refrig_kwh": er,
                        "E_regen_credit_kwh": eg,
                        "vehicle_key": "eactros_600",
                        "git_sha": _git_sha(),
                        "pipeline": "final_evidence_dem_vs_flat",
                    }
                )
                rows.append(row)
                print(
                    f"  status={row.get('status')} ops={row.get('operationally_served')} "
                    f"min_soc={row.get('min_soc')} traction={et}",
                    flush=True,
                )
                pd.DataFrame(rows).to_csv(OUT / "dem_vs_flat_missions.csv", index=False)
    finally:
        import morocco_etruck.optimization.multiroute_placement_evaluation as mpe

        mpe.load_multiroute_pilot_config = orig

    df = pd.DataFrame(rows)
    df.to_csv(OUT / "dem_vs_flat_missions.csv", index=False)
    # Pairwise delta table
    deltas = []
    for od in df.od_id.unique():
        dem = df[(df.od_id == od) & (df.terrain_mode == "dem")]
        flat = df[(df.od_id == od) & (df.terrain_mode == "flat")]
        if len(dem) and len(flat):
            d, f = dem.iloc[0], flat.iloc[0]
            deltas.append(
                {
                    "od_id": od,
                    "soc_frac": d.soc_frac,
                    "installed": d.installed,
                    "ops_dem": bool(d.operationally_served),
                    "ops_flat": bool(f.operationally_served),
                    "min_soc_dem": d.min_soc,
                    "min_soc_flat": f.min_soc,
                    "traction_dem": d.E_traction_kwh,
                    "traction_flat": f.E_traction_kwh,
                    "regen_dem": d.E_regen_credit_kwh,
                    "regen_flat": f.E_regen_credit_kwh,
                    "delta_traction_kwh": (
                        None
                        if pd.isna(d.E_traction_kwh) or pd.isna(f.E_traction_kwh)
                        else float(d.E_traction_kwh) - float(f.E_traction_kwh)
                    ),
                    "delta_min_soc": (
                        None
                        if pd.isna(d.min_soc) or pd.isna(f.min_soc)
                        else float(d.min_soc) - float(f.min_soc)
                    ),
                }
            )
    pd.DataFrame(deltas).to_csv(
        ROOT / "results/final_evidence/tables/results/R-T09_dem_vs_flat.csv", index=False
    )
    print("Wrote", OUT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
