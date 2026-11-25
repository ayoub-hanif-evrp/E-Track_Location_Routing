#!/usr/bin/env python
"""Path A correction: matched multi-route infrastructure ladder at 600s / 2e6.

Configs (identical code/protocol):
  I0 = no sites
  I1 = {y_benguerir_ca}
  I2 = {y_benguerir_ca, y_larache_rt}

Reports observed infra coverage separately from historical enum-selected E=11/14.
Also writes mission-level statuses so LIMIT is never confused with HOS infeasibility.
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

import pandas as pd  # noqa: E402

import run_stage_c_hos_national as stage_c  # noqa: E402

OUT = ROOT / "results" / "validation" / "path_a" / "infra_ladder"
CONFIGS = [
    ("I0_none", set()),
    ("I1_benguerir_ca", {"y_benguerir_ca"}),
    ("I2_benguerir_larache", {"y_benguerir_ca", "y_larache_rt"}),
]


def _git_sha() -> str:
    try:
        return (
            subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT)
            .decode()
            .strip()
        )
    except Exception:  # noqa: BLE001
        return stage_c.SHA


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    sha = _git_sha()
    fingerprint = {
        "git_sha": sha,
        "checkpoint_tag": "path-a-pre-correction-c8d9769",
        "vehicle_key": "eactros_600",
        "q": 2,
        "route_mode": "multi",
        "max_seconds": stage_c.UNIFORM_MAX_SECONDS,
        "max_expansions": stage_c.ABLATION_MAX_EXPANSIONS,
        "fridge": str(stage_c.FRIDGE.relative_to(ROOT)).replace("\\", "/"),
        "pipeline": "path_a_infra_ladder_matched_multi",
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    (OUT / "run_fingerprint.json").write_text(
        json.dumps(fingerprint, indent=2) + "\n", encoding="utf-8"
    )

    orig = stage_c._patch_realistic_speed_policy()
    summary_rows: list[dict] = []
    all_missions: list[dict] = []
    try:
        for cfg_id, installed in CONFIGS:
            print(f"[infra] {cfg_id} sites={sorted(installed) or ['(none)']}", flush=True)
            t0 = time.perf_counter()
            ev = stage_c._eval_installed_on_panel(
                vehicle_key="eactros_600",
                installed=set(installed),
                route_mode="multi",
                method_id=f"infra_{cfg_id}",
                budget="infra",
                q=2,
                max_seconds=stage_c.UNIFORM_MAX_SECONDS,
                max_expansions=stage_c.ABLATION_MAX_EXPANSIONS,
                include_energy_only=True,
            )
            elapsed = time.perf_counter() - t0
            for mr in ev["mission_rows"]:
                row = dict(mr)
                row["infra_config_id"] = cfg_id
                row["git_sha"] = sha
                row["run_fingerprint"] = fingerprint["pipeline"]
                all_missions.append(row)
            summary_rows.append(
                {
                    "infra_config_id": cfg_id,
                    "sites": ",".join(sorted(installed)),
                    "n_sites": len(installed),
                    "route_mode": "multi",
                    "ops_served": int(ev["n_operationally_served"]),
                    "ops_frac": float(ev["operational_coverage"]),
                    "energy_served": int(
                        round(float(ev["energy_coverage"]) * int(ev["n_missions"]))
                    ),
                    "energy_frac": float(ev["energy_coverage"]),
                    "n_missions": int(ev["n_missions"]),
                    "n_optimal": int(ev.get("n_optimal") or 0),
                    "n_infeasible": int(ev.get("n_infeasible") or 0),
                    "n_limit_reached": int(ev.get("n_limit_reached") or 0),
                    "elapsed_sec": round(elapsed, 1),
                    "max_seconds": stage_c.UNIFORM_MAX_SECONDS,
                    "max_expansions": stage_c.ABLATION_MAX_EXPANSIONS,
                    "git_sha": sha,
                    "note": (
                        "observed matched multi-route infra ladder; "
                        "not enum-selected E portfolio"
                    ),
                }
            )
            stage_c._write_csv(OUT / "infra_ladder_summary.csv", summary_rows)
            stage_c._write_csv(OUT / "infra_ladder_missions.csv", all_missions)
            print(
                f"  ops={summary_rows[-1]['ops_served']}/14 "
                f"energy={summary_rows[-1]['energy_served']}/14 "
                f"LIMIT={summary_rows[-1]['n_limit_reached']} "
                f"sec={elapsed:.0f}",
                flush=True,
            )
    finally:
        import morocco_etruck.optimization.multiroute_placement_evaluation as mpe

        mpe.load_multiroute_pilot_config = orig

    # Historical algorithm-selection reference (do not overwrite observed ladder).
    hist = []
    port = ROOT / "results" / "paper_campaign" / "q2_critical_portfolio.csv"
    if port.exists():
        df = pd.read_csv(port)
        ea = df[df.vehicle_key == "eactros_600"]
        for _, r in ea.iterrows():
            hist.append(
                {
                    "table": "historical_enum_selection",
                    "budget": r["budget"],
                    "E_ops": r.get("E_ops"),
                    "E_sites": r.get("E_sites"),
                    "C_ops": r.get("C_ops"),
                    "C_sites": r.get("C_sites"),
                    "B_ops": r.get("B_ops"),
                    "note": "screened enum_cap<=2 selection; preserve E=11/14 as historical",
                }
            )
    stage_c._write_csv(OUT / "historical_enum_selection_reference.csv", hist)

    notes = OUT / "infra_ladder_notes.md"
    i2 = next((s for s in summary_rows if s["infra_config_id"] == "I2_benguerir_larache"), None)
    i1 = next((s for s in summary_rows if s["infra_config_id"] == "I1_benguerir_ca"), None)
    notes.write_text(
        "\n".join(
            [
                "# Observed infrastructure ladder (matched multi-route)",
                "",
                "Protocol: 600 s / 2e6 expansions, q=2, eActros, hos_in_search ops + energy dual.",
                "",
                "| Config | Sites | Ops | Energy | LIMIT |",
                "|--------|-------|-----|--------|-------|",
                *[
                    f"| {s['infra_config_id']} | {s['sites'] or '(none)'} | "
                    f"{s['ops_served']}/14 | {s['energy_served']}/14 | {s['n_limit_reached']} |"
                    for s in summary_rows
                ],
                "",
                "## Interpretation",
                "",
                "- **Observed I1** (Benguerir alone) is the matched counterpart of historical screened E.",
                f"  Observed ops={i1['ops_served'] if i1 else '?'}/14; historical E ops=11/14.",
                "- **Observed I2** (Benguerir+Larache multi) must be reported if better than I1;",
                "  do **not** keep claiming 11/14 as best-known B2 coverage when I2 > I1.",
                f"  Observed I2 ops={i2['ops_served'] if i2 else '?'}/14.",
                "- Historical enum-selected E remains documented in "
                "`historical_enum_selection_reference.csv` (algorithm-selection table).",
                "- Any LIMIT rows are unresolved — not INFEASIBLE / not HOS-physical failures.",
                "",
                f"Fingerprint: `{fingerprint['pipeline']}` @ `{sha}`",
                "",
            ]
        ),
        encoding="utf-8",
    )
    print(f"[infra] wrote {OUT}", flush=True)


if __name__ == "__main__":
    main()
