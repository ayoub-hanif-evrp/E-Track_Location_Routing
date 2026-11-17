#!/usr/bin/env python
"""Critical q=1 confirms for northbound SOC and Marrakech→Agadir transitions."""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from run_high_impact_realism_sprint import (  # noqa: E402
    FRIDGE,
    ROAD_CENTS,
    VEHICLES,
    _mission_masks,
    _patch_realistic_speed_policy,
    _write_csv,
)
from run_paper_scientific_results_campaign import (  # noqa: E402
    OUT,
    _git_sha,
    _temp_demand_cfg,
    evaluate_mission_operational,
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

CELLS = [
    ("eactros_600", "agadir_casa", 5300.0, 1.0, "opt1_benguerir_ac", frozenset(["y_benguerir_ac"])),
    ("eactros_600", "agadir_casa", 5300.0, 1.0, "none", frozenset()),
    ("eactros_600", "agadir_casa", 15000.0, 0.8, "opt2_benguerir_pair", frozenset(["y_benguerir_ac", "y_settat_ac"])),
    ("eactros_600", "agadir_casa", 15000.0, 1.0, "opt1_benguerir_ac", frozenset(["y_benguerir_ac"])),
    ("volvo_475", "marrakech_agadir", 5300.0, 0.8, "none", frozenset()),
    ("volvo_475", "marrakech_agadir", 15000.0, 1.0, "none", frozenset()),
    ("volvo_475", "marrakech_agadir", 15000.0, 1.0, "amskroud_only", frozenset(["y_amskroud_ca"])),
]


def main() -> None:
    _patch_realistic_speed_policy()
    rows: list[dict] = []
    out = OUT / "critical_q1_confirms.csv"
    for veh, od, payload, soc, lab, sites in CELLS:
        for q in (2, 1):
            vpath = VEHICLES[veh]
            vehicle = load_vehicle(vpath)
            cfg = load_multiroute_placement_config(
                _temp_demand_cfg(od, payload, soc), root=ROOT
            )
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
            mid = context["missions"][0].id
            prep = context["prepared"][mid]
            pilot = load_multiroute_pilot_config(cfg.multiroute_pilot_path, root=ROOT)
            path_rows = pd.read_csv(pilot.path_alternatives_csv).to_dict(orient="records")
            masks = _mission_masks(context, path_rows)
            mr = evaluate_mission_operational(
                prep=prep,
                cfg=cfg,
                installed=set(sites),
                mask=masks[mid]["all"],
                vehicle=vehicle,
                fridge_path=FRIDGE,
                max_seconds=cfg.solver_max_seconds,
                max_expansions=cfg.solver_max_expansions,
            )
            fr = evaluate_mission_operational(
                prep=prep,
                cfg=cfg,
                installed=set(sites),
                mask=masks[mid]["short"],
                vehicle=vehicle,
                fridge_path=FRIDGE,
                max_seconds=cfg.solver_max_seconds,
                max_expansions=cfg.solver_max_expansions,
            )
            rec = {
                "vehicle_key": veh,
                "od_id": od,
                "payload_kg": payload,
                "soc_frac": soc,
                "infra_label": lab,
                "q": q,
                "multi_ops": bool(mr.get("operationally_served")),
                "fixed_ops": bool(fr.get("operationally_served")),
                "energy": bool(mr.get("energy_feasible")),
                "schedule": bool(mr.get("schedule_valid")),
                "indep_rest": bool(mr.get("hos_independent_rest")),
                "pad": mr.get("pad_location"),
                "min_soc": mr.get("min_soc"),
                "hos_notes": mr.get("hos_notes"),
                "git_sha": _git_sha(),
            }
            rows.append(rec)
            print(
                f"Q1CRIT q={q} {veh} {od} p={payload} soc={soc} {lab}: "
                f"multi={rec['multi_ops']} fixed={rec['fixed_ops']} "
                f"indep={rec['indep_rest']} min_soc={rec['min_soc']}",
                flush=True,
            )
            _write_csv(out, rows)
    print("done", len(rows), flush=True)


if __name__ == "__main__":
    main()
