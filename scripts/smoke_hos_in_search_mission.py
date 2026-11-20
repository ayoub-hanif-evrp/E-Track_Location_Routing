"""Smoke: one national mission under HOS-in-search; record audit-only flag."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))

import pandas as pd
from morocco_etruck.energy.vehicle import load_vehicle
from morocco_etruck.optimization.multiroute_placement import load_multiroute_placement_config
from morocco_etruck.optimization.multiroute_placement_evaluation import (
    load_multiroute_pilot_config,
    prepare_multiroute_placement_context,
)
from run_final_operational_correction import evaluate_mission_operational
from run_paper_scientific_results_campaign import (
    FRIDGE,
    ROAD_CENTS,
    VEHICLES,
    _mission_masks,
    _patch_realistic_speed_policy,
    _temp_demand_cfg,
)


def main() -> None:
    od = "casa_rabat"
    payload, soc = 5300.0, 0.8
    vehicle_key = "eactros_600"
    orig = _patch_realistic_speed_policy()
    try:
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
        mid = context["missions"][0].id
        mr = evaluate_mission_operational(
            prep=prep,
            cfg=cfg,
            installed=set(),
            mask=masks[mid]["all"],
            vehicle=vehicle,
            fridge_path=FRIDGE,
            max_seconds=cfg.solver_max_seconds,
            max_expansions=cfg.solver_max_expansions,
        )
        out = ROOT / "results/paper_campaign/hos_in_search_smoke.json"
        keep = {
            k: mr.get(k)
            for k in (
                "od_id",
                "operationally_served",
                "energy_feasible",
                "schedule_valid",
                "hos_adjusted",
                "hos_in_search",
                "hos_search_audit_only",
                "pad_location",
                "pad_duration_min",
                "status",
                "min_soc",
            )
        }
        out.write_text(json.dumps(keep, indent=2, default=str), encoding="utf-8")
        print("smoke", keep)
    finally:
        import morocco_etruck.optimization.multiroute_placement_evaluation as mpe

        mpe.load_multiroute_pilot_config = orig


if __name__ == "__main__":
    main()
