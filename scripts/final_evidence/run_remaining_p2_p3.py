#!/usr/bin/env python3
"""Complete remaining P2/P3 experiments for final evidence campaign (resumable, sequential).

- Headline 5.3t fridge on/off + UA adverse
- Headline sensitivity (CdA/aux/weather/charger) + combined adverse packs
- Finer SOC brackets near known transitions
- Fixed vs flexible routing on I0/I1/I2 for eActros stressed panel subset
"""
from __future__ import annotations

import copy
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
from morocco_etruck.energy.vehicle import load_vehicle  # noqa: E402
from morocco_etruck.energy.refrigeration import load_refrigeration  # noqa: E402
from morocco_etruck.optimization.multiroute_adapter import (  # noqa: E402
    load_multiroute_pilot_config,
)
from morocco_etruck.optimization.multiroute_placement import (  # noqa: E402
    load_multiroute_placement_config,
)
from morocco_etruck.optimization.multiroute_placement_evaluation import (  # noqa: E402
    prepare_multiroute_placement_context,
)

OUT = ROOT / "results/final_evidence/experiments"
TOMATO = ROOT / "configs/energy/pass2_tomato_firm_ripe.yaml"
VEHICLE_YAML = Path(stage_c.VEHICLES["eactros_600"])
SITE = {"y_benguerir_ca"}
HEADLINE_CELLS = [
    ("casa_marrakech", 5300.0, 0.5),
    ("casa_agadir", 5300.0, 0.5),
    ("casa_tangier", 5300.0, 0.8),
]
FRIDGE_VARIANTS = [
    ("tomato_9C_on", {"refrigeration_on": True}),
    ("tomato_9C_off", {"refrigeration_on": False}),
    ("tomato_UA_x1p25", {"refrigeration_on": True, "ua_mult": 1.25}),
]
SENS_VARIANTS = [
    ("nominal", {}),
    ("aero_CdA_x1p1", {"cda_mult": 1.1}),
    ("aero_CdA_x0p9", {"cda_mult": 0.9}),
    ("crr_x1p2", {"crr_mult": 1.2}),
    ("aux_x1p25", {"aux_mult": 1.25}),
    ("aux_x0p75", {"aux_mult": 0.75}),
    ("charger_250kW", {"charger_kw": 250.0}),
    ("charger_350kW", {"charger_kw": 350.0}),
    ("weather_hot", {"weather": "hot"}),
]
ADVERSE = [
    ("adverse_hot_UA", {"weather": "hot", "ua_mult": 1.25, "refrigeration_on": True}),
    ("adverse_aero_aux", {"cda_mult": 1.1, "aux_mult": 1.25}),
    ("adverse_hot_charger250", {"weather": "hot", "charger_kw": 250.0, "ua_mult": 1.25}),
]

ROW_COLS = [
    "variant",
    "block",
    "od_id",
    "payload_kg",
    "soc_frac",
    "installed",
    "status",
    "energy_feasible",
    "operationally_served",
    "min_soc",
    "arrival_soc",
    "charge_min_phys",
    "wait_min_phys",
    "drive_min_phys",
    "objective",
    "charger_power_kw",
    "vehicle_CdA_m2",
    "vehicle_Crr",
    "vehicle_P_aux_w",
    "weather_id",
    "refrigeration_on",
    "setpoint_c",
    "E_traction_kwh",
    "E_aux_kwh",
    "E_refrig_kwh",
    "E_regen_credit_kwh",
    "git_sha",
    "pipeline",
    "drive_tables_rebaked",
    "action_trace_json",
]


def _sha() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT).decode().strip()
    except Exception:  # noqa: BLE001
        return "unknown"


def _write_vehicle(*, cda_mult=None, crr_mult=None, aux_mult=None) -> Path:
    raw = copy.deepcopy(yaml.safe_load(VEHICLE_YAML.read_text(encoding="utf-8")))
    if cda_mult is not None:
        raw["aero"]["CdA_m2"] = float(raw["aero"]["CdA_m2"]) * float(cda_mult)
    if crr_mult is not None:
        raw["aero"]["Crr"] = float(raw["aero"]["Crr"]) * float(crr_mult)
    if aux_mult is not None:
        raw["auxiliaries"]["P_aux_w"] = float(raw["auxiliaries"]["P_aux_w"]) * float(aux_mult)
    td = Path(tempfile.mkdtemp(prefix="fe_veh_"))
    out = td / "vehicle.yaml"
    out.write_text(yaml.safe_dump(raw, sort_keys=False), encoding="utf-8")
    return out


def _write_fridge(*, ua_mult=None, tag="fridge") -> Path:
    raw = copy.deepcopy(yaml.safe_load(TOMATO.read_text(encoding="utf-8")))
    if ua_mult is not None:
        raw["UA_w_per_k"] = float(raw["UA_w_per_k"]) * float(ua_mult)
    td = Path(tempfile.mkdtemp(prefix="fe_fr_"))
    out = td / f"{tag}.yaml"
    out.write_text(yaml.safe_dump(raw, sort_keys=False), encoding="utf-8")
    return out


def _prepare(
    *,
    od_id: str,
    payload: float,
    soc: float,
    vehicle_yaml: Path,
    fridge_yaml: Path,
    weather_id: str,
    charger_kw: float,
    refrigeration_on: bool,
    cache_tag: str,
):
    key = (
        "fe_p2",
        cache_tag,
        od_id,
        payload,
        soc,
        str(vehicle_yaml),
        str(fridge_yaml),
        weather_id,
        charger_kw,
        refrigeration_on,
    )
    if key in stage_c._PREP_CACHE:
        return stage_c._PREP_CACHE[key]
    cfg_path = stage_c._temp_demand_cfg(od_id, float(payload), float(soc))
    raw = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))
    for m in raw["demand_scenarios"]["frontier_cell"]["missions"]:
        m["weather_id"] = weather_id
        m["refrigeration_on"] = bool(refrigeration_on)
        m["terrain_mode"] = "dem"
    cfg_path = cfg_path.with_name(f"{cfg_path.stem}_{cache_tag}.yaml")
    cfg_path.write_text(yaml.safe_dump(raw), encoding="utf-8")
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
        fridge_yaml=fridge_yaml,
        charger_power_kw=float(charger_kw),
        max_alternatives_for_union=2,
        probe_serviceability=False,
    )
    prep0 = next(iter(context["prepared"].values()))
    for st in prep0.template.stations.values():
        assert abs(float(st.power_kw) - float(charger_kw)) < 1e-6
        break
    pilot = load_multiroute_pilot_config(cfg.multiroute_pilot_path, root=ROOT)
    path_rows = pd.read_csv(pilot.path_alternatives_csv).to_dict(orient="records")
    masks = stage_c._mission_masks(context, path_rows)
    out = (cfg, vehicle, context, masks)
    stage_c._PREP_CACHE[key] = out
    return out


def _normalize_row(row: dict) -> dict:
    out = {c: row.get(c) for c in ROW_COLS}
    return out


def _save_df(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame([_normalize_row(r) for r in rows], columns=ROW_COLS)
    df.to_csv(path, index=False)


def _load_good_robustness(path: Path) -> list[dict]:
    """Keep only well-formed rows from prior runs (reject corrupted parallel appends)."""
    if not path.exists() or path.stat().st_size == 0:
        return []
    df = pd.read_csv(path)
    need = {"od_id", "variant", "block", "status"}
    if not need.issubset(df.columns):
        return []
    # Valid blocks only
    ok_blocks = {"refrigeration", "sensitivity", "adverse"}
    df = df[df["block"].astype(str).isin(ok_blocks)].copy()
    df = df[df["od_id"].astype(str).isin({c[0] for c in HEADLINE_CELLS})]
    df = df.drop_duplicates(subset=["od_id", "variant", "block"], keep="last")
    return df.to_dict(orient="records")


def _eval_row(od, payload, soc, installed, variant, opts, sha, block):
    v_yaml = VEHICLE_YAML
    if any(k in opts for k in ("cda_mult", "crr_mult", "aux_mult")):
        v_yaml = _write_vehicle(
            cda_mult=opts.get("cda_mult"),
            crr_mult=opts.get("crr_mult"),
            aux_mult=opts.get("aux_mult"),
        )
    fridge = TOMATO
    if opts.get("ua_mult"):
        fridge = _write_fridge(ua_mult=opts["ua_mult"], tag=variant)
    weather = str(opts.get("weather") or "cool")
    chg = float(opts.get("charger_kw") or 350.0)
    ref_on = bool(opts.get("refrigeration_on", True))
    print(f"[{block}] {od} p={payload} soc={soc} {variant}", flush=True)
    cfg, vehicle, context, masks = _prepare(
        od_id=od,
        payload=payload,
        soc=soc,
        vehicle_yaml=v_yaml,
        fridge_yaml=fridge,
        weather_id=weather,
        charger_kw=chg,
        refrigeration_on=ref_on,
        cache_tag=f"{block}_{variant}",
    )
    mid = context["missions"][0].id
    mr = evaluate_mission_operational(
        prep=context["prepared"][mid],
        cfg=cfg,
        installed=set(installed),
        mask=frozenset(masks[mid]["all"]),
        vehicle=vehicle,
        fridge_path=fridge,
        max_seconds=stage_c.UNIFORM_MAX_SECONDS,
        max_expansions=stage_c.ABLATION_MAX_EXPANSIONS,
        include_energy_only=True,
    )
    row = dict(mr)
    tr = row.get("action_trace_json")
    et = ea = er = eg = None
    if tr and not (isinstance(tr, float)):
        actions = json.loads(tr) if isinstance(tr, str) else tr
        et = sum(float(a.get("E_traction_kwh") or 0) for a in actions)
        ea = sum(float(a.get("E_aux_kwh") or 0) for a in actions)
        er = sum(float(a.get("E_refrig_kwh") or 0) for a in actions)
        eg = sum(float(a.get("E_regen_credit_kwh") or 0) for a in actions)
    row.update(
        {
            "variant": variant,
            "block": block,
            "od_id": od,
            "payload_kg": payload,
            "soc_frac": soc,
            "installed": ",".join(sorted(installed)),
            "charger_power_kw": chg,
            "vehicle_CdA_m2": float(vehicle.CdA_m2),
            "vehicle_Crr": float(vehicle.Crr),
            "vehicle_P_aux_w": float(vehicle.P_aux_w),
            "weather_id": weather,
            "refrigeration_on": ref_on,
            "setpoint_c": float(load_refrigeration(fridge).setpoint_c),
            "E_traction_kwh": et,
            "E_aux_kwh": ea,
            "E_refrig_kwh": er,
            "E_regen_credit_kwh": eg,
            "git_sha": sha,
            "pipeline": f"final_evidence_{block}",
            "drive_tables_rebaked": True,
        }
    )
    print(
        f"  status={row.get('status')} ops={row.get('operationally_served')} "
        f"min_soc={row.get('min_soc')} refrig_kwh={er}",
        flush=True,
    )
    return row


def run_fridge_and_sensitivity(sha: str) -> pd.DataFrame:
    out_path = OUT / "robustness" / "headline_robustness_missions.csv"
    rows = _load_good_robustness(out_path)
    # Keep only fully complete OD blocks from casa_marrakech sequential run;
    # drop partial/corrupt parallel OD results and recompute them.
    good = []
    for r in rows:
        if r.get("od_id") == "casa_marrakech" and str(r.get("block")) in {
            "refrigeration",
            "sensitivity",
            "adverse",
        }:
            good.append(r)
    rows = good
    done = {(r["od_id"], r["variant"], r["block"]) for r in rows}
    _save_df(out_path, rows)
    print(f"robustness kept good rows={len(rows)}", flush=True)

    for od, payload, soc in HEADLINE_CELLS:
        for vname, opts in FRIDGE_VARIANTS:
            key = (od, vname, "refrigeration")
            if key in done:
                continue
            rows.append(_eval_row(od, payload, soc, SITE, vname, opts, sha, "refrigeration"))
            done.add(key)
            _save_df(out_path, rows)
        for vname, opts in SENS_VARIANTS:
            key = (od, vname, "sensitivity")
            if key in done:
                continue
            rows.append(_eval_row(od, payload, soc, SITE, vname, opts, sha, "sensitivity"))
            done.add(key)
            _save_df(out_path, rows)
        for vname, opts in ADVERSE:
            key = (od, vname, "adverse")
            if key in done:
                continue
            rows.append(_eval_row(od, payload, soc, SITE, vname, opts, sha, "adverse"))
            done.add(key)
            _save_df(out_path, rows)
    return pd.DataFrame([_normalize_row(r) for r in rows], columns=ROW_COLS)


def run_finer_soc(sha: str) -> pd.DataFrame:
    out_path = OUT / "payload_soc" / "fine_soc_missions.csv"
    rows: list[dict] = []
    if out_path.exists() and out_path.stat().st_size > 0:
        prev = pd.read_csv(out_path)
        if {"od_id", "payload_kg", "soc_frac", "installed", "status"}.issubset(prev.columns):
            rows = prev.to_dict(orient="records")
    done = {
        (r["od_id"], float(r["payload_kg"]), float(r["soc_frac"]), str(r.get("installed") or ""))
        for r in rows
    }
    cells = [
        ("casa_marrakech", 10000.0, [0.50, 0.52, 0.55, 0.58, 0.60], SITE),
        ("casa_agadir", 15000.0, [0.50, 0.52, 0.55, 0.58, 0.60], SITE),
        ("casa_marrakech", 10000.0, [0.50, 0.55, 0.60], set()),
        ("casa_agadir", 5300.0, [0.45, 0.50], SITE),
    ]
    print(f"fine SOC done={len(done)}", flush=True)
    for od, payload, socs, installed in cells:
        for soc in socs:
            key = (od, payload, soc, ",".join(sorted(installed)))
            if key in done:
                continue
            rows.append(
                _eval_row(
                    od,
                    payload,
                    soc,
                    installed,
                    f"soc_{soc:.2f}",
                    {},
                    sha,
                    "payload_soc_fine",
                )
            )
            done.add(key)
            _save_df(out_path, rows)
    return pd.DataFrame([_normalize_row(r) for r in rows], columns=ROW_COLS)


def run_fixed_vs_flex(sha: str) -> pd.DataFrame:
    out_dir = OUT / "fixed_vs_flex"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "fixed_vs_flex_missions.csv"
    flex_cols = [
        "od_id",
        "payload_kg",
        "soc_frac",
        "infra_config_id",
        "route_mode",
        "installed",
        "status",
        "energy_feasible",
        "operationally_served",
        "min_soc",
        "arrival_soc",
        "charge_min_phys",
        "wait_min_phys",
        "drive_min_phys",
        "objective",
        "vehicle_key",
        "git_sha",
        "pipeline",
    ]
    rows: list[dict] = []
    if out_path.exists() and out_path.stat().st_size > 0:
        prev = pd.read_csv(out_path)
        if {"od_id", "infra_config_id", "route_mode", "status"}.issubset(prev.columns):
            rows = prev.to_dict(orient="records")
    done = {(r["od_id"], r["infra_config_id"], r["route_mode"]) for r in rows}
    configs = [
        ("I0_none", set()),
        ("I1_benguerir_ca", {"y_benguerir_ca"}),
        ("I2_benguerir_larache", {"y_benguerir_ca", "y_larache_rt"}),
    ]
    ods = ["casa_agadir", "casa_tangier", "agadir_casa", "casa_marrakech"]
    print(f"fixed_vs_flex done={len(done)}", flush=True)
    orig = stage_c._patch_realistic_speed_policy()
    try:
        for cfg_id, installed in configs:
            for route_mode in ("fixed", "multi"):
                for od in ods:
                    key = (od, cfg_id, route_mode)
                    if key in done:
                        continue
                    print(f"[flex] {cfg_id} {route_mode} {od}", flush=True)
                    mdef = next(m for m in stage_c._corridor_missions() if m["od_id"] == od)
                    payload = float(mdef.get("cargo_payload_kg", 5300.0))
                    soc = float(mdef.get("E_init_soc_frac", 0.8))
                    cfg, vehicle, context, masks = stage_c._prepare_one(
                        vehicle_key="eactros_600", od_id=od, payload=payload, soc=soc, q=2
                    )
                    mid = context["missions"][0].id
                    mask = frozenset(masks[mid]["short" if route_mode == "fixed" else "all"])
                    mr = evaluate_mission_operational(
                        prep=context["prepared"][mid],
                        cfg=cfg,
                        installed=set(installed),
                        mask=mask,
                        vehicle=vehicle,
                        fridge_path=stage_c.FRIDGE,
                        max_seconds=600.0,
                        max_expansions=2_000_000,
                        include_energy_only=True,
                    )
                    row = dict(mr)
                    row.update(
                        {
                            "od_id": od,
                            "payload_kg": payload,
                            "soc_frac": soc,
                            "infra_config_id": cfg_id,
                            "route_mode": route_mode,
                            "installed": ",".join(sorted(installed)),
                            "vehicle_key": "eactros_600",
                            "git_sha": sha,
                            "pipeline": "final_evidence_fixed_vs_flex",
                        }
                    )
                    rows.append(row)
                    done.add(key)
                    print(
                        f"  status={row.get('status')} ops={row.get('operationally_served')}",
                        flush=True,
                    )
                    pd.DataFrame([{c: r.get(c) for c in flex_cols} for r in rows], columns=flex_cols).to_csv(
                        out_path, index=False
                    )
    finally:
        import morocco_etruck.optimization.multiroute_placement_evaluation as mpe

        mpe.load_multiroute_pilot_config = orig
    return pd.DataFrame([{c: r.get(c) for c in flex_cols} for r in rows], columns=flex_cols)


def main() -> int:
    sha = _sha()
    fp = {
        "git_sha": sha,
        "pipeline": "final_evidence_remaining_p2_p3",
        "fridge": str(TOMATO.relative_to(ROOT)).replace("\\", "/"),
        "mode": "sequential_resumable",
    }
    (OUT / "robustness").mkdir(parents=True, exist_ok=True)
    (OUT / "robustness" / "run_fingerprint.json").write_text(
        json.dumps(fp, indent=2) + "\n", encoding="utf-8"
    )

    orig = stage_c._patch_realistic_speed_policy()
    try:
        rob = run_fridge_and_sensitivity(sha)
        fine = run_finer_soc(sha)
    finally:
        import morocco_etruck.optimization.multiroute_placement_evaluation as mpe

        mpe.load_multiroute_pilot_config = orig

    flex = run_fixed_vs_flex(sha)
    print("robustness rows", len(rob), "fine", len(fine), "flex", len(flex), flush=True)
    print("DONE remaining P2/P3", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
