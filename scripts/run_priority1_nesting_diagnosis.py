#!/usr/bin/env python
"""Priority 1: diagnose route-nesting anomalies on violator ODs.

Writes under results/validation/p1_nesting/ without clobbering paper_campaign.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import run_stage_c_hos_national as stage_c  # noqa: E402

OUT = ROOT / "results" / "validation" / "p1_nesting"
VIOLATOR_ODS = {"casa_agadir", "casa_tangier"}


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    print(
        f"[p1] nesting diagnosis ods={sorted(VIOLATOR_ODS)} "
        f"max_seconds={stage_c.UNIFORM_MAX_SECONDS}",
        flush=True,
    )
    # eActros B2 only — the published anomaly surface.
    stage_c.ablation_live(
        budgets=("B2",),
        od_filter=VIOLATOR_ODS,
        vehicle_filter={"eactros_600"},
        out_dir=OUT,
    )
    # If any LIMIT_ARTIFACT remains, escalate expansions once.
    import pandas as pd

    ab = pd.read_csv(OUT / "placement_flexibility_ablation.csv")
    limits = ab[ab["nesting_class_on_C"] == "LIMIT_ARTIFACT"]
    if limits.empty:
        print("[p1] no LIMIT_ARTIFACT on C after 600s/500k — done", flush=True)
        return
    print(
        f"[p1] escalating {len(limits)} LIMIT_ARTIFACT rows to 2e6 expansions",
        flush=True,
    )
    escalate_dir = OUT / "escalate_2e6"
    escalate_dir.mkdir(parents=True, exist_ok=True)
    # Monkeypatch expansions via _eval by wrapping ablation corners manually.
    site_src = pd.read_csv(stage_c.OUT / "q2_critical_portfolio.csv")
    prow = site_src[
        (site_src.vehicle_key == "eactros_600") & (site_src.budget.astype(str) == "B2")
    ].iloc[0]
    c_sites = stage_c._parse_sites(prow.get("C_sites"))
    e_sites = stage_c._parse_sites(prow.get("E_sites"))
    rows = []
    missions = []
    orig = stage_c._patch_realistic_speed_policy()
    try:
        corners = {
            "fixed_on_C": ("fixed", c_sites),
            "multi_on_C": ("multi", c_sites),
            "fixed_on_E": ("fixed", e_sites),
            "multi_on_E": ("multi", e_sites),
        }
        corner_ev = {}
        for name, (mode, sites) in corners.items():
            print(f"[p1-escalate] {name} {sorted(sites)}", flush=True)
            corner_ev[name] = stage_c._eval_installed_on_panel(
                vehicle_key="eactros_600",
                installed=sites,
                route_mode=mode,
                method_id=f"escalate_{name}",
                budget="B2",
                q=2,
                max_seconds=stage_c.UNIFORM_MAX_SECONDS,
                max_expansions=2_000_000,
                od_filter=VIOLATOR_ODS,
            )
        by_od: dict = {}
        for name, ev in corner_ev.items():
            for mr in ev.get("mission_rows") or []:
                od = str(mr.get("od_id"))
                slot = by_od.setdefault(od, {})
                slot[name] = bool(mr.get("operationally_served"))
                slot[f"status_{name}"] = str(mr.get("status") or "")
                slot[f"solve_sec_{name}"] = mr.get("solve_sec")
                dump = dict(mr)
                dump["ablation_corner"] = name
                missions.append(dump)
        for od, flags in sorted(by_od.items()):
            nest_c = stage_c._classify_nesting_corner(
                ops_fixed=flags.get("fixed_on_C"),
                ops_multi=flags.get("multi_on_C"),
                status_fixed=flags.get("status_fixed_on_C"),
                status_multi=flags.get("status_multi_on_C"),
            )
            nest_e = stage_c._classify_nesting_corner(
                ops_fixed=flags.get("fixed_on_E"),
                ops_multi=flags.get("multi_on_E"),
                status_fixed=flags.get("status_fixed_on_E"),
                status_multi=flags.get("status_multi_on_E"),
            )
            rows.append(
                {
                    "vehicle_key": "eactros_600",
                    "budget": "B2",
                    "od_id": od,
                    "C_sites": ",".join(sorted(c_sites)),
                    "E_sites": ",".join(sorted(e_sites)),
                    "ops_fixed_on_C": flags.get("fixed_on_C"),
                    "ops_multi_on_C": flags.get("multi_on_C"),
                    "ops_fixed_on_E": flags.get("fixed_on_E"),
                    "ops_multi_on_E": flags.get("multi_on_E"),
                    "status_fixed_on_C": flags.get("status_fixed_on_C"),
                    "status_multi_on_C": flags.get("status_multi_on_C"),
                    "status_fixed_on_E": flags.get("status_fixed_on_E"),
                    "status_multi_on_E": flags.get("status_multi_on_E"),
                    "nesting_class_on_C": nest_c,
                    "nesting_class_on_E": nest_e,
                    "max_expansions": 2_000_000,
                    "git_sha": stage_c.SHA,
                }
            )
        stage_c._write_csv(escalate_dir / "placement_flexibility_ablation.csv", rows)
        stage_c._write_csv(
            escalate_dir / "placement_flexibility_ablation_missions.csv", missions
        )
        print(f"[p1-escalate] wrote {escalate_dir}", flush=True)
    finally:
        import morocco_etruck.optimization.multiroute_placement_evaluation as mpe

        mpe.load_multiroute_pilot_config = orig


if __name__ == "__main__":
    main()
