#!/usr/bin/env python3
"""Build D-T07 vehicle/refrigeration parameters and frozen scenario inventory."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[2]
TAB = ROOT / "results/final_evidence/tables/dataset"
MAN = ROOT / "results/final_evidence/manifests"
EXP = ROOT / "results/final_evidence/experiments"

HEADLINE_YAML = ROOT / "configs/optimization/multiroute_placement_corridor_portfolio.yaml"
VEHICLES = {
    "eactros_600": ROOT / "configs/vehicles/eactros_600.yaml",
    "volvo_475": ROOT / "configs/vehicles/volvo_fh_electric_4x2_540kwh.yaml",
    "volvo_460_usable": ROOT / "configs/vehicles/volvo_fh_electric_4x2_540kwh_usable460.yaml",
}
# Registry key volvo_475 is the Path A / paper campaign vehicle key.
PRIMARY_VEHICLE_KEYS = ("eactros_600", "volvo_475")
INFRA = [
    ("I0_none", ()),
    ("I1_benguerir_ca", ("y_benguerir_ca",)),
    ("I2_benguerir_larache", ("y_benguerir_ca", "y_larache_rt")),
]
SOC_SCENARIOS = ("stressed_mixed", "common_soc_80")


def _flatten(prefix: str, obj, rows: list, vehicle_key: str, path: str) -> None:
    if isinstance(obj, dict):
        for k, v in obj.items():
            _flatten(f"{prefix}.{k}" if prefix else str(k), v, rows, vehicle_key, path)
    elif isinstance(obj, list):
        rows.append(
            {
                "vehicle_key": vehicle_key,
                "config_path": path,
                "parameter": prefix,
                "value": json.dumps(obj),
                "units_or_note": "list",
                "observation_type": "assumed_or_manufacturer_see_yaml_provenance",
            }
        )
    else:
        prov = ""
        rows.append(
            {
                "vehicle_key": vehicle_key,
                "config_path": path,
                "parameter": prefix,
                "value": obj,
                "units_or_note": prov,
                "observation_type": "see_yaml_nested_provenance",
            }
        )


def build_dt07() -> pd.DataFrame:
    rows: list[dict] = []
    for key, path in VEHICLES.items():
        if not path.exists():
            continue
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        rel = str(path.relative_to(ROOT)).replace("\\", "/")
        _flatten("", raw, rows, key, rel)
        # Highlight critical scalars with provenance tags when present
    df = pd.DataFrame(rows)

    # Refrigeration / cold-chain configs
    fridge_paths = list((ROOT / "configs").rglob("*tomato*")) + list(
        (ROOT / "configs").rglob("*pass2*")
    )
    fridge_rows = []
    for fp in sorted(set(fridge_paths)):
        if fp.suffix.lower() not in {".yaml", ".yml"}:
            continue
        try:
            raw = yaml.safe_load(fp.read_text(encoding="utf-8"))
        except Exception:
            continue
        fridge_rows.append(
            {
                "vehicle_key": "cold_chain",
                "config_path": str(fp.relative_to(ROOT)).replace("\\", "/"),
                "parameter": "file_root_keys",
                "value": ",".join(sorted(raw.keys())) if isinstance(raw, dict) else type(raw).__name__,
                "units_or_note": "tomato_firm_ripe_9C_headline",
                "observation_type": "assumed_research_cold_chain",
            }
        )
        if isinstance(raw, dict):
            for k in ("setpoint_c", "T_set_c", "setpoint_C", "UA_W_per_K", "COP", "precooled"):
                if k in raw:
                    fridge_rows.append(
                        {
                            "vehicle_key": "cold_chain",
                            "config_path": str(fp.relative_to(ROOT)).replace("\\", "/"),
                            "parameter": k,
                            "value": raw[k],
                            "units_or_note": "",
                            "observation_type": "assumed_research_cold_chain",
                        }
                    )
    return pd.concat([df, pd.DataFrame(fridge_rows)], ignore_index=True)


def build_inventory() -> pd.DataFrame:
    raw = yaml.safe_load(HEADLINE_YAML.read_text(encoding="utf-8"))
    missions = list(raw["demand_scenarios"]["corridor_eactros_equal"]["missions"])
    rows = []
    cell_id = 0
    for soc_scenario in SOC_SCENARIOS:
        for vehicle_key in PRIMARY_VEHICLE_KEYS:
            for infra_id, sites in INFRA:
                for m in missions:
                    od = m["od_id"]
                    stressed_soc = float(m["E_init_soc_frac"])
                    soc = 0.8 if soc_scenario == "common_soc_80" else stressed_soc
                    cell_id += 1
                    rows.append(
                        {
                            "cell_id": f"P1_{cell_id:03d}",
                            "block": "primary_comparison",
                            "soc_scenario": soc_scenario,
                            "vehicle_key": vehicle_key,
                            "infra_config_id": infra_id,
                            "installed": ",".join(sites),
                            "od_id": od,
                            "mission_yaml_id": m["id"],
                            "payload_kg": float(m["cargo_payload_kg"]),
                            "soc_frac": soc,
                            "stressed_soc_frac": stressed_soc,
                            "reserve": 0.1,
                            "q_kwh": 2,
                            "route_mode": "multi",
                            "max_seconds": 600,
                            "max_expansions": 2_000_000,
                            "refrigeration_on": True,
                            "terrain_mode": "dem",
                            "weather_id": m.get("weather_id"),
                            "reuse_path_a_if_fingerprint_match": (
                                vehicle_key == "eactros_600"
                                and soc_scenario == "stressed_mixed"
                            ),
                        }
                    )
    return pd.DataFrame(rows)


def main() -> None:
    TAB.mkdir(parents=True, exist_ok=True)
    MAN.mkdir(parents=True, exist_ok=True)
    EXP.mkdir(parents=True, exist_ok=True)

    dt07 = build_dt07()
    dt07.to_csv(TAB / "D-T07_vehicle_battery_refrig_charging_params.csv", index=False)

    inv = build_inventory()
    inv.to_csv(MAN / "scenario_inventory_primary.csv", index=False)
    inv.to_csv(EXP / "scenario_inventory_primary.csv", index=False)

    # Compact presentation: critical vehicle scalars
    crit = []
    for key, path in VEHICLES.items():
        if not path.exists():
            continue
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        bat = raw.get("battery", {})
        ch = raw.get("charging", {})
        aero = raw.get("aero", {})
        aux = raw.get("auxiliaries", {})
        crit.append(
            {
                "vehicle_key": key,
                "installed_kwh": bat.get("installed_kwh"),
                "usable_kwh": bat.get("usable_kwh"),
                "battery_provenance": bat.get("provenance"),
                "ccs_max_charge_kw": ch.get("ccs_max_charge_kw"),
                "CdA_m2": aero.get("CdA_m2"),
                "Crr": aero.get("Crr"),
                "P_aux_w": aux.get("P_aux_w"),
                "soc_min": (raw.get("soc") or {}).get("soc_min"),
                "cruise_kmh": (raw.get("speed_policy") or {}).get("cruise_kmh"),
                "config_path": str(path.relative_to(ROOT)).replace("\\", "/"),
            }
        )
    pd.DataFrame(crit).to_csv(TAB / "D-T07_vehicle_params_compact.csv", index=False)

    meta = {
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "n_primary_cells": int(len(inv)),
        "n_dt07_rows": int(len(dt07)),
        "vehicles": list(PRIMARY_VEHICLE_KEYS),
        "soc_scenarios": list(SOC_SCENARIOS),
        "infra": [i[0] for i in INFRA],
        "n_missions": int(inv["od_id"].nunique()),
    }
    (MAN / "scenario_inventory_meta.json").write_text(
        json.dumps(meta, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(meta, indent=2))


if __name__ == "__main__":
    main()
