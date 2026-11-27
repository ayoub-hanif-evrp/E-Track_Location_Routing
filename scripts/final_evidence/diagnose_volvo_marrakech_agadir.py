#!/usr/bin/env python3
"""P0 — Controlled Volvo Marrakech→Agadir ops diagnosis.

Does NOT treat default/unevaluated ``daily_driving_ok=False`` as evidence.
Audits the energy-only trace and independently relaxes operational constraints.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Callable

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import run_stage_c_hos_national as stage_c  # noqa: E402
from run_final_operational_correction import evaluate_mission_operational  # noqa: E402

OUT = ROOT / "results/final_evidence/experiments/volvo_ops_diagnosis"
TAB = ROOT / "results/final_evidence/tables/results"
OD = "marrakech_agadir"
SOC = 0.8


def _as_bool_or_none(v: Any) -> bool | None:
    try:
        if v is None or pd.isna(v):
            return None
    except (TypeError, ValueError):
        pass
    if isinstance(v, str) and v.strip().lower() in {"", "none", "nan", "not_evaluated"}:
        return None
    return bool(v)


def _mechanism_from_row(r: dict[str, Any] | pd.Series) -> str:
    """Classify mechanism without mistaking unevaluated HOS defaults for violations."""
    status = str(r.get("status") or "")
    energy = str(r.get("energy_status") or "")
    ops = bool(r.get("operationally_served"))
    if ops:
        return "served"
    daily_ok = _as_bool_or_none(r.get("daily_driving_ok"))
    hos_ok = _as_bool_or_none(r.get("hos_ok"))
    drive_min = r.get("drive_min_phys")
    energy_drive = r.get("energy_drive_min")
    if status != "OPTIMAL" or (isinstance(drive_min, float) and pd.isna(drive_min)) or drive_min is None:
        # No ops trace ⇒ HOS fields were not audited.
        if energy == "OPTIMAL":
            return "energy_feasible_ops_infeasible_mechanism_unresolved"
        return f"ops_{status.lower()}_no_trace"
    if daily_ok is False:
        return "daily_driving_limit_audited"
    if hos_ok is False:
        return "continuous_or_break_hos_audited"
    return "ops_trace_present_but_unserved"


def _mut_relax_continuous(inst) -> None:
    ts = max(1, int(getattr(inst, "time_step_min", 5) or 5))
    inst.hos_max_continuous_driving_steps = int(round(24 * 60 / ts))


def _mut_relax_daily(inst) -> None:
    ts = max(1, int(getattr(inst, "time_step_min", 5) or 5))
    inst.hos_max_daily_driving_steps = int(round(24 * 60 / ts))


def _mut_relax_both_hos(inst) -> None:
    _mut_relax_continuous(inst)
    _mut_relax_daily(inst)


def _mut_expand_rest_nodes(inst) -> None:
    # All station keys + active stations + arc endpoints when exposed.
    nodes = {str(x) for x in (getattr(inst, "stations", {}) or {})} | {
        str(x) for x in (getattr(inst, "active_stations", ()) or ())
    }
    arcs_obj = getattr(inst, "arcs", None)
    if isinstance(arcs_obj, dict):
        iterable = list(arcs_obj.values())
    elif isinstance(arcs_obj, list):
        iterable = arcs_obj
    else:
        iterable = []
    for a in iterable:
        for key in ("u", "v", "from_node", "to_node", "node_u", "node_v"):
            if hasattr(a, key):
                nodes.add(str(getattr(a, key)))
            elif isinstance(a, dict) and key in a:
                nodes.add(str(a[key]))
    inst.hos_rest_nodes = frozenset(nodes)


def _mut_hos_off(inst) -> None:
    inst.hos_in_search = False


def _mut_short_break(inst) -> None:
    # Require only a 5-min stationary reset (eligibility / break severity probe).
    ts = max(1, int(getattr(inst, "time_step_min", 5) or 5))
    inst.hos_min_break_steps = max(1, int(round(5.0 / ts)))


ABLATIONS: list[tuple[str, Callable | None, str]] = [
    ("baseline_hos_in_search", None, "Policy baseline (HOS-in-search)"),
    ("relax_continuous_driving", _mut_relax_continuous, "Relax continuous-driving limit only"),
    ("relax_daily_driving", _mut_relax_daily, "Relax daily-driving limit only"),
    ("relax_continuous_and_daily", _mut_relax_both_hos, "Relax both HOS driving limits"),
    ("expand_rest_nodes", _mut_expand_rest_nodes, "Expand eligible break/rest locations"),
    ("short_break_requirement", _mut_short_break, "Shorten qualifying break duration"),
    ("hos_in_search_off", _mut_hos_off, "Disable HOS-in-search (energy/ops resource layer only)"),
]


def _row(label: str, mr: dict, **extra) -> dict:
    out = dict(mr)
    out.update(extra)
    out["diagnostic_label"] = label
    out["mechanism_hypothesis"] = _mechanism_from_row(out)
    return out


def _energy_trace_audit(mr: dict) -> dict:
    """Summarize energy-only driving duration / energy without claiming HOS violation."""
    tr = mr.get("energy_action_trace_json")
    actions = []
    if tr and not (isinstance(tr, float) and pd.isna(tr)):
        actions = json.loads(tr) if isinstance(tr, str) else tr
    drive_s = 0.0
    road_m = 0.0
    et = ea = er = eg = ech = 0.0
    for a in actions:
        typ = a.get("action_type") or a.get("type")
        dt = float(a.get("dt_s") or 0.0)
        if typ == "DRIVE":
            drive_s += dt
            road_m += float(a.get("length_m") or 0.0)
        et += float(a.get("E_traction_kwh") or 0)
        ea += float(a.get("E_aux_kwh") or 0)
        er += float(a.get("E_refrig_kwh") or 0)
        eg += float(a.get("E_regen_credit_kwh") or 0)
        if typ == "CHARGE":
            ech += float(a.get("charge_kwh") or a.get("E_charge_kwh") or 0)
    drive_min = drive_s / 60.0
    return {
        "energy_trace_drive_min": drive_min,
        "energy_trace_road_km": road_m / 1000.0,
        "energy_trace_n_actions": len(actions),
        "energy_trace_traction_kwh": et,
        "energy_trace_aux_kwh": ea,
        "energy_trace_refrig_kwh": er,
        "energy_trace_regen_kwh": eg,
        "energy_trace_charge_kwh": ech,
        "energy_trace_daily_driving_would_pass_9h": (
            drive_min <= 9.0 * 60.0 + 1e-9 if actions else None
        ),
        "energy_trace_continuous_screen_note": (
            "Energy-only itinerary ignores HOS-in-search; drive_min is physical "
            "duration under energy-optimal actions, not a continuous-driving audit."
        ),
    }


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    TAB.mkdir(parents=True, exist_ok=True)

    primary = pd.read_csv(
        ROOT / "results/final_evidence/experiments/primary_comparison/primary_missions.csv"
    )
    focus = primary[
        (primary.vehicle_key == "volvo_475")
        & (primary.od_id == OD)
        & (primary.soc_scenario == "common_soc_80")
    ].copy()
    # Correct unevaluated HOS defaults in the extracted focus slice
    no_trace = (focus["status"].astype(str) != "OPTIMAL") | focus["drive_min_phys"].isna()
    for col in ("hos_ok", "daily_driving_ok"):
        if col in focus.columns:
            focus.loc[no_trace, col] = pd.NA
    if "duty_scope" in focus.columns:
        focus.loc[no_trace, "duty_scope"] = "NOT_EVALUATED"
    focus.to_csv(OUT / "primary_focus_rows.csv", index=False)

    orig = stage_c._patch_realistic_speed_policy()
    rows: list[dict] = []
    energy_audit_rows: list[dict] = []
    try:
        payload = 5300.0
        for mdef in stage_c._corridor_missions():
            if mdef["od_id"] == OD:
                payload = float(mdef.get("cargo_payload_kg", 5300.0))
                break

        configs = [
            ("I0_none", set()),
            ("I1_benguerir_ca", {"y_benguerir_ca"}),
            ("I2_benguerir_larache", {"y_benguerir_ca", "y_larache_rt"}),
            ("I3_plus_benguerir_ac", {"y_benguerir_ca", "y_larache_rt", "y_benguerir_ac"}),
        ]

        cfg, vehicle, context, masks = stage_c._prepare_one(
            vehicle_key="volvo_475", od_id=OD, payload=payload, soc=SOC, q=2
        )
        mid = context["missions"][0].id
        prep = context["prepared"][mid]
        mask = frozenset(masks[mid]["all"])

        # Full infra baselines + energy-trace capture on I2
        for cfg_id, installed in configs:
            print(f"[volvo-diag] baseline {cfg_id}", flush=True)
            mr = evaluate_mission_operational(
                prep=prep,
                cfg=cfg,
                installed=set(installed),
                mask=mask,
                vehicle=vehicle,
                fridge_path=stage_c.FRIDGE,
                max_seconds=600.0,
                max_expansions=2_000_000,
                include_energy_only=True,
                capture_energy_trace=(cfg_id == "I2_benguerir_larache"),
            )
            row = _row(
                "baseline_hos_in_search",
                mr,
                infra_config_id=cfg_id,
                installed=",".join(sorted(installed)),
                od_id=OD,
                payload_kg=payload,
                soc_frac=SOC,
                vehicle_key="volvo_475",
                ablation_note="Policy baseline",
            )
            if cfg_id == "I2_benguerir_larache":
                audit = _energy_trace_audit(mr)
                row.update(audit)
                energy_audit_rows.append(
                    {
                        "od_id": OD,
                        "vehicle_key": "volvo_475",
                        "infra_config_id": cfg_id,
                        "energy_status": mr.get("energy_status"),
                        "ops_status": mr.get("status"),
                        **audit,
                    }
                )
            rows.append(row)
            print(
                f"  status={mr.get('status')} energy={mr.get('energy_status')} "
                f"hos_ok={mr.get('hos_ok')} daily_driving_ok={mr.get('daily_driving_ok')} "
                f"ops={mr.get('operationally_served')} mech={row['mechanism_hypothesis']}",
                flush=True,
            )

        # Controlled ablations on I2 only
        installed_i2 = {"y_benguerir_ca", "y_larache_rt"}
        for label, mut, note in ABLATIONS:
            if label == "baseline_hos_in_search":
                continue  # already recorded
            print(f"[volvo-diag] ablation {label}", flush=True)
            mr = evaluate_mission_operational(
                prep=prep,
                cfg=cfg,
                installed=set(installed_i2),
                mask=mask,
                vehicle=vehicle,
                fridge_path=stage_c.FRIDGE,
                max_seconds=600.0,
                max_expansions=2_000_000,
                include_energy_only=True,
                mutate_ops_instance=mut,
                capture_energy_trace=False,
            )
            rows.append(
                _row(
                    label,
                    mr,
                    infra_config_id="I2_benguerir_larache",
                    installed=",".join(sorted(installed_i2)),
                    od_id=OD,
                    payload_kg=payload,
                    soc_frac=SOC,
                    vehicle_key="volvo_475",
                    ablation_note=note,
                )
            )
            print(
                f"  status={mr.get('status')} ops={mr.get('operationally_served')} "
                f"hos_ok={mr.get('hos_ok')} daily={mr.get('daily_driving_ok')}",
                flush=True,
            )

        # eActros contrast I2
        print("[volvo-diag] eActros contrast I2", flush=True)
        cfg_e, veh_e, ctx_e, masks_e = stage_c._prepare_one(
            vehicle_key="eactros_600", od_id=OD, payload=payload, soc=SOC, q=2
        )
        mid_e = ctx_e["missions"][0].id
        mr_e = evaluate_mission_operational(
            prep=ctx_e["prepared"][mid_e],
            cfg=cfg_e,
            installed={"y_benguerir_ca", "y_larache_rt"},
            mask=frozenset(masks_e[mid_e]["all"]),
            vehicle=veh_e,
            fridge_path=stage_c.FRIDGE,
            max_seconds=600.0,
            max_expansions=2_000_000,
            include_energy_only=True,
            capture_energy_trace=True,
        )
        rows.append(
            _row(
                "eactros_contrast_I2",
                mr_e,
                infra_config_id="I2_benguerir_larache",
                installed="y_benguerir_ca,y_larache_rt",
                od_id=OD,
                payload_kg=payload,
                soc_frac=SOC,
                vehicle_key="eactros_600",
                ablation_note="eActros contrast under identical infra",
            )
        )
    finally:
        import morocco_etruck.optimization.multiroute_placement_evaluation as mpe

        mpe.load_multiroute_pilot_config = orig

    df = pd.DataFrame(rows)
    df.to_csv(OUT / "volvo_marrakech_agadir_diagnostics.csv", index=False)
    if energy_audit_rows:
        pd.DataFrame(energy_audit_rows).to_csv(OUT / "energy_only_trace_audit.csv", index=False)

    # Mechanism table
    mech = []
    for _, r in focus.iterrows():
        mech.append(
            {
                "source": "primary",
                "infra_config_id": r.infra_config_id,
                "diagnostic_label": "",
                "energy_status": r.energy_status,
                "status": r.status,
                "operationally_served": r.operationally_served,
                "hos_ok": r.get("hos_ok"),
                "daily_driving_ok": r.get("daily_driving_ok"),
                "audit_ok": r.get("audit_ok"),
                "drive_min_phys": r.get("drive_min_phys"),
                "energy_drive_min": None,
                "mechanism_hypothesis": _mechanism_from_row(r),
            }
        )
    for _, r in df.iterrows():
        mech.append(
            {
                "source": "diagnostic",
                "infra_config_id": r.get("infra_config_id"),
                "diagnostic_label": r.get("diagnostic_label"),
                "energy_status": r.get("energy_status"),
                "status": r.get("status"),
                "operationally_served": r.get("operationally_served"),
                "hos_ok": r.get("hos_ok"),
                "daily_driving_ok": r.get("daily_driving_ok"),
                "audit_ok": r.get("audit_ok"),
                "drive_min_phys": r.get("drive_min_phys"),
                "energy_drive_min": r.get("energy_drive_min"),
                "mechanism_hypothesis": r.get("mechanism_hypothesis"),
                "ablation_note": r.get("ablation_note"),
            }
        )
    mech_df = pd.DataFrame(mech)
    mech_df.to_csv(TAB / "R-T12_volvo_marrakech_agadir_ops_mechanism.csv", index=False)

    # Binding-mechanism synthesis from ablations
    abl = df[df.vehicle_key == "volvo_475"]
    served_abl = abl[abl.operationally_served == True]  # noqa: E712
    energy_drive = None
    if energy_audit_rows:
        energy_drive = energy_audit_rows[0].get("energy_trace_drive_min")
    daily_pass_on_energy = None
    if energy_audit_rows:
        daily_pass_on_energy = energy_audit_rows[0].get(
            "energy_trace_daily_driving_would_pass_9h"
        )

    labels = (
        sorted(served_abl.diagnostic_label.astype(str).unique()) if len(served_abl) else []
    )
    cont_only = "relax_continuous_driving" in labels
    daily_only = "relax_daily_driving" in labels
    rest_exp = "expand_rest_nodes" in labels
    if cont_only and not daily_only:
        binding = (
            "Binding mechanism (ablation evidence): continuous-driving / qualifying-break "
            "eligibility under HOS-in-search — not the Art.17 daily-driving limit. "
            f"Ops restored by: {', '.join(labels)}. "
            "Relaxing daily driving alone did not restore serviceability."
        )
        if rest_exp:
            binding += (
                " Expanding eligible rest nodes also restores ops, consistent with a "
                "break-location / continuous-driving interaction rather than a pure "
                "daily-driving exceedance."
            )
    elif len(served_abl):
        binding = (
            f"Ops restored under ablation(s): {', '.join(labels)}. "
            "Interpret the minimal successful relaxation as the binding family. "
            "Default/unevaluated daily_driving_ok must not be treated as evidence."
        )
    elif energy_drive is not None and daily_pass_on_energy is True:
        binding = (
            "Energy-feasible but infeasible under the modeled operational constraints; "
            "precise mechanism unresolved. Energy-only drive duration is within the 9 h "
            "daily-driving screen, so default/unevaluated daily_driving_ok=False must not "
            "be reported as the binding cause."
        )
    else:
        binding = (
            "Energy-feasible but infeasible under the modeled operational constraints; "
            "precise mechanism unresolved."
        )

    notes = [
        "# Volvo Marrakech→Agadir operational infeasibility",
        "",
        "## Corrected interpretation",
        "",
        "Primary / baseline ops solves return `status=INFEASIBLE` with **no action trace**.",
        "In that state, `hos_ok` and `daily_driving_ok` are **not evaluated** — they must not",
        "be reported as False evidence of a daily-driving (Art. 17) violation.",
        "",
        "Previous campaign text that named **daily driving** as the binding mechanism was",
        "incorrect: it read the early-return default, not an audited HOS computation.",
        "",
        "## Energy-only audit",
        "",
    ]
    if energy_audit_rows:
        ea = energy_audit_rows[0]
        notes.extend(
            [
                f"- Energy status: `{ea.get('energy_status')}`",
                f"- Energy-trace drive duration: **{ea.get('energy_trace_drive_min'):.2f} min**"
                if ea.get("energy_trace_drive_min") is not None
                else "- Energy-trace drive duration: n/a",
                f"- Energy-trace road distance: **{ea.get('energy_trace_road_km'):.2f} km**"
                if ea.get("energy_trace_road_km") is not None
                else "- Energy-trace road distance: n/a",
                f"- Would pass 9 h daily-driving screen on energy trace: `{daily_pass_on_energy}`",
                f"- Traction/aux/refrig/regen/charge kWh: "
                f"{ea.get('energy_trace_traction_kwh')}/"
                f"{ea.get('energy_trace_aux_kwh')}/"
                f"{ea.get('energy_trace_refrig_kwh')}/"
                f"{ea.get('energy_trace_regen_kwh')}/"
                f"{ea.get('energy_trace_charge_kwh')}",
                "",
            ]
        )
    notes.extend(
        [
            "## Controlled ablations (I2 Benguerir CA + Larache RT)",
            "",
            "Independently tested: continuous-driving relaxation, daily-driving relaxation,",
            "both, expanded rest nodes, shortened break requirement, and HOS-in-search off.",
            "",
            "## Binding mechanism",
            "",
            binding,
            "",
            "Modeled policy uses the campaign's single-duty HOS screen; this is not a full",
            "multi-day Art. 16 compliance certificate.",
            "",
        ]
    )
    (OUT / "mechanism_notes.md").write_text("\n".join(notes), encoding="utf-8")
    print(mech_df.to_string(index=False))
    print("\nBINDING:", binding)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
