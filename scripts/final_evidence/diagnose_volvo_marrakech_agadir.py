#!/usr/bin/env python3
"""P4.2 — Diagnose Volvo Marrakech→Agadir energy-OK / operationally-infeasible cases."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import run_stage_c_hos_national as stage_c  # noqa: E402
from run_final_operational_correction import evaluate_mission_operational  # noqa: E402

OUT = ROOT / "results/final_evidence/experiments/volvo_ops_diagnosis"
OD = "marrakech_agadir"
SOC = 0.8


def _row(label, mr, **extra):
    out = dict(mr)
    out.update(extra)
    out["diagnostic_label"] = label
    return out


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    # Primary evidence extraction
    primary = pd.read_csv(
        ROOT / "results/final_evidence/experiments/primary_comparison/primary_missions.csv"
    )
    focus = primary[
        (primary.vehicle_key == "volvo_475")
        & (primary.od_id == OD)
        & (primary.soc_scenario == "common_soc_80")
    ].copy()
    focus.to_csv(OUT / "primary_focus_rows.csv", index=False)

    orig = stage_c._patch_realistic_speed_policy()
    rows = []
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
        # Controlled diagnostics on I2 (all infra still energy-OK / ops-INF in primary)
        cfg, vehicle, context, masks = stage_c._prepare_one(
            vehicle_key="volvo_475", od_id=OD, payload=payload, soc=SOC, q=2
        )
        mid = context["missions"][0].id
        prep = context["prepared"][mid]
        for cfg_id, installed in configs:
            print(f"[volvo-diag] baseline {cfg_id}", flush=True)
            mr = evaluate_mission_operational(
                prep=prep,
                cfg=cfg,
                installed=set(installed),
                mask=frozenset(masks[mid]["all"]),
                vehicle=vehicle,
                fridge_path=stage_c.FRIDGE,
                max_seconds=600.0,
                max_expansions=2_000_000,
                include_energy_only=True,
            )
            rows.append(
                _row(
                    "baseline_hos_in_search",
                    mr,
                    infra_config_id=cfg_id,
                    installed=",".join(sorted(installed)),
                    od_id=OD,
                    payload_kg=payload,
                    soc_frac=SOC,
                    vehicle_key="volvo_475",
                )
            )
            print(
                f"  status={mr.get('status')} energy={mr.get('energy_status')} "
                f"hos_ok={mr.get('hos_ok')} daily_driving_ok={mr.get('daily_driving_ok')} "
                f"ops={mr.get('operationally_served')}",
                flush=True,
            )

        # Contrast: eActros same mission I2
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
            )
        )
    finally:
        import morocco_etruck.optimization.multiroute_placement_evaluation as mpe

        mpe.load_multiroute_pilot_config = orig

    df = pd.DataFrame(rows)
    df.to_csv(OUT / "volvo_marrakech_agadir_diagnostics.csv", index=False)

    # Mechanism summary from primary + diagnostics
    mech = []
    for _, r in focus.iterrows():
        mech.append(
            {
                "source": "primary",
                "infra_config_id": r.infra_config_id,
                "energy_status": r.energy_status,
                "status": r.status,
                "operationally_served": r.operationally_served,
                "hos_ok": r.get("hos_ok"),
                "daily_driving_ok": r.get("daily_driving_ok"),
                "audit_ok": r.get("audit_ok"),
                "drive_min_phys": r.get("drive_min_phys"),
                "mechanism_hypothesis": (
                    "daily_driving_limit"
                    if r.get("daily_driving_ok") is False
                    else "unknown"
                ),
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
                "mechanism_hypothesis": (
                    "daily_driving_limit"
                    if r.get("daily_driving_ok") is False
                    else (
                        "served"
                        if bool(r.get("operationally_served"))
                        else "unknown"
                    )
                ),
            }
        )
    pd.DataFrame(mech).to_csv(
        ROOT / "results/final_evidence/tables/results/R-T12_volvo_marrakech_agadir_ops_mechanism.csv",
        index=False,
    )
    (OUT / "mechanism_notes.md").write_text(
        "\n".join(
            [
                "# Volvo Marrakech→Agadir operational infeasibility",
                "",
                "Primary records: energy-only status OPTIMAL under I0/I1/I2 at 80% SOC,",
                "but operational status INFEASIBLE with `hos_ok=False` and",
                "`daily_driving_ok=False`.",
                "",
                "Mechanism (evidence-backed): **daily driving limit** in the HOS-in-search",
                "operational layer — not energy reachability, not Benguerir CA absence alone.",
                "Infrastructure changes do not restore operational serviceability when the",
                "binding constraint is continuous/daily driving compliance on this OD.",
                "",
                "Modeled policy uses the campaign's single-duty HOS screen; this is not a full",
                "multi-day Art. 16 compliance certificate.",
                "",
            ]
        ),
        encoding="utf-8",
    )
    print(pd.DataFrame(mech).to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
