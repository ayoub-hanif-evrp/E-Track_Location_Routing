"""Escalate B1 Settat casa_agadir LIMIT to conclusive OPTIMAL/INFEASIBLE if possible.

Does not claim HOS infeasibility while status remains LIMIT_REACHED.
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import run_stage_c_hos_national as stage_c  # noqa: E402

OUT = ROOT / "results" / "validation" / "path_a" / "limit_escalate"
SITE = {"y_settat_ca"}
# Higher expansions than standard 2e6 for this single disputed cell
MAX_EXP = 5_000_000
MAX_SEC = 1200.0


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    sha = (
        subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT).decode().strip()
    )
    orig = stage_c._patch_realistic_speed_policy()
    rows = []
    try:
        print(
            f"[escalate] casa_agadir settat 600→{MAX_SEC}s exp={MAX_EXP}",
            flush=True,
        )
        ev = stage_c._eval_installed_on_panel(
            vehicle_key="eactros_600",
            installed=set(SITE),
            route_mode="fixed",  # B conventional is fixed
            method_id="escalate_settat_casa_agadir_fixed",
            budget="B1",
            q=2,
            max_seconds=MAX_SEC,
            max_expansions=MAX_EXP,
            od_filter={"casa_agadir"},
            include_energy_only=True,
        )
        # Also multi-route on same Settat install
        ev2 = stage_c._eval_installed_on_panel(
            vehicle_key="eactros_600",
            installed=set(SITE),
            route_mode="multi",
            method_id="escalate_settat_casa_agadir_multi",
            budget="B1",
            q=2,
            max_seconds=MAX_SEC,
            max_expansions=MAX_EXP,
            od_filter={"casa_agadir"},
            include_energy_only=True,
        )
        for evx in (ev, ev2):
            for mr in evx["mission_rows"]:
                row = dict(mr)
                row["git_sha"] = sha
                row["max_expansions_requested"] = MAX_EXP
                row["interpretation"] = (
                    "conclusive"
                    if str(mr.get("status")).upper() in {"OPTIMAL", "INFEASIBLE"}
                    else "still_unresolved_LIMIT"
                )
                rows.append(row)
                print(
                    f"  {row['method_id']}: status={row.get('status')} "
                    f"ops={row.get('operationally_served')} "
                    f"energy={row.get('energy_feasible_energy_only')} "
                    f"→ {row['interpretation']}",
                    flush=True,
                )
        stage_c._write_csv(OUT / "settat_casa_agadir_escalate.csv", rows)
        (OUT / "run_fingerprint.json").write_text(
            json.dumps(
                {
                    "git_sha": sha,
                    "max_seconds": MAX_SEC,
                    "max_expansions": MAX_EXP,
                    "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
    finally:
        import morocco_etruck.optimization.multiroute_placement_evaluation as mpe

        mpe.load_multiroute_pilot_config = orig
    print(f"[escalate] wrote {OUT}", flush=True)


if __name__ == "__main__":
    main()
