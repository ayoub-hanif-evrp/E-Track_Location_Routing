#!/usr/bin/env python3
"""P0 — Reconcile eActros Casa–Agadir 10 t @50% Benguerir CA conflict.

Historical P6 (with realistic speed patch): OPTIMAL / ops served.
Journal P4 (_eval_row without speed patch): energy OPTIMAL / ops INFEASIBLE.
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "scripts/final_evidence"))

import run_stage_c_hos_national as stage_c  # noqa: E402
from run_final_operational_correction import evaluate_mission_operational  # noqa: E402
import morocco_etruck.optimization.multiroute_placement_evaluation as mpe  # noqa: E402

OUT = ROOT / "results/final_evidence/experiments/payload_conflict_p0"
TAB = ROOT / "results/final_evidence/tables/results"
SITE = {"y_benguerir_ca"}
OD = "casa_agadir"
PAYLOAD = 10000.0
SOC = 0.5
Q = 2


def _drive_mins(trace) -> float:
    if trace is None or (isinstance(trace, float) and pd.isna(trace)):
        return float("nan")
    acts = json.loads(trace) if isinstance(trace, str) else trace
    return sum(float(a.get("dt_s") or 0) for a in acts if (a.get("action_type") or a.get("type")) == "DRIVE") / 60.0


def _disc_ceil_mins(trace, ts_min: float = 5.0) -> float:
    if trace is None or (isinstance(trace, float) and pd.isna(trace)):
        return float("nan")
    acts = json.loads(trace) if isinstance(trace, str) else trace
    total = 0.0
    for a in acts:
        if (a.get("action_type") or a.get("type")) != "DRIVE":
            continue
        dt_min = float(a.get("dt_s") or 0) / 60.0
        total += math.ceil(dt_min / ts_min) * ts_min if dt_min > 0 else 0.0
    return total


def _eval(*, use_speed_patch: bool, label: str) -> dict:
    print(f"[P0] eval {label} speed_patch={use_speed_patch}", flush=True)
    orig = None
    if use_speed_patch:
        orig = stage_c._patch_realistic_speed_policy()
    try:
        cfg, vehicle, context, masks = stage_c._prepare_one(
            vehicle_key="eactros_600",
            od_id=OD,
            payload=PAYLOAD,
            soc=SOC,
            q=Q,
        )
        mid = context["missions"][0].id
        prep = context["prepared"][mid]
        pilot = mpe.load_multiroute_pilot_config(cfg.multiroute_pilot_path, root=ROOT)
        sp = dict(pilot.speed_policy)
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
                "label": label,
                "use_speed_patch": use_speed_patch,
                "od_id": OD,
                "payload_kg": PAYLOAD,
                "soc_frac": SOC,
                "q": Q,
                "installed": "y_benguerir_ca",
                "vehicle_key": "eactros_600",
                "speed_adapt_peak": sp.get("adapt_speed_to_peak_power"),
                "speed_adapt_cont": sp.get("adapt_speed_to_continuous_power"),
                "min_adapt_speed_kmh": sp.get("min_adapt_speed_kmh"),
                "cruise_kmh": sp.get("cruise_kmh"),
                "E_truck_init_kwh": int(round(SOC * float(vehicle.usable_kwh))),
                "usable_kwh": float(vehicle.usable_kwh),
                "drive_min_phys_trace": _drive_mins(row.get("action_trace_json")),
                "drive_min_disc5_trace": _disc_ceil_mins(row.get("action_trace_json"), 5.0),
            }
        )
        print(
            f"  status={row.get('status')} energy={row.get('energy_status')} "
            f"ops={row.get('operationally_served')} drive={row.get('drive_min_phys')} "
            f"disc5={row.get('drive_min_disc5_trace')} adapt_peak={sp.get('adapt_speed_to_peak_power')}",
            flush=True,
        )
        return row
    finally:
        if orig is not None:
            mpe.load_multiroute_pilot_config = orig
        stage_c._PREP_CACHE.clear()


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    TAB.mkdir(parents=True, exist_ok=True)

    hist = pd.read_csv(ROOT / "results/validation/p6_sensitivity/southbound_sensitivity.csv")
    h = hist[(hist.od_id == OD) & (hist.payload_kg == PAYLOAD) & (hist.soc_frac == SOC)].iloc[0]
    journal = pd.read_csv(
        ROOT / "results/final_evidence/experiments/journal_p2_p4/heavier_payload_infra_missions.csv"
    )
    j = journal[(journal.od_id == OD) & (journal.payload_kg == PAYLOAD)].iloc[0]

    rows = []
    rows.append(_eval(use_speed_patch=True, label="current_with_p6_speed_patch"))
    rows.append(_eval(use_speed_patch=False, label="current_without_speed_patch"))

    # Historical metrics
    rows.append(
        {
            "label": "historical_p6_record",
            "use_speed_patch": True,
            "od_id": OD,
            "payload_kg": PAYLOAD,
            "soc_frac": SOC,
            "status": h.status,
            "energy_status": h.get("energy_status"),
            "energy_feasible": h.energy_feasible,
            "operationally_served": h.operationally_served,
            "min_soc": h.min_soc,
            "charge_min_phys": h.charge_min_phys,
            "drive_min_phys": h.drive_min_phys,
            "wait_min_phys": h.wait_min_phys,
            "drive_min_phys_trace": _drive_mins(h.action_trace_json),
            "drive_min_disc5_trace": _disc_ceil_mins(h.action_trace_json, 5.0),
            "pipeline": "p6_southbound_sensitivity",
        }
    )
    rows.append(
        {
            "label": "journal_p4_record",
            "use_speed_patch": False,
            "od_id": OD,
            "payload_kg": PAYLOAD,
            "soc_frac": SOC,
            "status": j.status,
            "energy_status": j.energy_status,
            "energy_feasible": j.energy_feasible,
            "operationally_served": j.operationally_served,
            "pipeline": j.pipeline,
            "note": "journal _eval_row omitted _patch_realistic_speed_policy",
        }
    )

    df = pd.DataFrame(rows)
    df.to_csv(OUT / "casa_agadir_10t_conflict_comparison.csv", index=False)
    df.to_csv(TAB / "R-T22_payload10t_conflict_reconciliation.csv", index=False)

    # Mechanism verdict
    with_patch = next(r for r in rows if r["label"] == "current_with_p6_speed_patch")
    without = next(r for r in rows if r["label"] == "current_without_speed_patch")
    mechanism = []
    mechanism.append("# P0 — Payload 10 t conflict reconciliation")
    mechanism.append("")
    mechanism.append("## Mission")
    mechanism.append(
        "eActros 600 · Casa–Agadir · 10 000 kg · 50% SOC · Benguerir CA · q=2 kWh"
    )
    mechanism.append("")
    mechanism.append("## Observed disagreement")
    mechanism.append(
        f"- Historical P6: status={h.status}, ops={h.operationally_served}, "
        f"drive={h.drive_min_phys:.2f} min, charge={h.charge_min_phys}, min_soc={h.min_soc:.4f}"
    )
    mechanism.append(
        f"- Journal P4: status={j.status}, energy={j.energy_status}, ops={j.operationally_served}"
    )
    mechanism.append("")
    mechanism.append("## Controlled re-runs (current code)")
    mechanism.append(
        f"- **With** `_patch_realistic_speed_policy` (adapt_peak=True): "
        f"status={with_patch.get('status')} ops={with_patch.get('operationally_served')} "
        f"drive={with_patch.get('drive_min_phys')} disc5≈{with_patch.get('drive_min_disc5_trace')} "
        f"adapt_peak={with_patch.get('speed_adapt_peak')}"
    )
    mechanism.append(
        f"- **Without** speed patch: "
        f"status={without.get('status')} energy={without.get('energy_status')} "
        f"ops={without.get('operationally_served')} drive={without.get('drive_min_phys')} "
        f"disc5≈{without.get('drive_min_disc5_trace')} "
        f"adapt_peak={without.get('speed_adapt_peak')}"
    )
    mechanism.append("")
    if (
        bool(with_patch.get("operationally_served"))
        and not bool(without.get("operationally_served"))
        and bool(without.get("energy_feasible"))
    ):
        verdict = (
            "DISCREPANCY RESOLVED: different **effective speed-policy preparation**. "
            "Primary/P6 protocol applies `_patch_realistic_speed_policy` "
            "(adapt_speed_to_peak_power=True with min adapt floor). "
            "Journal P4 `_eval_row` omitted this patch, yielding energy-feasible but "
            "operationally infeasible HOS outcomes under slower/unadapted climb speeds "
            "and/or different drive-time discretization. "
            "**Authoritative result for Path A:** P6 / speed-patched OPTIMAL "
            f"(drive≈{h.drive_min_phys:.2f} min, charge={h.charge_min_phys} min, "
            f"min_soc≈{float(h.min_soc):.4f}). "
            "Journal heavier-payload INFEASIBLE rows that omitted the patch are "
            "**not** scientifically comparable and must be regenerated or labeled invalid."
        )
    elif bool(with_patch.get("operationally_served")) == bool(h.operationally_served):
        verdict = (
            "Current speed-patched re-run agrees with historical P6. "
            "Journal P4 without patch is non-authoritative for this cell."
        )
    else:
        verdict = (
            "UNRESOLVED: speed-patch alone does not fully restore agreement; "
            "see comparison CSV for remaining diffs."
        )
    mechanism.append("## Verdict")
    mechanism.append(verdict)
    mechanism.append("")
    mechanism.append("## Scientific rule")
    mechanism.append(
        "Do not prefer the higher-feasibility number. Use the **matched primary protocol** "
        "(realistic speed patch + tomato fridge + cool weather + q=2) for payload frontiers."
    )
    (OUT / "P0_payload10t_conflict_notes.md").write_text("\n".join(mechanism) + "\n", encoding="utf-8")
    print(verdict)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
