#!/usr/bin/env python3
"""Final scientific closure: regenerate patched payload cells, extend HOS screen,
controlled charging comparison, and update authoritative tables.
"""
from __future__ import annotations

import dataclasses
import json
import math
import subprocess
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "scripts/final_evidence"))

import morocco_etruck.optimization.multiroute_placement_evaluation as mpe  # noqa: E402
import run_stage_c_hos_national as stage_c  # noqa: E402
from morocco_etruck.energy.vehicle import (  # noqa: E402
    load_vehicle,
    tapered_charge_session_minutes,
)
from run_final_operational_correction import evaluate_mission_operational  # noqa: E402

FE = ROOT / "results/final_evidence"
OUT_PAY = FE / "experiments/payload_conflict_p0"
OUT_TIME = FE / "experiments/time_discretization"
OUT_CHG = FE / "experiments/charging_taper_comparison"
TAB = FE / "tables/results"
FIG = FE / "figures/results"
SRC = FIG / "source_data"


def _sha() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT).decode().strip()
    except Exception:
        return "unknown"


def _actions(tr):
    if tr is None or (isinstance(tr, float) and pd.isna(tr)):
        return []
    return json.loads(tr) if isinstance(tr, str) else tr


def _eval_cell(
    *,
    vehicle_key: str,
    od: str,
    payload: float,
    soc: float,
    installed: set[str],
    q: int = 2,
    time_step_min: int | None = None,
    apply_taper: bool | None = None,
    label: str = "",
) -> dict:
    print(
        f"[closure] {label or od} {vehicle_key} p={payload} soc={soc} "
        f"ts={time_step_min} taper={apply_taper} sites={sorted(installed)}",
        flush=True,
    )
    orig_speed = stage_c._patch_realistic_speed_policy()
    orig_ts = None
    orig_taper = None
    try:
        if time_step_min is not None:
            base_loader = mpe.load_multiroute_pilot_config
            deadline = int(round(240 * 5 / float(time_step_min)))

            def wrapped(path, *, root=None):
                pilot = base_loader(path, root=root if root is not None else ROOT)
                return dataclasses.replace(
                    pilot,
                    time_step_min=int(time_step_min),
                    deadline_steps=int(deadline),
                )

            mpe.load_multiroute_pilot_config = wrapped
            orig_ts = base_loader

        cfg, vehicle, context, masks = stage_c._prepare_one(
            vehicle_key=vehicle_key,
            od_id=od,
            payload=payload,
            soc=soc,
            q=q,
        )
        mid = context["missions"][0].id
        taper_flag = True if apply_taper is None else bool(apply_taper)
        context["prepared"][mid].template.apply_charge_taper = taper_flag

        def _mutate_ops(inst):
            inst.apply_charge_taper = taper_flag

        mr = evaluate_mission_operational(
            prep=context["prepared"][mid],
            cfg=cfg,
            installed=set(installed),
            mask=frozenset(masks[mid]["all"]),
            vehicle=vehicle,
            fridge_path=stage_c.FRIDGE,
            max_seconds=stage_c.UNIFORM_MAX_SECONDS,
            max_expansions=stage_c.ABLATION_MAX_EXPANSIONS,
            include_energy_only=True,
            mutate_ops_instance=_mutate_ops,
        )
        row = dict(mr)
        row.update(
            {
                "label": label,
                "vehicle_key": vehicle_key,
                "od_id": od,
                "payload_kg": payload,
                "soc_frac": soc,
                "installed": ",".join(sorted(installed)),
                "q": q,
                "time_step_min": time_step_min if time_step_min is not None else 5,
                "apply_taper": taper_flag,
                "speed_patch": True,
                "git_sha": _sha(),
                "E_truck_init_kwh": int(round(soc * float(vehicle.usable_kwh))),
                "usable_kwh": float(vehicle.usable_kwh),
            }
        )
        print(
            f"  status={row.get('status')} energy={row.get('energy_status')} "
            f"ops={row.get('operationally_served')} min_soc={row.get('min_soc')} "
            f"charge={row.get('charge_min_phys')} wait={row.get('wait_min_phys')}",
            flush=True,
        )
        return row
    finally:
        mpe.load_multiroute_pilot_config = orig_speed
        stage_c._PREP_CACHE.clear()
        mpe.load_multiroute_pilot_config = orig_speed


def regenerate_heavier_payload() -> Path:
    """Authoritative heavier-payload cells WITH speed patch (P6 protocol)."""
    OUT_PAY.mkdir(parents=True, exist_ok=True)
    cells = [
        ("casa_marrakech", 5300.0, 0.5, set(), "I0"),
        ("casa_marrakech", 10000.0, 0.5, set(), "I0"),
        ("casa_marrakech", 5300.0, 0.5, {"y_benguerir_ca"}, "I1"),
        ("casa_marrakech", 10000.0, 0.5, {"y_benguerir_ca"}, "I1"),
        ("casa_marrakech", 15000.0, 0.5, {"y_benguerir_ca"}, "I1"),
        ("casa_agadir", 5300.0, 0.5, {"y_benguerir_ca"}, "I1"),
        ("casa_agadir", 10000.0, 0.5, {"y_benguerir_ca"}, "I1"),
        ("casa_agadir", 15000.0, 0.5, {"y_benguerir_ca"}, "I1"),
        ("casa_tangier", 5300.0, 0.8, {"y_benguerir_ca", "y_larache_rt"}, "I2"),
        ("casa_tangier", 10000.0, 0.8, {"y_benguerir_ca", "y_larache_rt"}, "I2"),
        ("agadir_casa", 5300.0, 0.5, {"y_benguerir_ac"}, "I1_ac"),
        ("agadir_casa", 10000.0, 0.5, {"y_benguerir_ac"}, "I1_ac"),
    ]
    rows = []
    path = OUT_PAY / "heavier_payload_speed_patched.csv"
    if path.exists():
        rows = pd.read_csv(path).to_dict(orient="records")
    done = {
        (r.get("od_id"), float(r.get("payload_kg") or 0), r.get("infra_label"), r.get("vehicle_key"))
        for r in rows
    }
    for od, payload, soc, installed, infra in cells:
        key = (od, float(payload), infra, "eactros_600")
        if key in done:
            continue
        # Fix loader restore carefully
        row = _eval_cell_safe(
            vehicle_key="eactros_600",
            od=od,
            payload=payload,
            soc=soc,
            installed=installed,
            label=f"payload_{int(payload)}_{infra}",
        )
        row["infra_label"] = infra
        row["pipeline"] = "closure_speed_patched_payload"
        row["authoritative"] = True
        rows.append(row)
        pd.DataFrame(rows).to_csv(path, index=False)
    pd.DataFrame(rows).to_csv(TAB / "R-T18_heavier_payload_infra.csv", index=False)
    # Mark invalid journal rows
    (OUT_PAY / "P0_invalid_journal_payload_note.md").write_text(
        "Journal `heavier_payload_infra_missions.csv` rows generated without "
        "`_patch_realistic_speed_policy` are **non-authoritative**. "
        "Use `heavier_payload_speed_patched.csv` / updated `R-T18_*` instead.\n",
        encoding="utf-8",
    )
    return path


def _eval_cell_safe(**kwargs) -> dict:
    """Evaluate with speed patch; restore loader exactly."""
    vehicle_key = kwargs["vehicle_key"]
    od = kwargs["od"]
    payload = kwargs["payload"]
    soc = kwargs["soc"]
    installed = kwargs["installed"]
    label = kwargs.get("label", "")
    time_step_min = kwargs.get("time_step_min")
    apply_taper = kwargs.get("apply_taper")
    print(
        f"[closure] {label or od} {vehicle_key} p={payload} soc={soc} "
        f"ts={time_step_min} taper={apply_taper}",
        flush=True,
    )
    # Capture true original loader
    true_orig = mpe.load_multiroute_pilot_config
    speed_orig = stage_c._patch_realistic_speed_policy()
    # After patch, loader is speed-wrapped; speed_orig is true original
    try:
        if time_step_min is not None:
            current = mpe.load_multiroute_pilot_config
            deadline = int(round(240 * 5 / float(time_step_min)))

            def ts_wrap(path, *, root=None):
                pilot = current(path, root=root if root is not None else ROOT)
                return dataclasses.replace(
                    pilot,
                    time_step_min=int(time_step_min),
                    deadline_steps=deadline,
                )

            mpe.load_multiroute_pilot_config = ts_wrap

        cfg, vehicle, context, masks = stage_c._prepare_one(
            vehicle_key=vehicle_key, od_id=od, payload=payload, soc=soc, q=2
        )
        mid = context["missions"][0].id
        taper_flag = True if apply_taper is None else bool(apply_taper)
        # Propagate into template so energy-only + ops clones inherit the model.
        context["prepared"][mid].template.apply_charge_taper = taper_flag

        def _mutate_ops(inst):
            inst.apply_charge_taper = taper_flag

        mr = evaluate_mission_operational(
            prep=context["prepared"][mid],
            cfg=cfg,
            installed=set(installed),
            mask=frozenset(masks[mid]["all"]),
            vehicle=vehicle,
            fridge_path=stage_c.FRIDGE,
            max_seconds=stage_c.UNIFORM_MAX_SECONDS,
            max_expansions=stage_c.ABLATION_MAX_EXPANSIONS,
            include_energy_only=True,
            mutate_ops_instance=_mutate_ops,
        )
        row = dict(mr)
        row.update(
            {
                "label": label,
                "vehicle_key": vehicle_key,
                "od_id": od,
                "payload_kg": payload,
                "soc_frac": soc,
                "installed": ",".join(sorted(installed)),
                "time_step_min": time_step_min if time_step_min is not None else 5,
                "apply_taper": taper_flag,
                "speed_patch": True,
                "git_sha": _sha(),
                "E_truck_init_kwh": int(round(soc * float(vehicle.usable_kwh))),
                "usable_kwh": float(vehicle.usable_kwh),
            }
        )
        print(
            f"  status={row.get('status')} energy={row.get('energy_status')} "
            f"ops={row.get('operationally_served')} min_soc={row.get('min_soc')} "
            f"chg={row.get('charge_min_phys')} wait={row.get('wait_min_phys')}",
            flush=True,
        )
        return row
    finally:
        # restore true original (unpatched) loader
        mpe.load_multiroute_pilot_config = speed_orig
        stage_c._PREP_CACHE.clear()


def continuous_driving_segments(trace) -> list[dict]:
    """Accumulate physical/discrete drive between qualifying CHARGE/WAIT/REST breaks."""
    acts = _actions(trace)
    segs = []
    phys = 0.0
    disc = 0.0
    n = 0
    start_idx = 0
    for i, a in enumerate(acts):
        typ = a.get("action_type") or a.get("type")
        if typ == "DRIVE":
            dt = float(a.get("dt_s") or 0) / 60.0
            phys += dt
            disc += math.ceil(dt / 5.0) * 5.0 if dt > 0 else 0.0
            n += 1
        elif typ in {"CHARGE", "WAIT", "REST", "BREAK"}:
            dt_stat = float(a.get("dt_s") or 0) / 60.0
            # qualifying unbroken break modeled as >=45 min stationary
            if dt_stat + 1e-9 >= 45.0 and n > 0:
                segs.append(
                    {
                        "seg_start_action": start_idx,
                        "seg_end_action": i,
                        "n_drive_arcs": n,
                        "phys_drive_min": phys,
                        "disc5_drive_min": disc,
                        "break_min": dt_stat,
                        "break_type": typ,
                        "near_270_phys": abs(270.0 - phys) <= 15.0 or phys > 255,
                        "near_270_disc": disc >= 270.0 - 1e-9,
                        "disc_exceeds_270": disc > 270.0 + 1e-9,
                        "phys_under_270": phys < 270.0 - 1e-9,
                    }
                )
                phys = disc = 0.0
                n = 0
                start_idx = i + 1
            elif n > 0 and dt_stat < 45.0:
                # short stop does not reset continuous driving under uninterrupted model
                pass
    if n > 0:
        segs.append(
            {
                "seg_start_action": start_idx,
                "seg_end_action": len(acts) - 1,
                "n_drive_arcs": n,
                "phys_drive_min": phys,
                "disc5_drive_min": disc,
                "break_min": 0.0,
                "break_type": "END",
                "near_270_phys": abs(270.0 - phys) <= 15.0 or phys > 255,
                "near_270_disc": disc >= 270.0 - 1e-9,
                "disc_exceeds_270": disc > 270.0 + 1e-9,
                "phys_under_270": phys < 270.0 - 1e-9,
            }
        )
    return segs


def extend_hos_screen() -> Path:
    OUT_TIME.mkdir(parents=True, exist_ok=True)
    panel = pd.read_csv(FE / "experiments/primary_i0_i3_panel/primary_i0_i3_missions.csv")
    settat = FE / "experiments/volvo_settat_vs_benguerir/volvo_settat_vs_benguerir_missions.csv"
    frames = [panel.assign(panel_source="primary_i0_i3_224")]
    if settat.exists():
        frames.append(pd.read_csv(settat).assign(panel_source="volvo_settat_benguerir_56"))
    # also payload robustness if present
    for extra, name in [
        (FE / "experiments/payload_soc/fine_soc_missions.csv", "fine_soc"),
        (FE / "experiments/robustness/headline_robustness_missions.csv", "robustness"),
    ]:
        if extra.exists():
            try:
                frames.append(pd.read_csv(extra).assign(panel_source=name))
            except Exception:
                pass
    rows = []
    for df in frames:
        for _, r in df.iterrows():
            served = r.get("operationally_served")
            status = str(r.get("status") or "")
            energy_ok = bool(r.get("energy_feasible")) if "energy_feasible" in df.columns else False
            # Prefer ops traces; for energy-OK/ops-INF use energy trace if present
            tr = r.get("action_trace_json")
            if (not served) and energy_ok:
                tr = r.get("energy_action_trace_json") or tr
            if tr is None or (isinstance(tr, float) and pd.isna(tr)):
                continue
            for s in continuous_driving_segments(tr):
                rows.append(
                    {
                        "panel_source": r.panel_source,
                        "vehicle_key": r.get("vehicle_key"),
                        "od_id": r.get("od_id"),
                        "soc_scenario": r.get("soc_scenario"),
                        "soc_frac": r.get("soc_frac"),
                        "infra_config_id": r.get("infra_config_id") or r.get("installed"),
                        "status": status,
                        "operationally_served": served,
                        "energy_feasible": r.get("energy_feasible"),
                        **s,
                        "affected_candidate": bool(
                            s["disc_exceeds_270"] and s["phys_under_270"]
                        )
                        or bool(s["near_270_disc"] and s["phys_under_270"]),
                    }
                )
    out = pd.DataFrame(rows)
    out.to_csv(OUT_TIME / "affected_case_inventory_224plus.csv", index=False)
    out.to_csv(TAB / "R-T14b_hos_segment_screen_224plus.csv", index=False)
    aff = out[out.affected_candidate == True]  # noqa: E712
    aff.to_csv(OUT_TIME / "affected_cases_near_270.csv", index=False)
    print(f"[P1] segment rows={len(out)} affected={len(aff)}")
    return OUT_TIME / "affected_case_inventory_224plus.csv"


def reevaluate_time_affected() -> Path:
    """Matched finer-ts reevals for priority cells."""
    OUT_TIME.mkdir(parents=True, exist_ok=True)
    cells = [
        # Volvo MA all infra
        ("volvo_475", "marrakech_agadir", 0.8, set(), "I0", [5, 2, 1]),
        ("volvo_475", "marrakech_agadir", 0.8, {"y_benguerir_ca"}, "I1", [5, 2, 1]),
        (
            "volvo_475",
            "marrakech_agadir",
            0.8,
            {"y_benguerir_ca", "y_larache_rt"},
            "I2",
            [5, 2, 1],
        ),
        (
            "volvo_475",
            "marrakech_agadir",
            0.8,
            {"y_benguerir_ca", "y_larache_rt", "y_benguerir_ac"},
            "I3",
            [5, 2, 1],
        ),
        # eActros Casa-Tangier I2/I3 both SOC
        (
            "eactros_600",
            "casa_tangier",
            0.5,
            {"y_benguerir_ca", "y_larache_rt"},
            "I2",
            [5, 2, 1],
        ),
        (
            "eactros_600",
            "casa_tangier",
            0.8,
            {"y_benguerir_ca", "y_larache_rt"},
            "I2",
            [5, 2, 1],
        ),
        (
            "eactros_600",
            "casa_tangier",
            0.5,
            {"y_benguerir_ca", "y_larache_rt", "y_benguerir_ac"},
            "I3",
            [5, 2, 1],
        ),
        (
            "eactros_600",
            "casa_tangier",
            0.8,
            {"y_benguerir_ca", "y_larache_rt", "y_benguerir_ac"},
            "I3",
            [5, 2, 1],
        ),
    ]
    path = OUT_TIME / "refined_time_matched_reevals.csv"
    rows = []
    if path.exists():
        rows = pd.read_csv(path).to_dict(orient="records")
    done = {
        (
            r.get("vehicle_key"),
            r.get("od_id"),
            float(r.get("soc_frac") or 0),
            r.get("infra_label"),
            int(r.get("time_step_min") or 0),
        )
        for r in rows
    }
    for vk, od, soc, installed, infra, tss in cells:
        for ts in tss:
            key = (vk, od, float(soc), infra, int(ts))
            if key in done:
                continue
            row = _eval_cell_safe(
                vehicle_key=vk,
                od=od,
                payload=5300.0,
                soc=soc,
                installed=installed,
                time_step_min=ts,
                label=f"{infra}_ts{ts}",
            )
            row["infra_label"] = infra
            # waiting analysis
            acts = _actions(row.get("action_trace_json"))
            wait = sum(
                float(a.get("dt_s") or 0)
                for a in acts
                if (a.get("action_type") or a.get("type")) == "WAIT"
            ) / 60.0
            charge = sum(
                float(a.get("dt_s") or 0)
                for a in acts
                if (a.get("action_type") or a.get("type")) == "CHARGE"
            ) / 60.0
            row["wait_min_from_trace"] = wait
            row["charge_min_from_trace"] = charge
            rows.append(row)
            pd.DataFrame(rows).to_csv(path, index=False)
    pd.DataFrame(rows).to_csv(TAB / "R-T14c_refined_time_matched_reevals.csv", index=False)
    return path


def charging_comparison(*, force: bool = True) -> Path:
    OUT_CHG.mkdir(parents=True, exist_ok=True)
    missions = [
        ("eactros_600", "casa_agadir", 0.5, {"y_benguerir_ca"}, "stressed"),
        ("eactros_600", "casa_agadir", 0.8, {"y_benguerir_ca"}, "common80"),
        ("volvo_475", "casa_agadir", 0.8, {"y_benguerir_ca"}, "common80"),
    ]
    path = OUT_CHG / "constant_vs_taper_missions.csv"
    # Prior runs monkeypatched the wrong symbol; force a clean re-eval.
    rows: list[dict] = []
    if path.exists() and not force:
        rows = pd.read_csv(path).to_dict(orient="records")
    done = {
        (
            r.get("vehicle_key"),
            r.get("od_id"),
            float(r.get("soc_frac") or 0),
            bool(r.get("apply_taper")),
        )
        for r in rows
        if r.get("charging_model_propagated")
    }
    for vk, od, soc, installed, tag in missions:
        for taper in (False, True):
            key = (vk, od, float(soc), taper)
            if key in done:
                continue
            row = _eval_cell_safe(
                vehicle_key=vk,
                od=od,
                payload=5300.0,
                soc=soc,
                installed=installed,
                apply_taper=taper,
                label=f"{tag}_{'taper' if taper else 'const'}",
            )
            row["soc_scenario_tag"] = tag
            row["charging_model_propagated"] = True
            acts = _actions(row.get("action_trace_json"))
            charges = [
                a
                for a in acts
                if (a.get("action_type") or a.get("type")) == "CHARGE"
            ]
            if charges:
                c0 = charges[0]
                soc0 = float(c0.get("soc_before") or float("nan"))
                soc1 = float(c0.get("soc_after") or float("nan"))
                ekwh = float(c0.get("charge_kwh") or 0)
                row["first_charge_soc_before"] = soc0
                row["first_charge_soc_after"] = soc1
                row["first_charge_kwh"] = ekwh
                row["first_charge_min"] = float(c0.get("dt_s") or 0) / 60.0
                row["first_charge_model"] = c0.get("charging_model")
                vpath = stage_c.VEHICLES[vk]
                v = load_vehicle(ROOT / vpath if not Path(vpath).is_absolute() else vpath)
                if soc0 == soc0 and soc1 == soc1 and soc1 > soc0:
                    offline = tapered_charge_session_minutes(
                        v, 350.0, soc_start=soc0, soc_end=soc1
                    )
                    row["offline_minutes_const"] = offline.get("minutes_constant")
                    row["offline_minutes_taper"] = offline.get("minutes_taper")
                    row["offline_battery_kwh"] = offline.get("battery_kwh")
            rows.append(row)
            pd.DataFrame(rows).to_csv(path, index=False)

    df = pd.DataFrame(rows)
    df.to_csv(path, index=False)
    df.to_csv(TAB / "R-T23_constant_vs_taper_charging.csv", index=False)

    # Identical start/target SOC continuous duration table (comparison 1)
    offline_rows = []
    for (vk, od, soc_f), g in df.groupby(["vehicle_key", "od_id", "soc_frac"]):
        g = g.set_index("apply_taper")
        if True not in g.index:
            continue
        tap = g.loc[True]
        offline_rows.append(
            {
                "vehicle_key": vk,
                "od_id": od,
                "soc_frac": soc_f,
                "soc_start": tap.get("first_charge_soc_before"),
                "soc_end": tap.get("first_charge_soc_after"),
                "energy_kwh": tap.get("first_charge_kwh"),
                "minutes_constant_continuous": tap.get("offline_minutes_const"),
                "minutes_taper_continuous": tap.get("offline_minutes_taper"),
                "minutes_reopt_constant_discrete": (
                    float(g.loc[False].get("charge_min_phys") or 0)
                    if False in g.index
                    else None
                ),
                "minutes_reopt_taper_discrete": tap.get("charge_min_phys"),
                "wait_reopt_constant": (
                    g.loc[False].get("wait_min_phys") if False in g.index else None
                ),
                "wait_reopt_taper": tap.get("wait_min_phys"),
                "journey_obj_constant": (
                    g.loc[False].get("objective") if False in g.index else None
                ),
                "journey_obj_taper": tap.get("objective"),
                "min_soc_constant": (
                    g.loc[False].get("min_soc") if False in g.index else None
                ),
                "min_soc_taper": tap.get("min_soc"),
                "ops_constant": (
                    g.loc[False].get("operationally_served")
                    if False in g.index
                    else None
                ),
                "ops_taper": tap.get("operationally_served"),
                "note": (
                    "Discrete 5-min ceil can mask continuous taper vs constant "
                    "differences; continuous offline minutes are authoritative "
                    "for identical SOC-interval duration."
                ),
            }
        )
    pd.DataFrame(offline_rows).to_csv(
        OUT_CHG / "identical_soc_interval_continuous.csv", index=False
    )
    pd.DataFrame(offline_rows).to_csv(
        TAB / "R-T23b_charging_identical_soc_interval.csv", index=False
    )

    (OUT_CHG / "P2_charging_comparison_notes.md").write_text(
        """# P2 — Controlled nonlinear charging comparison

## Charging model

- **Taper:** research envelope `conservative_ccs_taper_factor`
  (full ≤60% SOC; linear derate 60→80→95%).
- **Constant:** station∩vehicle nameplate power × η, no SOC derate.
- **Not** an empirically measured OEM curve.

## Propagation

`RoutingInstance.apply_charge_taper` is set on the prepared template and ops
instance; `apply_charge` records `charging_model` on each CHARGE action;
continuous replay uses the same flag when step counts are absent.

## Comparisons

1. **Identical SOC interval (continuous):** `identical_soc_interval_continuous.csv`
   / `R-T23b_*` — wall-clock minutes for the same soc_start→soc_end window.
2. **Reoptimized mission (discrete 5 min):** `constant_vs_taper_missions.csv`
   / `R-T23_*` — solver may choose the same discrete step count when continuous
   differences are smaller than the time quantum.

Matched otherwise: speed patch, HOS, terrain, payload 5300 kg, Benguerir CA, q=2.
""",
        encoding="utf-8",
    )
    return path


def update_payload_soc_tables() -> None:
    """Merge authoritative P6 southbound + speed-patched closure into R-T05."""
    p6 = pd.read_csv(ROOT / "results/validation/p6_sensitivity/southbound_sensitivity.csv")
    p6["source"] = "p6_southbound_sensitivity_speed_patched"
    p6["authoritative"] = True
    # closure patched heavier if available
    clo = OUT_PAY / "heavier_payload_speed_patched.csv"
    frames = [
        p6[
            [
                c
                for c in [
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
                    "drive_min_phys",
                    "wait_min_phys",
                    "source",
                    "authoritative",
                ]
                if c in p6.columns
            ]
        ]
    ]
    if clo.exists():
        c = pd.read_csv(clo)
        c["installed"] = c["installed"]
        c["source"] = "closure_speed_patched_payload"
        c["authoritative"] = True
        frames.append(
            c[
                [
                    x
                    for x in [
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
                        "drive_min_phys",
                        "wait_min_phys",
                        "source",
                        "authoritative",
                    ]
                    if x in c.columns
                ]
            ]
        )
    allp = pd.concat(frames, ignore_index=True)
    # Prefer p6 for overlapping southbound cells
    allp = allp.drop_duplicates(
        subset=["od_id", "payload_kg", "soc_frac", "installed"], keep="first"
    )
    allp.to_csv(TAB / "R-T05_payload_soc_feasibility.csv", index=False)
    SRC.mkdir(parents=True, exist_ok=True)
    allp.to_csv(SRC / "R-Fig4_payload_soc.csv", index=False)
    print(f"[P0/P6] updated R-T05 n={len(allp)}")


def main() -> int:
    TAB.mkdir(parents=True, exist_ok=True)
    print("=== extend HOS screen ===", flush=True)
    extend_hos_screen()
    print("=== regenerate heavier payload (speed patch) ===", flush=True)
    regenerate_heavier_payload()
    update_payload_soc_tables()
    print("=== refined time reevals ===", flush=True)
    reevaluate_time_affected()
    print("=== charging comparison ===", flush=True)
    charging_comparison()
    print("DONE closure core experiments", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
