#!/usr/bin/env python
"""P6 extras: aero / aux / weather / charger-power with re-baked DRIVE tables.

Real charger_power_kw variation is passed into prepare (not a label-only stub).
"""
from __future__ import annotations

import copy
import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from run_final_operational_correction import evaluate_mission_operational  # noqa: E402
import run_stage_c_hos_national as stage_c  # noqa: E402
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

OUT = ROOT / "results" / "validation" / "p6_extras"
SITE = {"y_benguerir_ca"}
CELLS = [
    ("casa_marrakech", 15000.0, 0.8),
    ("casa_agadir", 15000.0, 0.8),
]
VEHICLE_YAML = Path(stage_c.VEHICLES["eactros_600"])


def _sha() -> str:
    try:
        return (
            subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT)
            .decode()
            .strip()
        )
    except Exception:  # noqa: BLE001
        return stage_c.SHA


def _write_variant_vehicle_yaml(
    *,
    cda_mult: float | None = None,
    aux_mult: float | None = None,
) -> Path:
    raw = yaml.safe_load(VEHICLE_YAML.read_text(encoding="utf-8"))
    raw = copy.deepcopy(raw)
    if cda_mult is not None:
        raw["aero"]["CdA_m2"] = float(raw["aero"]["CdA_m2"]) * float(cda_mult)
    if aux_mult is not None:
        raw["auxiliaries"]["P_aux_w"] = float(raw["auxiliaries"]["P_aux_w"]) * float(
            aux_mult
        )
    td = Path(tempfile.mkdtemp(prefix="p6_vehicle_"))
    out = td / "eactros_600_variant.yaml"
    out.write_text(yaml.safe_dump(raw, sort_keys=False), encoding="utf-8")
    return out


def _temp_demand_cfg_weather(
    od_id: str, payload: float, soc: float, weather_id: str
) -> Path:
    cfg_path = stage_c._temp_demand_cfg(od_id, float(payload), float(soc))
    raw = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))
    for m in raw["demand_scenarios"]["frontier_cell"]["missions"]:
        m["weather_id"] = weather_id
    out = cfg_path.with_name(f"{cfg_path.stem}_{weather_id}.yaml")
    out.write_text(yaml.safe_dump(raw), encoding="utf-8")
    return out


def _prepare_variant(
    *,
    od_id: str,
    payload: float,
    soc: float,
    vehicle_yaml: Path,
    weather_id: str = "cool",
    charger_power_kw: float = 350.0,
    cache_tag: str,
):
    key = (
        "p6x_rebake",
        cache_tag,
        od_id,
        float(payload),
        float(soc),
        2,
        str(vehicle_yaml.resolve()),
        weather_id,
        float(charger_power_kw),
    )
    if key in stage_c._PREP_CACHE:
        return stage_c._PREP_CACHE[key]

    cfg_path = _temp_demand_cfg_weather(od_id, float(payload), float(soc), weather_id)
    cfg = load_multiroute_placement_config(cfg_path, root=ROOT)
    vehicle = load_vehicle(vehicle_yaml)
    context = prepare_multiroute_placement_context(
        cfg,
        root=ROOT,
        demand_name="frontier_cell",
        energy_quantum_kwh=2,
        objective_mode="enroute_incremental_cost",
        vehicle_yaml=vehicle_yaml,
        road_cost_per_km=stage_c.ROAD_CENTS,
        fridge_yaml=stage_c.FRIDGE,
        charger_power_kw=float(charger_power_kw),
        max_alternatives_for_union=2,
        probe_serviceability=False,
    )
    # Sanity: station power must reflect charger_power_kw
    prep0 = next(iter(context["prepared"].values()))
    for st in prep0.template.stations.values():
        assert abs(float(st.power_kw) - float(charger_power_kw)) < 1e-6, (
            st.power_kw,
            charger_power_kw,
        )
        break

    pilot = load_multiroute_pilot_config(cfg.multiroute_pilot_path, root=ROOT)
    path_rows = pd.read_csv(pilot.path_alternatives_csv).to_dict(orient="records")
    masks = stage_c._mission_masks(context, path_rows)
    out = (cfg, vehicle, context, masks, float(charger_power_kw))
    stage_c._PREP_CACHE[key] = out
    return out


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    sha = _sha()
    orig = stage_c._patch_realistic_speed_policy()
    rows = []
    variants = [
        ("nominal", {}),
        ("aero_CdA_x1p1", {"cda_mult": 1.1}),
        ("aero_CdA_x0p9", {"cda_mult": 0.9}),
        ("aux_x1p25", {"aux_mult": 1.25}),
        ("aux_x0p75", {"aux_mult": 0.75}),
        ("charger_250kW", {"charger_kw": 250.0}),
        ("charger_350kW", {"charger_kw": 350.0}),
        ("weather_hot", {"weather": "hot"}),
    ]
    try:
        for od, payload, soc in CELLS:
            for vname, opts in variants:
                print(f"[p6x] {od} p={payload} soc={soc} {vname}", flush=True)
                v_yaml = VEHICLE_YAML
                if "cda_mult" in opts or "aux_mult" in opts:
                    v_yaml = _write_variant_vehicle_yaml(
                        cda_mult=opts.get("cda_mult"),
                        aux_mult=opts.get("aux_mult"),
                    )
                weather = str(opts.get("weather") or "cool")
                chg = float(opts.get("charger_kw") or 350.0)
                cfg, vehicle, context, masks, chg_used = _prepare_variant(
                    od_id=od,
                    payload=payload,
                    soc=soc,
                    vehicle_yaml=v_yaml,
                    weather_id=weather,
                    charger_power_kw=chg,
                    cache_tag=vname,
                )
                mid = context["missions"][0].id
                prep = context["prepared"][mid]
                # Verify vehicle physics fingerprint inputs changed when intended
                if "cda_mult" in opts:
                    assert abs(vehicle.CdA_m2 - 6.5 * float(opts["cda_mult"])) < 1e-9
                if "aux_mult" in opts:
                    assert abs(vehicle.P_aux_w - 2500.0 * float(opts["aux_mult"])) < 1e-6

                mr = evaluate_mission_operational(
                    prep=prep,
                    cfg=cfg,
                    installed=SITE,
                    mask=frozenset(masks[mid]["all"]),
                    vehicle=vehicle,
                    fridge_path=stage_c.FRIDGE,
                    max_seconds=stage_c.UNIFORM_MAX_SECONDS,
                    max_expansions=stage_c.ABLATION_MAX_EXPANSIONS,
                    include_energy_only=True,
                )
                row = dict(mr)
                row.update(
                    {
                        "variant": vname,
                        "od_id": od,
                        "payload_kg": payload,
                        "soc_frac": soc,
                        "installed": ",".join(sorted(SITE)),
                        "charger_power_kw": chg_used,
                        "vehicle_CdA_m2": float(vehicle.CdA_m2),
                        "vehicle_P_aux_w": float(vehicle.P_aux_w),
                        "weather_id": weather,
                        "git_sha": sha,
                        "pipeline": "p6_extras_rebake",
                        "drive_tables_rebaked": True,
                        "note": "re-baked DRIVE tables; charger_power_kw applied in prepare",
                    }
                )
                rows.append(row)
                stage_c._write_csv(OUT / "southbound_extras.csv", rows)
                print(
                    f"  status={row.get('status')} ops={row.get('operationally_served')} "
                    f"chg={chg_used} CdA={vehicle.CdA_m2:.3f} "
                    f"min_soc={row.get('min_soc')}",
                    flush=True,
                )
    finally:
        import morocco_etruck.optimization.multiroute_placement_evaluation as mpe

        mpe.load_multiroute_pilot_config = orig

    (OUT / "run_fingerprint.json").write_text(
        json.dumps(
            {
                "git_sha": sha,
                "pipeline": "p6_extras_rebake",
                "charger_variation": "real_prepare_override",
                "n_rows": len(rows),
                "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"[p6x] wrote {OUT} n={len(rows)}", flush=True)


if __name__ == "__main__":
    main()
