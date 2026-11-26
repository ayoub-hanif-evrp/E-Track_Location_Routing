#!/usr/bin/env python3
"""Build OD × candidate accessibility matrix from route-union topology.

Uses the same prepare pipeline as operational evaluation. A candidate is
accessible on an OD if its station_key appears on that OD's path-union station
map. Direction-blind counterfactual is labeled explicitly as non-executable.
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

from run_high_impact_realism_sprint import (  # noqa: E402
    FRIDGE,
    ROAD_CENTS,
    VEHICLES,
    _patch_realistic_speed_policy,
)
from morocco_etruck.optimization.multiroute_placement import (  # noqa: E402
    load_multiroute_placement_config,
)
from morocco_etruck.optimization.multiroute_placement_evaluation import (  # noqa: E402
    prepare_multiroute_placement_context,
)

CFG = ROOT / "configs/optimization/multiroute_placement_corridor_portfolio.yaml"
OUT = ROOT / "results/final_evidence/dataset"
TAB = ROOT / "results/final_evidence/tables/dataset"
HEADLINE_ODS = [
    "casa_marrakech",
    "casa_agadir",
    "marrakech_agadir",
    "agadir_marrakech",
    "marrakech_casa",
    "agadir_casa",
    "casa_tangier",
    "tangier_casa",
    "tangier_rabat",
    "rabat_tangier",
    "rabat_fes",
    "fes_rabat",
    "casa_rabat",
    "rabat_casa",
]


def _git_sha() -> str:
    try:
        return (
            subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT)
            .decode()
            .strip()
        )
    except Exception:  # noqa: BLE001
        return "unknown"


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    TAB.mkdir(parents=True, exist_ok=True)
    raw_sites = yaml.safe_load(CFG.read_text(encoding="utf-8"))["sites"]
    site_by_key = {s["station_key"]: s for s in raw_sites}
    site_ids = [s["id"] for s in raw_sites]

    orig = _patch_realistic_speed_policy()
    long_rows = []
    od_rows = []
    try:
        demand = {
            "note": "OD-candidate accessibility",
            "missions": [
                {
                    "id": f"acc_{od}",
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
                for od in HEADLINE_ODS
            ],
        }
        with tempfile.TemporaryDirectory() as td:
            tdir = Path(td)
            cfg_path = tdir / "acc_cfg.yaml"
            raw = yaml.safe_load(CFG.read_text(encoding="utf-8"))
            raw["demand_scenarios"] = {"accessibility": demand}
            cfg_path.write_text(yaml.safe_dump(raw), encoding="utf-8")
            cfg = load_multiroute_placement_config(cfg_path, root=ROOT)
            context = prepare_multiroute_placement_context(
                cfg,
                root=ROOT,
                demand_name="accessibility",
                energy_quantum_kwh=5,
                objective_mode="enroute_incremental_cost",
                vehicle_yaml=VEHICLES["eactros_600"],
                road_cost_per_km=ROAD_CENTS,
                fridge_yaml=FRIDGE,
                charger_power_kw=350.0,
                max_alternatives_for_union=2,
                probe_serviceability=False,
            )
            for m in context["missions"]:
                prep = context["prepared"][m.id]
                st = getattr(prep.template, "stations", {}) or {}
                keys_on = sorted(str(k) for k in (st.keys() if isinstance(st, dict) else st))
                keys_set = set(keys_on)
                od_rows.append(
                    {
                        "od_id": m.od_id,
                        "dem_complete": bool(getattr(prep.ctx, "dem_complete", False)),
                        "n_station_keys_on_union": len(keys_on),
                        "station_keys_on_union": ",".join(keys_on),
                        "git_sha": _git_sha(),
                    }
                )
                for s in raw_sites:
                    sk = s["station_key"]
                    on_union = sk in keys_set
                    # Direction-blind: treat opposite-direction sibling as accessible
                    # if either directional key for same place-name stem is on union.
                    stem = sk.rsplit("_", 1)[0]
                    siblings = [k for k in site_by_key if k.startswith(stem + "_") or k == stem]
                    # Better: group by place token
                    place = sk.split("_")[0]
                    place_keys = [k for k in site_by_key if k.split("_")[0] == place]
                    blind_on = any(k in keys_set for k in place_keys)
                    long_rows.append(
                        {
                            "od_id": m.od_id,
                            "site_id": s["id"],
                            "station_key": sk,
                            "direction": s.get("direction"),
                            "label": s.get("label"),
                            "on_route_union_directional": on_union,
                            "on_route_union_direction_blind_counterfactual": blind_on,
                            "direction_blind_is_executable": False,
                            "note": (
                                "direction_blind counterfactual is NOT physically executable "
                                "opposite-carriageway access"
                                if blind_on and not on_union
                                else ""
                            ),
                        }
                    )
                print(f"{m.od_id}: {keys_on}", flush=True)
    finally:
        import morocco_etruck.optimization.multiroute_placement_evaluation as mpe

        mpe.load_multiroute_pilot_config = orig

    long_df = pd.DataFrame(long_rows)
    od_df = pd.DataFrame(od_rows)
    long_df.to_csv(OUT / "od_candidate_accessibility_long.csv", index=False)
    od_df.to_csv(OUT / "od_station_keys_on_union.csv", index=False)

    # Wide matrix (directional)
    mat = long_df.pivot_table(
        index="od_id",
        columns="site_id",
        values="on_route_union_directional",
        aggfunc="max",
    ).reindex(index=HEADLINE_ODS, columns=site_ids)
    mat = mat.fillna(False).astype(bool)
    mat.to_csv(TAB / "R-T10_od_candidate_accessibility_matrix.csv")

    # Blind counterfactual matrix
    mat_b = long_df.pivot_table(
        index="od_id",
        columns="site_id",
        values="on_route_union_direction_blind_counterfactual",
        aggfunc="max",
    ).reindex(index=HEADLINE_ODS, columns=site_ids)
    mat_b = mat_b.fillna(False).astype(bool)
    mat_b.to_csv(OUT / "od_candidate_accessibility_direction_blind_counterfactual.csv")

    # Focus rows for infeasible diagnosis
    focus = long_df[
        long_df["od_id"].isin(["marrakech_agadir", "agadir_casa", "casa_agadir"])
        & long_df["station_key"].isin(
            [
                "amskroud_ca",
                "benguerir_ca",
                "benguerir_ac",
                "settat_ca",
                "settat_ac",
            ]
        )
    ]
    focus.to_csv(OUT / "infeasible_mission_topology_focus.csv", index=False)

    meta = {
        "git_sha": _git_sha(),
        "n_ods": len(HEADLINE_ODS),
        "n_sites": len(site_ids),
        "n_accessible_pairs": int(long_df["on_route_union_directional"].sum()),
        "focus_verification": focus.to_dict(orient="records"),
    }
    (OUT / "od_candidate_accessibility_meta.json").write_text(
        json.dumps(meta, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(meta, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
