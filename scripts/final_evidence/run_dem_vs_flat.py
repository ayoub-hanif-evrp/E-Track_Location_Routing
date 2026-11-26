#!/usr/bin/env python3
"""Controlled DEM vs flat comparisons.

Two separate experiment families:
1. fixed_short — identical shortest-path geometry; terrain is the only change.
2. reoptimized_multi — multi-route union; routing/charging may differ (previous campaign).

Do not interpret reoptimized distance/traction deltas as pure terrain effects.
"""
from __future__ import annotations

import hashlib
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
TAB = ROOT / "results/final_evidence/tables/results"

CELLS = [
    ("casa_agadir", 5300.0, 0.5, {"y_benguerir_ca"}),
    ("casa_marrakech", 5300.0, 0.5, {"y_benguerir_ca"}),
    ("rabat_fes", 5300.0, 0.8, set()),
    ("casa_rabat", 5300.0, 0.8, set()),
]


def _git_sha() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT).decode().strip()
    except Exception:  # noqa: BLE001
        return "unknown"


def _prepare(od: str, payload: float, soc: float, terrain: str):
    raw = yaml.safe_load(stage_c.CFG_HEADLINE.read_text(encoding="utf-8"))
    td = Path(tempfile.mkdtemp(prefix=f"demflat_{terrain}_"))
    cfg_path = td / f"{od}_{terrain}.yaml"
    raw["demand_scenarios"] = {
        "cell": {
            "note": f"dem_vs_flat_{terrain}",
            "missions": [
                {
                    "id": f"{terrain}_{od}",
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
    from morocco_etruck.optimization.multiroute_adapter import load_multiroute_pilot_config

    pilot = load_multiroute_pilot_config(cfg.multiroute_pilot_path, root=ROOT)
    path_rows = pd.read_csv(pilot.path_alternatives_csv).to_dict(orient="records")
    masks = stage_c._mission_masks(context, path_rows)
    return cfg, vehicle, context, masks, mid


def _trace_metrics(mr: dict) -> dict:
    tr = mr.get("action_trace_json")
    et = ea = er = eg = ech = 0.0
    arcs = []
    charge_min = wait_min = 0.0
    if tr and not (isinstance(tr, float)):
        actions = json.loads(tr) if isinstance(tr, str) else tr
        for a in actions:
            et += float(a.get("E_traction_kwh") or 0)
            ea += float(a.get("E_aux_kwh") or 0)
            er += float(a.get("E_refrig_kwh") or 0)
            eg += float(a.get("E_regen_credit_kwh") or 0)
            typ = a.get("action_type") or a.get("type")
            if typ == "DRIVE" and a.get("arc_id"):
                arcs.append(str(a["arc_id"]))
            if typ == "CHARGE":
                ech += float(a.get("charge_kwh") or 0)
                charge_min += float(a.get("dt_s") or 0) / 60.0
            if typ in {"WAIT", "BREAK", "REST"}:
                wait_min += float(a.get("dt_s") or 0) / 60.0
    route_id = hashlib.sha1("|".join(arcs).encode()).hexdigest()[:12] if arcs else ""
    return {
        "E_traction_kwh": et,
        "E_aux_kwh": ea,
        "E_refrig_kwh": er,
        "E_regen_credit_kwh": eg,
        "E_charge_kwh": ech,
        "E_net_battery_kwh": et + ea + er - eg,
        "drive_arc_ids": ",".join(arcs),
        "route_id": route_id,
        "n_drive_arcs": len(arcs),
        "charge_min_from_trace": charge_min,
        "wait_break_min_from_trace": wait_min,
    }


def _eval_cell(od, payload, soc, installed, terrain, route_mode: str) -> dict:
    print(f"[demflat] {route_mode} {od} terrain={terrain}", flush=True)
    cfg, vehicle, context, masks, mid = _prepare(od, payload, soc, terrain)
    mask_key = "short" if route_mode == "fixed_short" else "all"
    mr = evaluate_mission_operational(
        prep=context["prepared"][mid],
        cfg=cfg,
        installed=set(installed),
        mask=frozenset(masks[mid][mask_key]),
        vehicle=vehicle,
        fridge_path=FRIDGE,
        max_seconds=600.0,
        max_expansions=2_000_000,
        include_energy_only=True,
    )
    row = dict(mr)
    row.update(_trace_metrics(row))
    row.update(
        {
            "od_id": od,
            "payload_kg": payload,
            "soc_frac": soc,
            "terrain_mode": terrain,
            "route_mode": route_mode,
            "installed": ",".join(sorted(installed)),
            "vehicle_key": "eactros_600",
            "git_sha": _git_sha(),
            "pipeline": "final_evidence_dem_vs_flat_v2",
        }
    )
    print(
        f"  status={row.get('status')} ops={row.get('operationally_served')} "
        f"road_km={row.get('road_km')} route={row.get('route_id')} "
        f"traction={row.get('E_traction_kwh')}",
        flush=True,
    )
    return row


def _pairwise(df: pd.DataFrame, route_mode: str) -> pd.DataFrame:
    deltas = []
    sub = df[df.route_mode == route_mode]
    for (od, soc), g in sub.groupby(["od_id", "soc_frac"]):
        dem = g[g.terrain_mode == "dem"]
        flat = g[g.terrain_mode == "flat"]
        if not len(dem) or not len(flat):
            continue
        d, f = dem.iloc[0], flat.iloc[0]
        same_route = str(d.route_id) == str(f.route_id) and abs(
            float(d.road_km or 0) - float(f.road_km or 0)
        ) < 0.05
        deltas.append(
            {
                "comparison_family": route_mode,
                "od_id": od,
                "soc_frac": d.soc_frac,
                "installed": d.installed,
                "ops_dem": bool(d.operationally_served),
                "ops_flat": bool(f.operationally_served),
                "road_km_dem": d.road_km,
                "road_km_flat": f.road_km,
                "route_id_dem": d.route_id,
                "route_id_flat": f.route_id,
                "same_route_geometry": same_route,
                "min_soc_dem": d.min_soc,
                "min_soc_flat": f.min_soc,
                "traction_dem": d.E_traction_kwh,
                "traction_flat": f.E_traction_kwh,
                "regen_dem": d.E_regen_credit_kwh,
                "regen_flat": f.E_regen_credit_kwh,
                "net_battery_dem": d.E_net_battery_kwh,
                "net_battery_flat": f.E_net_battery_kwh,
                "charge_kwh_dem": d.E_charge_kwh,
                "charge_kwh_flat": f.E_charge_kwh,
                "charge_min_dem": d.charge_min_phys if "charge_min_phys" in d else d.charge_min_from_trace,
                "charge_min_flat": f.charge_min_phys if "charge_min_phys" in f else f.charge_min_from_trace,
                "delta_traction_kwh": float(d.E_traction_kwh) - float(f.E_traction_kwh)
                if pd.notna(d.E_traction_kwh) and pd.notna(f.E_traction_kwh)
                else None,
                "delta_min_soc": float(d.min_soc) - float(f.min_soc)
                if pd.notna(d.min_soc) and pd.notna(f.min_soc)
                else None,
                "interpretation": (
                    "terrain_only"
                    if same_route
                    else "confounded_route_and_terrain"
                ),
            }
        )
    return pd.DataFrame(deltas)


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    TAB.mkdir(parents=True, exist_ok=True)
    # Preserve previous reoptimized CSV as explicit archive
    legacy = OUT / "dem_vs_flat_missions.csv"
    if legacy.exists() and not (OUT / "dem_vs_flat_missions_reoptimized_legacy.csv").exists():
        legacy.replace(OUT / "dem_vs_flat_missions_reoptimized_legacy.csv")

    orig = stage_c._patch_realistic_speed_policy()
    rows = []
    try:
        for route_mode in ("fixed_short", "reoptimized_multi"):
            for od, payload, soc, installed in CELLS:
                for terrain in ("dem", "flat"):
                    rows.append(
                        _eval_cell(od, payload, soc, installed, terrain, route_mode)
                    )
                    pd.DataFrame(rows).to_csv(OUT / "dem_vs_flat_missions.csv", index=False)
    finally:
        import morocco_etruck.optimization.multiroute_placement_evaluation as mpe

        mpe.load_multiroute_pilot_config = orig

    df = pd.DataFrame(rows)
    df.to_csv(OUT / "dem_vs_flat_missions.csv", index=False)

    fixed = _pairwise(df, "fixed_short")
    reopt = _pairwise(df, "reoptimized_multi")
    both = pd.concat([fixed, reopt], ignore_index=True)
    both.to_csv(TAB / "R-T09_dem_vs_flat.csv", index=False)
    fixed.to_csv(TAB / "R-T09_dem_vs_flat_fixed_route.csv", index=False)
    reopt.to_csv(TAB / "R-T09_dem_vs_flat_reoptimized.csv", index=False)

    # Coastal Casa–Rabat mechanism note
    note_lines = [
        "# DEM vs flat interpretation notes",
        "",
        "## Comparison families",
        "",
        "1. `fixed_short`: identical shortest-path mask; terrain-only effect.",
        "2. `reoptimized_multi`: multi-route union; routing/charging may change with terrain.",
        "",
        "Casa–Marrakech reoptimized distance differences (≈257 vs ≈236 km) are **route-selection**",
        "effects under energy stress, not DEM geometry changes. Use the fixed-route table for",
        "terrain-only traction deltas.",
        "",
        "## Casa–Rabat coastal traction under DEM",
        "",
    ]
    cr = both[(both.od_id == "casa_rabat")]
    if len(cr):
        note_lines.append(cr.to_string(index=False))
        note_lines.extend(
            [
                "",
                "If DEM traction is lower than flat on this short coastal OD, the likely physical",
                "mechanism is **net downhill / regen-eligible grade segments** captured by DEM but",
                "absent under flat (zero grade). Verify via regen credits and net battery columns;",
                "if regen and net demand do not reconcile, treat as an accounting issue.",
                "",
            ]
        )
    (OUT / "dem_vs_flat_interpretation.md").write_text("\n".join(note_lines), encoding="utf-8")
    print(both.to_string(index=False))
    print("Wrote", OUT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
