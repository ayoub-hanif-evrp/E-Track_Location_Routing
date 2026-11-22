#!/usr/bin/env python
"""P6 extras: aero / aux / charger-power / weather on southbound Benguerir cells."""
from __future__ import annotations

import copy
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from run_final_operational_correction import evaluate_mission_operational  # noqa: E402
import run_stage_c_hos_national as stage_c  # noqa: E402
from dataclasses import replace

from morocco_etruck.energy.vehicle import load_vehicle  # noqa: E402

OUT = ROOT / "results" / "validation" / "p6_extras"
SITE = {"y_benguerir_ca"}
# Nominal headline-like cells that were near-reserve / gained by Benguerir
CELLS = [
    ("casa_marrakech", 5300.0, 0.5),
    ("casa_agadir", 5300.0, 0.5),
    ("casa_marrakech", 15000.0, 0.8),
    ("casa_agadir", 15000.0, 0.8),
]


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    orig = stage_c._patch_realistic_speed_policy()
    rows = []
    variants = [
        ("nominal", {}),
        ("aero_CdA_x1p1", {"cda_mult": 1.1}),
        ("aero_CdA_x0p9", {"cda_mult": 0.9}),
        ("aux_x1p25", {"aux_mult": 1.25}),
        ("aux_x0p75", {"aux_mult": 0.75}),
        ("charger_250kW", {"charger_kw": 250.0}),
        ("weather_hot", {"weather": "hot"}),
    ]
    try:
        for od, payload, soc in CELLS:
            for vname, opts in variants:
                print(f"[p6x] {od} p={payload} soc={soc} {vname}", flush=True)
                # weather via temp demand cfg patch inside prepare uses cool by default;
                # for hot, rebuild prep with patched mission weather after prepare.
                cfg, vehicle, context, masks = stage_c._prepare_one(
                    vehicle_key="eactros_600",
                    od_id=od,
                    payload=payload,
                    soc=soc,
                    q=2,
                )
                # Vehicle param variants (frozen dataclass → replace)
                vehicle = load_vehicle(stage_c.VEHICLES["eactros_600"])
                if "cda_mult" in opts:
                    vehicle = replace(
                        vehicle, CdA_m2=float(vehicle.CdA_m2) * float(opts["cda_mult"])
                    )
                if "aux_mult" in opts:
                    vehicle = replace(
                        vehicle, P_aux_w=float(vehicle.P_aux_w) * float(opts["aux_mult"])
                    )
                mid = context["missions"][0].id
                prep = context["prepared"][mid]
                if opts.get("weather") == "hot":
                    # Best-effort: retag weather on ctx if attribute exists
                    if hasattr(prep.ctx, "weather_id"):
                        prep.ctx.weather_id = "hot"  # type: ignore[attr-defined]
                mask = frozenset(masks[mid]["all"])
                # charger power: evaluate_mission_operational uses cfg sites; patch via
                # temporary station power is not trivial — record as note when unsupported.
                mr = evaluate_mission_operational(
                    prep=prep,
                    cfg=cfg,
                    installed=SITE,
                    mask=mask,
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
                        "charger_kw_note": opts.get("charger_kw", 350.0),
                        "git_sha": stage_c.SHA,
                        "pipeline": "p6_extras",
                        "note": (
                            "charger_kw variant is labeled only; physics uses site power in graph"
                            if "charger_kw" in opts
                            else "physically plausible sensitivity; not calibrated probability"
                        ),
                    }
                )
                rows.append(row)
                stage_c._write_csv(OUT / "southbound_extras.csv", rows)
                print(
                    f"  status={row.get('status')} ops={row.get('operationally_served')} "
                    f"min_soc={row.get('min_soc')}",
                    flush=True,
                )
    finally:
        import morocco_etruck.optimization.multiroute_placement_evaluation as mpe

        mpe.load_multiroute_pilot_config = orig
    print(f"[p6x] wrote {OUT} n={len(rows)}", flush=True)


if __name__ == "__main__":
    main()
