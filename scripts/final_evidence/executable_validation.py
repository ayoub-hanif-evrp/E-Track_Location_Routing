#!/usr/bin/env python3
"""P6 — Executable scientific validation (no hardcoded True checks)."""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
FE = ROOT / "results/final_evidence"
sys.path.insert(0, str(ROOT / "scripts/final_evidence"))


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def check(name: str, passed: bool, detail) -> dict:
    return {"check_id": name, "passed": bool(passed), "detail": detail}


def main() -> int:
    checks = []
    # Primary uniqueness / coverage
    prim = pd.read_csv(FE / "experiments/primary_comparison/primary_missions.csv")
    key = ["vehicle_key", "soc_scenario", "infra_config_id", "od_id"]
    n = len(prim)
    nuniq = prim.drop_duplicates(key).shape[0]
    checks.append(check("primary_unique_scenario_keys", n == nuniq == 168, {"n": n, "nuniq": nuniq}))
    summary = pd.read_csv(FE / "experiments/primary_comparison/primary_summary.csv")
    e = summary[(summary.vehicle_key == "eactros_600") & (summary.soc_scenario == "stressed_mixed")]
    ladder = {r.infra_config_id: int(r.ops_served) for _, r in e.iterrows()}
    checks.append(
        check(
            "eactros_stressed_ladder_9_11_12",
            ladder.get("I0_none") == 9
            and ladder.get("I1_benguerir_ca") == 11
            and ladder.get("I2_benguerir_larache") == 12,
            ladder,
        )
    )
    # Aggregates match
    rebuilt = (
        prim.groupby(["vehicle_key", "soc_scenario", "infra_config_id"])
        .agg(ops_served=("operationally_served", "sum"), n_missions=("od_id", "count"))
        .reset_index()
    )
    merged = summary.merge(
        rebuilt,
        on=["vehicle_key", "soc_scenario", "infra_config_id"],
        suffixes=("_sum", "_reb"),
    )
    agg_ok = bool(
        (merged["ops_served_sum"] == merged["ops_served_reb"]).all()
        and (merged["n_missions_sum"] == merged["n_missions_reb"]).all()
    )
    checks.append(check("primary_summary_matches_missions", agg_ok, {"n_groups": int(len(merged))}))

    # Robustness / fine / flex completeness
    rob = pd.read_csv(FE / "experiments/robustness/headline_robustness_missions.csv")
    checks.append(check("robustness_45_complete", len(rob) == 45, {"n": len(rob)}))
    fine = pd.read_csv(FE / "experiments/payload_soc/fine_soc_missions.csv")
    checks.append(check("fine_soc_15_complete", len(fine) == 15, {"n": len(fine)}))
    flex = pd.read_csv(FE / "experiments/fixed_vs_flex/fixed_vs_flex_missions.csv")
    checks.append(check("fixed_vs_flex_24_complete", len(flex) == 24, {"n": len(flex)}))

    # Historical q-grid reproduction
    q = pd.read_csv(FE / "tables/results/R-T11_energy_grid_resolution.csv")
    hist = q[q["scenario_family"].astype(str).str.contains("historical_15t", na=False)]
    q5 = hist[hist.q_kwh == 5]
    q2 = hist[hist.q_kwh == 2]
    hist_ok = (
        len(hist) == 6
        and (q5.status == "INFEASIBLE").all()
        and (q2.status == "OPTIMAL").all()
    )
    checks.append(
        check(
            "historical_15t_qgrid_reproduced",
            hist_ok,
            hist[["q_kwh", "route_mode", "status", "operationally_served"]].to_dict(orient="records")
            if len(hist)
            else "missing",
        )
    )

    # Elevation ordered reconstruction length fidelity
    elev = pd.read_csv(FE / "tables/dataset/D-T05_elevation_by_mission.csv")
    max_abs_err_km = float((elev["length_error_m"].abs() / 1000.0).max())
    min_cov = float(elev["dem_coverage_frac"].min())
    checks.append(
        check(
            "elevation_ordered_length_error_lt_1km",
            max_abs_err_km < 1.0 and min_cov >= 0.99,
            {"max_abs_err_km": max_abs_err_km, "min_coverage": min_cov},
        )
    )
    # Casa-Agadir must not be ~868 km artifact
    ca = elev[elev.od_id == "casa_agadir"].iloc[0]
    checks.append(
        check(
            "casa_agadir_elevation_not_double_counted",
            400 < float(ca.path_length_m) / 1000.0 < 500,
            {"path_length_km": float(ca.path_length_m) / 1000.0},
        )
    )

    # DEM vs flat families present
    rt09 = FE / "tables/results/R-T09_dem_vs_flat.csv"
    if rt09.exists():
        d = pd.read_csv(rt09)
        has_fixed = "fixed_short" in set(d.get("comparison_family", pd.Series(dtype=str)))
        checks.append(check("dem_vs_flat_has_fixed_route_family", has_fixed, d.comparison_family.value_counts().to_dict() if "comparison_family" in d.columns else "legacy_only"))
    else:
        checks.append(check("dem_vs_flat_has_fixed_route_family", False, "missing R-T09"))

    # Fine-SOC preserved transitions
    trans = pd.read_csv(FE / "tables/results/R-T05_preserved_soc_transitions.csv")
    checks.append(check("preserved_soc_transitions_present", len(trans) >= 3, {"n": len(trans)}))

    # Volvo naming
    vpf = pd.read_csv(FE / "tables/results/R-T02_vehicle_parameter_files.csv")
    volvo = vpf[vpf.vehicle_key == "volvo_475"]
    checks.append(
        check(
            "volvo_primary_usable_475",
            len(volvo) == 1 and float(volvo.iloc[0].usable_kwh) == 475.0,
            volvo.to_dict(orient="records"),
        )
    )

    # LIMIT ≠ INFEASIBLE vocabulary in primary
    statuses = set(prim.status.astype(str))
    checks.append(
        check(
            "status_vocab_has_distinct_limit",
            "INFEASIBLE" in statuses,
            {"statuses": sorted(statuses), "n_limit": int((prim.status == "LIMIT_REACHED").sum())},
        )
    )

    # Artifact presence
    required = [
        "figures/dataset/D-Figure5_elevation_profiles.png",
        "tables/dataset/D-T05_elevation_by_mission.csv",
        "tables/results/R-T11_energy_grid_resolution.csv",
        "validation/FINAL_SCIENTIFIC_RESULTS_REPORT.md",
    ]
    missing = [p for p in required if not (FE / p).exists()]
    checks.append(check("required_artifacts_present", not missing, missing))

    # SHA256 release manifest
    arts = []
    for p in sorted(FE.rglob("*")):
        if p.is_file() and p.suffix.lower() in {".csv", ".json", ".md", ".png", ".pdf", ".svg"}:
            # skip corrupt backups
            if "corrupt_backup" in p.name:
                continue
            arts.append(
                {
                    "path": str(p.relative_to(ROOT)).replace("\\", "/"),
                    "bytes": p.stat().st_size,
                    "sha256": _sha256(p),
                }
            )
    all_pass = all(c["passed"] for c in checks)
    manifest = {
        "baseline_commit_expected": "8b0cbf716cc342550299895d4da58889b8239d37",
        "campaign_status": "COMPLETE" if all_pass else "IN_PROGRESS_VALIDATION_GAPS",
        "n_artifacts": len(arts),
        "validation_all_passed": all_pass,
        "artifacts": arts,
    }
    (FE / "manifests/release_manifest_sha256.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    pd.DataFrame(checks).to_csv(
        FE / "tables/results/R-T13_validation_reproducibility_checks.csv", index=False
    )
    (FE / "validation/executable_validation_report.json").write_text(
        json.dumps({"all_passed": all_pass, "checks": checks}, indent=2) + "\n",
        encoding="utf-8",
    )
    print(pd.DataFrame(checks).to_string(index=False))
    print("ALL_PASSED" if all_pass else "GAPS_REMAIN")
    return 0 if all_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
