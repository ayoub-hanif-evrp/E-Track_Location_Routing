#!/usr/bin/env python
"""Priority 6: southbound Benguerir sensitivity (Casa→Marrakech / Casa→Agadir)."""

from __future__ import annotations

import itertools
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from run_final_operational_correction import evaluate_mission_operational  # noqa: E402
import run_stage_c_hos_national as stage_c  # noqa: E402

OUT = ROOT / "results" / "validation" / "p6_sensitivity"
ODS = ("casa_marrakech", "casa_agadir")
SITE = {"y_benguerir_ca"}
SOCS = (0.5, 0.6, 0.7, 0.8, 1.0)
PAYLOADS = (5300.0, 10000.0, 15000.0)
Q = 2


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    orig = stage_c._patch_realistic_speed_policy()
    rows = []
    try:
        for od, soc, payload in itertools.product(ODS, SOCS, PAYLOADS):
            # Skip unrealistic heavy+low SOC extremes only if prep fails later
            print(f"[p6] {od} soc={soc} p={payload}", flush=True)
            cfg, vehicle, context, masks = stage_c._prepare_one(
                vehicle_key="eactros_600",
                od_id=od,
                payload=payload,
                soc=soc,
                q=Q,
            )
            mid = context["missions"][0].id
            prep = context["prepared"][mid]
            mask = frozenset(masks[mid]["all"])
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
                    "vehicle_key": "eactros_600",
                    "od_id": od,
                    "payload_kg": payload,
                    "soc_frac": soc,
                    "q": Q,
                    "installed": ",".join(sorted(SITE)),
                    "route_mode": "multi",
                    "git_sha": stage_c.SHA,
                    "pipeline": "p6_southbound_sensitivity",
                    "note": "not a calibrated real-world success probability",
                }
            )
            rows.append(row)
            stage_c._write_csv(OUT / "southbound_sensitivity.csv", rows)
            print(
                f"  status={row.get('status')} ops={row.get('operationally_served')} "
                f"min_soc={row.get('min_soc')}",
                flush=True,
            )
    finally:
        import morocco_etruck.optimization.multiroute_placement_evaluation as mpe

        mpe.load_multiroute_pilot_config = orig
    print(f"[p6] wrote {OUT} n={len(rows)}", flush=True)


if __name__ == "__main__":
    main()
