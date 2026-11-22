#!/usr/bin/env python
"""Priority 5: controlled q-grid for Agadir→Casa 15t SOC0.8 + Benguerir AC."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import run_stage_c_hos_national as stage_c  # noqa: E402

OUT = ROOT / "results" / "validation" / "p5_qgrid"
OD = "agadir_casa"
PAYLOAD = 15000.0
SOC = 0.8
SITE = {"y_benguerir_ac"}
QUANTA = (5, 2, 1)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    orig = stage_c._patch_realistic_speed_policy()
    rows = []
    try:
        for q in QUANTA:
            for mode in ("multi", "fixed"):
                print(f"[p5] q={q} mode={mode} {OD} p={PAYLOAD} soc={SOC}", flush=True)
                # Build one-OD eval manually to control payload/soc/q
                cfg, vehicle, context, masks = stage_c._prepare_one(
                    vehicle_key="eactros_600",
                    od_id=OD,
                    payload=PAYLOAD,
                    soc=SOC,
                    q=q,
                )
                mid = context["missions"][0].id
                prep = context["prepared"][mid]
                short = frozenset(masks[mid]["short"])
                all_mask = frozenset(masks[mid]["all"])
                mask = short if mode == "fixed" else all_mask
                from run_final_operational_correction import evaluate_mission_operational

                mr = evaluate_mission_operational(
                    prep=prep,
                    cfg=cfg,
                    installed=SITE,
                    mask=mask,
                    vehicle=vehicle,
                    fridge_path=stage_c.FRIDGE,
                    max_seconds=stage_c.UNIFORM_MAX_SECONDS,
                    max_expansions=int(cfg.solver_max_expansions),
                    include_energy_only=True,
                )
                row = dict(mr)
                row.update(
                    {
                        "vehicle_key": "eactros_600",
                        "od_id": OD,
                        "payload_kg": PAYLOAD,
                        "soc_frac": SOC,
                        "q": q,
                        "route_mode": mode,
                        "installed": ",".join(sorted(SITE)),
                        "short_subseteq_all": short <= all_mask,
                        "n_short": len(short),
                        "n_all": len(all_mask),
                        "git_sha": stage_c.SHA,
                        "pipeline": "p5_controlled_qgrid",
                    }
                )
                rows.append(row)
                print(
                    f"  status={row.get('status')} ops={row.get('operationally_served')} "
                    f"min_soc={row.get('min_soc')} energy={row.get('energy_feasible_energy_only')}",
                    flush=True,
                )
                stage_c._write_csv(OUT / "qgrid_controlled.csv", rows)
    finally:
        import morocco_etruck.optimization.multiroute_placement_evaluation as mpe

        mpe.load_multiroute_pilot_config = orig
    print(f"[p5] wrote {OUT}", flush=True)


if __name__ == "__main__":
    main()
