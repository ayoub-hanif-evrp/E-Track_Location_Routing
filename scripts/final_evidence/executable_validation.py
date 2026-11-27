#!/usr/bin/env python3
"""P6 — Executable scientific validation.

Generate validation report first; write SHA-256 release manifest LAST.
The manifest hashes every authoritative artifact except itself.
"""
from __future__ import annotations

import hashlib
import json
import math
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
FE = ROOT / "results/final_evidence"
sys.path.insert(0, str(ROOT / "scripts/final_evidence"))

EXPECTED_LADDER = {
    ("eactros_600", "stressed_mixed"): {
        "I0_none": 9,
        "I1_benguerir_ca": 11,
        "I2_benguerir_larache": 12,
        "I3_benguerir_ca_larache_benguerir_ac": 13,
    },
    ("eactros_600", "common_soc_80"): {
        "I0_none": 11,
        "I1_benguerir_ca": 12,
        "I2_benguerir_larache": 13,
        "I3_benguerir_ca_larache_benguerir_ac": 14,
    },
    ("volvo_475", "stressed_mixed"): {
        "I0_none": 7,
        "I1_benguerir_ca": 7,
        "I2_benguerir_larache": 8,
        "I3_benguerir_ca_larache_benguerir_ac": 8,
    },
    ("volvo_475", "common_soc_80"): {
        "I0_none": 8,
        "I1_benguerir_ca": 9,
        "I2_benguerir_larache": 10,
        "I3_benguerir_ca_larache_benguerir_ac": 10,
    },
}


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def check(name: str, passed: bool, detail) -> dict:
    return {"check_id": name, "passed": bool(passed), "detail": detail}


def _is_nullish(v) -> bool:
    if v is None:
        return True
    if isinstance(v, float) and (math.isnan(v) or pd.isna(v)):
        return True
    if isinstance(v, str) and v.strip().lower() in {"", "nan", "none", "not_evaluated"}:
        return True
    return False


def main() -> int:
    checks: list[dict] = []

    panel_path = FE / "experiments/primary_i0_i3_panel/primary_i0_i3_missions.csv"
    if not panel_path.exists():
        checks.append(check("primary_224_panel_present", False, "missing panel CSV"))
        panel = None
    else:
        panel = pd.read_csv(panel_path)
        key = ["vehicle_key", "soc_scenario", "infra_config_id", "od_id"]
        n = len(panel)
        nuniq = panel.drop_duplicates(key).shape[0]
        checks.append(
            check("primary_224_unique_scenario_keys", n == nuniq == 224, {"n": n, "nuniq": nuniq})
        )
        summary = pd.read_csv(FE / "experiments/primary_i0_i3_panel/primary_i0_i3_summary.csv")
        rebuilt = (
            panel.groupby(["vehicle_key", "soc_scenario", "infra_config_id"])
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
        checks.append(check("panel_summary_matches_missions", agg_ok, {"n_groups": int(len(merged))}))

        ladder_ok = True
        ladder_detail = {}
        for (vk, soc), exp in EXPECTED_LADDER.items():
            for infra, n_exp in exp.items():
                hit = summary[
                    (summary.vehicle_key == vk)
                    & (summary.soc_scenario == soc)
                    & (summary.infra_config_id == infra)
                ]
                got = int(hit.iloc[0].ops_served) if len(hit) else None
                ladder_detail[f"{vk}|{soc}|{infra}"] = {"got": got, "expected": n_exp}
                if got != n_exp:
                    ladder_ok = False
        checks.append(check("coverage_ladder_i0_i3", ladder_ok, ladder_detail))

        # Directional installation counts
        meta_ok = True
        for infra, n_dir in {
            "I0_none": 0,
            "I1_benguerir_ca": 1,
            "I2_benguerir_larache": 2,
            "I3_benguerir_ca_larache_benguerir_ac": 3,
        }.items():
            hit = summary[summary.infra_config_id == infra]
            if not len(hit) or int(hit.iloc[0].n_directional_installations) != n_dir:
                meta_ok = False
        checks.append(check("directional_installation_counts", meta_ok, "I0=0,I1=1,I2=2,I3=3"))

    # Legacy 168 still present for provenance
    prim = pd.read_csv(FE / "experiments/primary_comparison/primary_missions.csv")
    checks.append(
        check(
            "legacy_primary_168_present",
            len(prim) == 168,
            {"n": len(prim)},
        )
    )

    # Unevaluated HOS fields must not be False without a trace
    hos_bad = 0
    if panel is not None:
        no_trace = (panel["status"].astype(str) != "OPTIMAL") | panel.get(
            "drive_min_phys", pd.Series([None] * len(panel))
        ).isna()
        for col in ("hos_ok", "daily_driving_ok"):
            if col in panel.columns:
                hos_bad += int((no_trace & panel[col].isin([False, 0, "False", "false"])).sum())
    checks.append(
        check(
            "hos_fields_not_false_without_trace",
            hos_bad == 0,
            {"n_false_without_trace": hos_bad},
        )
    )

    # I3 mission-level audit file
    i3 = FE / "experiments/i3_three_site/i3_missions.csv"
    checks.append(check("i3_missions_present", i3.exists() and len(pd.read_csv(i3)) == 56, str(i3)))

    # Robustness / fine / flex
    rob = pd.read_csv(FE / "experiments/robustness/headline_robustness_missions.csv")
    checks.append(check("robustness_45_complete", len(rob) == 45, {"n": len(rob)}))
    fine = pd.read_csv(FE / "experiments/payload_soc/fine_soc_missions.csv")
    checks.append(check("fine_soc_15_complete", len(fine) == 15, {"n": len(fine)}))
    flex = pd.read_csv(FE / "experiments/fixed_vs_flex/fixed_vs_flex_missions.csv")
    checks.append(check("fixed_vs_flex_24_complete", len(flex) == 24, {"n": len(flex)}))

    # Historical q-grid
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
            hist[["q_kwh", "route_mode", "status"]].to_dict(orient="records") if len(hist) else "missing",
        )
    )

    # Elevation
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
    ca = elev[elev.od_id == "casa_agadir"].iloc[0]
    checks.append(
        check(
            "casa_agadir_elevation_not_double_counted",
            400 < float(ca.path_length_m) / 1000.0 < 500,
            {"path_length_km": float(ca.path_length_m) / 1000.0},
        )
    )
    checks.append(
        check(
            "elevation_continuity_investigation_present",
            (FE / "dataset/elevation_continuity_grade_notes.md").exists(),
            "dataset/elevation_continuity_grade_notes.md",
        )
    )

    # DEM vs flat missing-value handling
    rt09 = FE / "tables/results/R-T09_dem_vs_flat_fixed_route.csv"
    if rt09.exists():
        d = pd.read_csv(rt09)
        cm = d[(d.od_id == "casa_marrakech") & (d.soc_frac == 0.5)]
        ok_mv = True
        detail = {}
        if len(cm):
            row = cm.iloc[0]
            # If DEM infeasible, traction_dem must be nullish (not 0.0 pretending to be energy)
            if not bool(row.get("ops_dem")):
                ok_mv = _is_nullish(row.get("traction_dem")) and _is_nullish(row.get("delta_traction_kwh"))
                detail = {
                    "ops_dem": bool(row.get("ops_dem")),
                    "ops_flat": bool(row.get("ops_flat")),
                    "traction_dem": row.get("traction_dem"),
                    "delta_traction_kwh": row.get("delta_traction_kwh"),
                    "interpretation": row.get("interpretation"),
                }
        else:
            ok_mv = False
            detail = "missing casa_marrakech 0.5 fixed row"
        checks.append(check("dem_flat_infeasible_uses_missing_energy", ok_mv, detail))
        checks.append(
            check(
                "dem_vs_flat_has_fixed_route_family",
                "fixed_short" in set(d.get("comparison_family", pd.Series(dtype=str))),
                d.comparison_family.value_counts().to_dict()
                if "comparison_family" in d.columns
                else "legacy",
            )
        )
    else:
        checks.append(check("dem_flat_infeasible_uses_missing_energy", False, "missing R-T09 fixed"))
        checks.append(check("dem_vs_flat_has_fixed_route_family", False, "missing"))

    # Volvo mechanism must not claim daily_driving_limit from unevaluated defaults
    r12 = FE / "tables/results/R-T12_volvo_marrakech_agadir_ops_mechanism.csv"
    if r12.exists():
        mech = pd.read_csv(r12)
        bad_claim = mech[
            mech.mechanism_hypothesis.astype(str).str.contains("daily_driving_limit")
            & ~mech.mechanism_hypothesis.astype(str).str.contains("audited")
        ]
        # Allow only explicitly audited label
        checks.append(
            check(
                "volvo_hos_mechanism_not_default_false",
                len(bad_claim) == 0,
                bad_claim.head(5).to_dict(orient="records") if len(bad_claim) else "ok",
            )
        )
    else:
        checks.append(check("volvo_hos_mechanism_not_default_false", False, "missing R-T12"))

    notes = FE / "experiments/volvo_ops_diagnosis/mechanism_notes.md"
    if notes.exists():
        txt = notes.read_text(encoding="utf-8")
        checks.append(
            check(
                "volvo_mechanism_notes_corrected",
                "not evaluated" in txt.lower() or "unresolved" in txt.lower(),
                "mechanism_notes.md",
            )
        )

    # Volvo Settatt vs Benguerir full panel
    vpanel = FE / "experiments/volvo_settat_vs_benguerir/volvo_settat_vs_benguerir_missions.csv"
    if vpanel.exists():
        vp = pd.read_csv(vpanel)
        checks.append(
            check(
                "volvo_settat_vs_benguerir_56",
                len(vp) == 56,
                {"n": len(vp)},
            )
        )
    else:
        checks.append(check("volvo_settat_vs_benguerir_56", False, "missing panel"))

    # Fine-SOC transitions
    trans = pd.read_csv(FE / "tables/results/R-T05_preserved_soc_transitions.csv")
    checks.append(check("preserved_soc_transitions_present", len(trans) >= 3, {"n": len(trans)}))

    # Volvo usable energy
    vpf = pd.read_csv(FE / "tables/results/R-T02_vehicle_parameter_files.csv")
    volvo = vpf[vpf.vehicle_key == "volvo_475"]
    checks.append(
        check(
            "volvo_primary_usable_475",
            len(volvo) == 1 and float(volvo.iloc[0].usable_kwh) == 475.0,
            volvo.to_dict(orient="records"),
        )
    )

    # R-Fig5 elevation alignment source exists
    elev_src = FE / "figures/results/source_data/R-Fig5_casa_marrakech_elevation.csv"
    arc_src = FE / "figures/results/source_data/R-Fig5_casa_marrakech_executed_arcs.csv"
    checks.append(
        check(
            "rfig5_executed_elevation_alignment_artifacts",
            elev_src.exists() and arc_src.exists(),
            {"elevation": elev_src.exists(), "arcs": arc_src.exists()},
        )
    )

    # Required figures/tables
    required = [
        "figures/results/R-Figure1_infrastructure_coverage.png",
        "figures/results/R-Figure2_geographic_feasibility.png",
        "figures/results/R-Figure5_casa_marrakech_operational_profile.png",
        "figures/results/R-Figure9b_casa_marrakech_terrain_triptych.png",
        "tables/dataset/D-T05_elevation_by_mission.csv",
        "tables/results/R-T02_infrastructure_coverage.csv",
        "tables/results/R-T03_mission_level_operational_results.csv",
        "tables/results/R-T11_energy_grid_resolution.csv",
        "validation/FINAL_SCIENTIFIC_RESULTS_REPORT.md",
    ]
    missing = [p for p in required if not (FE / p).exists()]
    checks.append(check("required_artifacts_present", not missing, missing))

    # Status consistency docs
    audit = FE / "validation/AUDIT_CORRECTIONS_STATUS.md"
    progress = FE / "manifests/CAMPAIGN_PROGRESS.md"
    for label, path in [("audit_status", audit), ("campaign_progress", progress)]:
        if path.exists():
            txt = path.read_text(encoding="utf-8").lower()
            conflict = ("complete" in txt) and ("in-progress" in txt or "in flight" in txt or "do not claim complete" in txt)
            checks.append(check(f"{label}_no_conflicting_complete_markers", not conflict, str(path)))
        else:
            checks.append(check(f"{label}_no_conflicting_complete_markers", False, "missing"))

    all_pass = all(c["passed"] for c in checks)

    # Write validation outputs FIRST (excluding final manifest)
    report_path = FE / "validation/executable_validation_report.json"
    report_path.write_text(
        json.dumps({"all_passed": all_pass, "checks": checks}, indent=2) + "\n",
        encoding="utf-8",
    )
    pd.DataFrame(checks).to_csv(
        FE / "tables/results/R-T13_validation_reproducibility_checks.csv", index=False
    )

    # Manifest LAST — hash all artifacts except the manifest itself
    manifest_rel = "results/final_evidence/manifests/release_manifest_sha256.json"
    arts = []
    for p in sorted(FE.rglob("*")):
        if not p.is_file():
            continue
        if p.suffix.lower() not in {".csv", ".json", ".md", ".png", ".pdf", ".svg"}:
            continue
        if "corrupt_backup" in p.name:
            continue
        # Side-outputs of verify_release_manifest.py (must not enter hashed inventory)
        if p.name.startswith("clean_checkout_verification"):
            continue
        rel = str(p.relative_to(ROOT)).replace("\\", "/")
        if rel == manifest_rel:
            continue
        arts.append({"path": rel, "bytes": p.stat().st_size, "sha256": _sha256(p)})

    # Verify hashes immediately (integrity self-check)
    mismatches = []
    for a in arts:
        actual = _sha256(ROOT / a["path"])
        if actual != a["sha256"]:
            mismatches.append(a["path"])
    checks.append(
        check("release_manifest_hash_self_consistent", not mismatches, mismatches[:10])
    )
    all_pass = all(c["passed"] for c in checks)
    # Refresh report with final hash check included
    report_path.write_text(
        json.dumps({"all_passed": all_pass, "checks": checks}, indent=2) + "\n",
        encoding="utf-8",
    )
    pd.DataFrame(checks).to_csv(
        FE / "tables/results/R-T13_validation_reproducibility_checks.csv", index=False
    )

    # Re-hash artifacts that validation just rewrote (report + R-T13), still excluding manifest
    arts = []
    for p in sorted(FE.rglob("*")):
        if not p.is_file():
            continue
        if p.suffix.lower() not in {".csv", ".json", ".md", ".png", ".pdf", ".svg"}:
            continue
        if "corrupt_backup" in p.name:
            continue
        if p.name.startswith("clean_checkout_verification"):
            continue
        rel = str(p.relative_to(ROOT)).replace("\\", "/")
        if rel == manifest_rel:
            continue
        arts.append({"path": rel, "bytes": p.stat().st_size, "sha256": _sha256(p)})

    manifest = {
        "baseline_commit_expected": "8b0cbf716cc342550299895d4da58889b8239d37",
        "campaign_status": "COMPLETE" if all_pass else "IN_PROGRESS_VALIDATION_GAPS",
        "n_artifacts": len(arts),
        "validation_all_passed": all_pass,
        "manifest_excludes_self": True,
        "artifacts": arts,
    }
    man_path = FE / "manifests/release_manifest_sha256.json"
    man_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    # Final verification: every stored hash matches file bytes; manifest not listed
    verify_fail = []
    for a in manifest["artifacts"]:
        p = ROOT / a["path"]
        if not p.exists():
            verify_fail.append({"path": a["path"], "reason": "missing"})
            continue
        if _sha256(p) != a["sha256"]:
            verify_fail.append({"path": a["path"], "reason": "hash_mismatch"})
    if any(a["path"] == manifest_rel for a in manifest["artifacts"]):
        verify_fail.append({"path": manifest_rel, "reason": "manifest_included_in_self"})
    final_ok = all_pass and not verify_fail
    if not final_ok and all_pass:
        # Downgrade if only manifest verify failed
        all_pass = False
        manifest["campaign_status"] = "IN_PROGRESS_VALIDATION_GAPS"
        manifest["validation_all_passed"] = False
        man_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    print(pd.DataFrame(checks).to_string(index=False))
    if verify_fail:
        print("MANIFEST_VERIFY_FAIL", verify_fail[:10])
    print("ALL_PASSED" if (all_pass and not verify_fail) else "GAPS_REMAIN")
    return 0 if (all_pass and not verify_fail) else 1


if __name__ == "__main__":
    raise SystemExit(main())
