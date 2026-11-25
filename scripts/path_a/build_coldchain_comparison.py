"""Cold-chain reconciliation: tomato setpoint sources + fridge on/off/demand variants.

Headline commodity = firm-ripe fresh tomatoes. Campaign fridge YAML already uses
UNECE mid-band 9 °C (not +2 °C). This script:
1. Documents sourced setpoint ranges.
2. Re-evaluates critical cells with refrigeration_on True/False and UA demand variants
   with re-baked DRIVE tables.
"""
from __future__ import annotations

import copy
import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from run_final_operational_correction import evaluate_mission_operational  # noqa: E402
import run_stage_c_hos_national as stage_c  # noqa: E402
from morocco_etruck.energy.refrigeration import (  # noqa: E402
    load_refrigeration,
    tru_electrical_power_w,
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
import pandas as pd  # noqa: E402

OUT = ROOT / "results" / "validation" / "path_a" / "coldchain"
TOMATO = ROOT / "configs" / "energy" / "pass2_tomato_firm_ripe.yaml"
APPROX = ROOT / "configs" / "energy" / "refrigeration_approx.yaml"
SITE = {"y_benguerir_ca"}
# Feasible-regime cells where refrigeration load can change reserve (Benguerir installed)
CELLS = [
    ("casa_marrakech", 15000.0, 0.8),
    ("casa_agadir", 15000.0, 0.8),
]


def _sha() -> str:
    try:
        return (
            subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT)
            .decode()
            .strip()
        )
    except Exception:  # noqa: BLE001
        return "unknown"


def _write_fridge_variant(
    base: Path,
    *,
    setpoint_c: float | None = None,
    ua_mult: float | None = None,
    tag: str,
) -> Path:
    raw = yaml.safe_load(base.read_text(encoding="utf-8"))
    raw = copy.deepcopy(raw)
    if setpoint_c is not None:
        raw["setpoint_c"] = float(setpoint_c)
    if ua_mult is not None:
        raw["UA_w_per_k"] = float(raw["UA_w_per_k"]) * float(ua_mult)
    td = Path(tempfile.mkdtemp(prefix="fridge_var_"))
    out = td / f"{tag}.yaml"
    out.write_text(yaml.safe_dump(raw, sort_keys=False), encoding="utf-8")
    return out


def _prepare(
    *,
    od_id: str,
    payload: float,
    soc: float,
    fridge_yaml: Path,
    refrigeration_on: bool,
    cache_tag: str,
):
    key = ("cold", cache_tag, od_id, payload, soc, refrigeration_on, str(fridge_yaml))
    if key in stage_c._PREP_CACHE:
        return stage_c._PREP_CACHE[key]
    cfg_path = stage_c._temp_demand_cfg(od_id, float(payload), float(soc))
    raw = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))
    for m in raw["demand_scenarios"]["frontier_cell"]["missions"]:
        m["refrigeration_on"] = bool(refrigeration_on)
        m["commodity"] = "firm_ripe_fresh_tomatoes"
    out_cfg = cfg_path.with_name(f"{cfg_path.stem}_{cache_tag}.yaml")
    out_cfg.write_text(yaml.safe_dump(raw), encoding="utf-8")
    cfg = load_multiroute_placement_config(out_cfg, root=ROOT)
    vehicle = load_vehicle(stage_c.VEHICLES["eactros_600"])
    context = prepare_multiroute_placement_context(
        cfg,
        root=ROOT,
        demand_name="frontier_cell",
        energy_quantum_kwh=2,
        objective_mode="enroute_incremental_cost",
        vehicle_yaml=stage_c.VEHICLES["eactros_600"],
        road_cost_per_km=stage_c.ROAD_CENTS,
        fridge_yaml=fridge_yaml,
        charger_power_kw=350.0,
        max_alternatives_for_union=2,
        probe_serviceability=False,
    )
    pilot = load_multiroute_pilot_config(cfg.multiroute_pilot_path, root=ROOT)
    path_rows = pd.read_csv(pilot.path_alternatives_csv).to_dict(orient="records")
    masks = stage_c._mission_masks(context, path_rows)
    out = (cfg, vehicle, context, masks)
    stage_c._PREP_CACHE[key] = out
    return out


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    sha = _sha()
    tomato = load_refrigeration(TOMATO)
    approx = load_refrigeration(APPROX)

    # Sourced parameter table (documentation + computed TRU W)
    source_rows = [
        {
            "parameter": "setpoint_c",
            "headline_yaml": float(tomato.setpoint_c),
            "legacy_approx_yaml": float(approx.setpoint_c),
            "published_guidance": "UNECE ECE/TRADE/470 firm-ripe tomatoes ≈ 8–10 °C",
            "source_url": "https://unece.org/sites/default/files/2023-07/ECE_TRADE_470_E_web.pdf",
            "reconcile_note": (
                "Campaign FRIDGE=pass2_tomato_firm_ripe.yaml uses 9 °C mid-band. "
                "refrigeration_approx.yaml at +2 °C is NOT the tomato headline and "
                "must not be cited as commodity setpoint."
            ),
        },
        {
            "parameter": "UA_w_per_k",
            "headline_yaml": float(tomato.UA_w_per_k),
            "legacy_approx_yaml": float(approx.UA_w_per_k),
            "published_guidance": "order-of-magnitude insulated semi-trailer 50–120 W/K (assumed)",
            "source_url": "configs/energy/pass2_tomato_firm_ripe.yaml UA_sensitivity",
            "reconcile_note": "research assumption; not Thermo King calibrated",
        },
    ]
    for t_amb in (15.0, 25.0, 35.0):
        source_rows.append(
            {
                "parameter": f"tru_W_at_{int(t_amb)}C_amb",
                "headline_yaml": round(tru_electrical_power_w(t_amb, tomato), 1),
                "legacy_approx_yaml": round(tru_electrical_power_w(t_amb, approx), 1),
                "published_guidance": "few kW TRU electrical draw order-of-magnitude",
                "source_url": "UA–COP engineering model",
                "reconcile_note": "Wh = P*dt on DRIVE/CHARGE/WAIT when refrigeration_on",
            }
        )
    pd.DataFrame(source_rows).to_csv(OUT / "coldchain_parameter_sources.csv", index=False)

    variants = [
        ("tomato_9C_on", TOMATO, True, None, None),
        ("tomato_9C_off", TOMATO, False, None, None),
        ("tomato_UA_x1p25_on", None, True, None, 1.25),
        ("approx_2C_on_NOT_headline", APPROX, True, None, None),
    ]

    orig = stage_c._patch_realistic_speed_policy()
    rows = []
    try:
        for od, payload, soc in CELLS:
            for vname, fridge_path, ref_on, sp, ua_m in variants:
                if fridge_path is None:
                    fridge_path = _write_fridge_variant(
                        TOMATO, setpoint_c=sp, ua_mult=ua_m, tag=vname
                    )
                print(f"[cold] {od} p={payload} soc={soc} {vname}", flush=True)
                cfg, vehicle, context, masks = _prepare(
                    od_id=od,
                    payload=payload,
                    soc=soc,
                    fridge_yaml=fridge_path,
                    refrigeration_on=ref_on,
                    cache_tag=vname,
                )
                mid = context["missions"][0].id
                prep = context["prepared"][mid]
                # Verify mission refrigeration flag
                assert bool(getattr(context["missions"][0], "refrigeration_on", ref_on)) == ref_on
                mr = evaluate_mission_operational(
                    prep=prep,
                    cfg=cfg,
                    installed=SITE,
                    mask=frozenset(masks[mid]["all"]),
                    vehicle=vehicle,
                    fridge_path=fridge_path,
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
                        "refrigeration_on": ref_on,
                        "fridge_yaml": str(fridge_path),
                        "setpoint_c": float(load_refrigeration(fridge_path).setpoint_c),
                        "installed": ",".join(sorted(SITE)),
                        "git_sha": sha,
                        "pipeline": "path_a_coldchain_rebake",
                        "drive_tables_rebaked": True,
                    }
                )
                rows.append(row)
                stage_c._write_csv(OUT / "coldchain_variants.csv", rows)
                print(
                    f"  status={row.get('status')} ops={row.get('operationally_served')} "
                    f"energy={row.get('energy_feasible_energy_only')} "
                    f"min_soc={row.get('min_soc')}",
                    flush=True,
                )
    finally:
        import morocco_etruck.optimization.multiroute_placement_evaluation as mpe

        mpe.load_multiroute_pilot_config = orig

    # Difference summary: on vs off
    df = pd.DataFrame(rows)
    diffs = []
    for (od, payload, soc), g in df.groupby(["od_id", "payload_kg", "soc_frac"]):
        on = g[g["variant"] == "tomato_9C_on"]
        off = g[g["variant"] == "tomato_9C_off"]
        if on.empty or off.empty:
            continue
        on_r, off_r = on.iloc[0], off.iloc[0]
        diffs.append(
            {
                "od_id": od,
                "payload_kg": payload,
                "soc_frac": soc,
                "ops_on": bool(on_r.get("operationally_served")),
                "ops_off": bool(off_r.get("operationally_served")),
                "status_on": on_r.get("status"),
                "status_off": off_r.get("status"),
                "min_soc_on": on_r.get("min_soc"),
                "min_soc_off": off_r.get("min_soc"),
                "differs": bool(on_r.get("operationally_served"))
                != bool(off_r.get("operationally_served"))
                or (
                    on_r.get("min_soc") is not None
                    and off_r.get("min_soc") is not None
                    and abs(float(on_r["min_soc"]) - float(off_r["min_soc"])) > 1e-4
                ),
            }
        )
    pd.DataFrame(diffs).to_csv(OUT / "coldchain_on_vs_off_diff.csv", index=False)

    (OUT / "run_fingerprint.json").write_text(
        json.dumps(
            {
                "git_sha": sha,
                "fridge_headline": str(TOMATO.relative_to(ROOT)).replace("\\", "/"),
                "setpoint_headline_c": float(tomato.setpoint_c),
                "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                "n_rows": len(rows),
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (OUT / "coldchain_notes.md").write_text(
        "\n".join(
            [
                "# Cold-chain reconciliation",
                "",
                f"- Headline fridge: `{TOMATO.relative_to(ROOT).as_posix()}` setpoint "
                f"**{tomato.setpoint_c} °C** (UNECE firm-ripe tomato 8–10 °C mid-band).",
                f"- Legacy `{APPROX.name}` setpoint **{approx.setpoint_c} °C** is not the "
                "tomato commodity claim — keep for sensitivity only.",
                "- Variants re-bake DRIVE tables; compare refrigeration-on vs off and UA/setpoint bands.",
                "",
            ]
        ),
        encoding="utf-8",
    )
    print(f"[cold] wrote {OUT} n={len(rows)}", flush=True)


if __name__ == "__main__":
    main()
