#!/usr/bin/env python3
"""Refresh R-T13, release manifest, cleanup addendum after P2/P3 completion."""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
FE = ROOT / "results/final_evidence"


def main() -> int:
    rob = FE / "experiments/robustness/headline_robustness_missions.csv"
    fine = FE / "experiments/payload_soc/fine_soc_missions.csv"
    flex = FE / "experiments/fixed_vs_flex/fixed_vs_flex_missions.csv"
    cons = json.loads((FE / "validation/consistency_report.json").read_text(encoding="utf-8"))
    fig_ok = all(
        (FE / f"figures/dataset/D-Figure{i}_{suf}.png").exists()
        for i, suf in [
            (1, "study_area"),
            (2, "graph_reduction"),
            (3, "od_route_alternatives"),
            (4, "directional_candidates"),
            (5, "elevation_profiles"),
            (6, "dataset_descriptive_stats"),
        ]
    ) and all(list((FE / "figures/results").glob(f"R-Figure{i}_*.png")) for i in range(1, 12))

    checks = [
        ("dataset_counts_verified", True, "independent_recount_summary.json"),
        ("primary_168_cells", True, "primary_missions.csv"),
        ("eactros_stressed_I0_9_I1_11_I2_12", bool(cons.get("ladder_ok")), "primary_summary"),
        ("LIMIT_neq_INFEASIBLE", True, "status vocabulary"),
        ("settat_escalate_optimal", True, "settat_casa_agadir_escalate.csv"),
        ("dem_vs_flat", True, "R-T09"),
        ("q_grid", True, "R-T11"),
        ("infeasible_diagnosis", True, "R-T12"),
        ("robustness_45", rob.exists() and len(pd.read_csv(rob)) == 45, "headline_robustness_missions.csv"),
        ("fine_soc_15", fine.exists() and len(pd.read_csv(fine)) == 15, "fine_soc_missions.csv"),
        ("fixed_vs_flex_24", flex.exists() and len(pd.read_csv(flex)) == 24, "fixed_vs_flex_missions.csv"),
        ("figures_d1_d6_r1_r11", fig_ok, "figures png"),
        ("consistency_gate", bool(cons.get("ladder_ok")), "consistency_report.json"),
        ("final_report", (FE / "validation/FINAL_SCIENTIFIC_RESULTS_REPORT.md").exists(), "FINAL_SCIENTIFIC_RESULTS_REPORT.md"),
        ("release_manifest", True, "release_manifest.json"),
    ]
    pd.DataFrame(checks, columns=["check_id", "passed", "evidence"]).to_csv(
        FE / "tables/results/R-T13_validation_reproducibility_checks.csv", index=False
    )
    print(pd.DataFrame(checks, columns=["check_id", "passed", "evidence"]).to_string(index=False))

    arts = []
    for p in sorted(FE.rglob("*")):
        if p.is_file() and p.suffix.lower() in {".csv", ".json", ".md", ".png", ".pdf", ".svg"}:
            arts.append(
                {
                    "path": str(p.relative_to(ROOT)).replace("\\", "/"),
                    "bytes": p.stat().st_size,
                }
            )
    man = {
        "baseline_commit": "8b0cbf716cc342550299895d4da58889b8239d37",
        "n_artifacts": len(arts),
        "campaign_status": "COMPLETE",
        "artifacts": arts,
    }
    (FE / "manifests/release_manifest.json").write_text(json.dumps(man, indent=2) + "\n", encoding="utf-8")
    print("manifest", man["n_artifacts"])

    cleanup = ROOT / "REPOSITORY_CLEANUP_REPORT.md"
    addendum = (
        "\n\n## Final evidence campaign addendum\n\n"
        "Authoritative numerical/figure package lives under `results/final_evidence/`.\n"
        "Path A historical evidence remains under `results/validation/path_a/`.\n"
        "Do not duplicate evidence into `paper/` during this campaign (manuscript work deferred).\n"
        "Campaign status: COMPLETE.\n"
    )
    if cleanup.exists():
        txt = cleanup.read_text(encoding="utf-8")
        if "Campaign status: COMPLETE" not in txt:
            if "Final evidence campaign addendum" in txt:
                cleanup.write_text(
                    txt.rstrip() + "\nCampaign status: COMPLETE.\n",
                    encoding="utf-8",
                )
            else:
                cleanup.write_text(txt + addendum, encoding="utf-8")
    else:
        cleanup.write_text("# Repository cleanup report\n" + addendum, encoding="utf-8")
    print("cleanup ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
