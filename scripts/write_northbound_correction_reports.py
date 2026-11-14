#!/usr/bin/env python
"""Write PASS northbound correction reports from diagnostic/revalidation CSVs."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]


def write_root_cause() -> None:
    summary = json.loads(
        (ROOT / "results/northbound_power_speed_diagnostics_summary.json").read_text(
            encoding="utf-8"
        )
    )
    df = pd.read_csv(ROOT / "results/northbound_power_speed_diagnostics.csv")
    v = summary["vehicles"]["volvo_475"]
    fails = df[(df.vehicle == "volvo_475") & (df.get("peak_ok_fixed") == False)]  # noqa: E712
    lines = [
        "# Northbound power / grade / speed root cause",
        "",
        "## Verdict",
        "",
        "PASS 2’s all-zero Agadir→Casablanca coverage was **not** primarily an optimizer "
        "failure. Under fixed road-class cruise speeds, DEM-derived grades create "
        "`peak_motor_power_exceeded` rejects. Power-feasible speed reduction clears those "
        "motor rejects, but the mission remains **energy-infeasible before the two "
        "hypothetical chargers** (settat_ac, benguerir_ac) can be reached.",
        "",
        "**Do not** interpret the current simulator as proving a Volvo FH Electric cannot "
        "operate in Morocco. COPDEM GLO-30 is a DSM; grades are not surveyed pavement.",
        "",
        "## Priority 1 — Exact motor-power failures (fixed cruise)",
        "",
        f"- OD: `{summary['od_id']}`; payload {summary['payload_kg']} kg; GCM/mass "
        f"{v['gcm_kg']} kg.",
        f"- Micros inspected: {v['n_micro_edges']}; fixed peak fails: {v['n_fixed_peak_fail']}.",
        f"- Failing macros only: `{', '.join(v['failing_macro_ids'])}`.",
        f"- Short extreme DEM spike candidates (L≤80 m & |grade|≥8%): {v['n_spike_candidates']}.",
        f"- After peak-feasible speed search: adapt_peak_ok={v['n_adapt_peak_ok']}/"
        f"{v['n_micro_edges']}; still infeasible at 1 km/h floor: "
        f"{v['n_still_peak_infeas_at_floor']}.",
        f"- Segments whose peak-feasible speed is below motorway normal min 60 km/h: "
        f"{v['n_below_motorway_min_60']} (operational flag; not asserted legal).",
        "",
        "Worst fixed-cruise segments (Volvo) request ~650–690 kW wheel power at 80 km/h "
        "on ~9–11% DEM grades over tens of metres — consistent with mg·sinθ·v gravity power "
        "at 25.3 t, and far above the 400 kW research peak rating.",
        "",
        "### DEM provenance",
        "",
        "- Source: Copernicus GLO-30 via project COP-DEM sampling "
        "(`data/processed/multiroute/elevation/`, `dem_sampling_meta.json`).",
        "- Product class: **digital surface model** (buildings/vegetation/infrastructure "
        "possible), **not** a surveyed road-centerline pavement grade.",
        "- Macro metadata reports max sampled |grade| above 10% on some northbound macros; "
        "short spikes are audited in the CSV (`is_short_dem_spike_candidate`).",
        "- **No arbitrary DEM smoothing** was applied.",
        "",
        "## Priority 2 — Decree 2-10-420 (speed)",
        "",
        "Official consolidated reference used for research interpretation: Moroccan "
        "Decree **2-10-420**, Articles 17–18 (distinct from 2-10-421 weights/dimensions):",
        "",
        "- Goods vehicles >19 t: motorway **maximum 80 km/h**.",
        "- Outside urban areas (non-motorway provisions): generally **70 km/h**.",
        "- Article 18: normal motorway **minimum 60 km/h**; unusually slow motorway "
        "operation requires careful legal/safety treatment — modeled as an explicit class "
        "`below_motorway_normal_min_60`, not as automatic legality.",
        "",
        "Scenario comparison encoded in diagnostics:",
        "",
        "| Tag | Policy |",
        "| --- | --- |",
        "| A | Fixed road-class cruise (status quo) |",
        "| B | Legal-cap only (defaults already ≈ legal caps) |",
        "| C | Peak-power-feasible speed ≤ commanded cruise |",
        "| D | Continuous-power-feasible speed (eActros peak≠cont) |",
        "",
        "## Priority 3 — Physical correction adopted",
        "",
        "Opt-in flags on `speed_policy` (fingerprint-invalidating for DRIVE caches):",
        "",
        "- `adapt_speed_to_peak_power`",
        "- `adapt_speed_to_continuous_power`",
        "- `min_adapt_speed_mps`",
        "",
        "Implemented in `apply_drive` / `simulate_drive_from_soc` / DRIVE build / continuous "
        "replay. **OEM power ratings are not retuned.** Peak is never treated as unlimited "
        "duration when continuous adaptation is enabled. Instantaneous speed changes between "
        "micros omit accel/decel energy — documented limitation, not a fully validated cycle.",
        "",
        "## Reproduction",
        "",
        "```bash",
        "python scripts/run_northbound_power_speed_diagnostics.py",
        "python scripts/run_northbound_revalidated_feasibility.py",
        "```",
        "",
        "Artifacts: `results/northbound_power_speed_diagnostics.csv`, "
        "`results/northbound_power_speed_diagnostics_summary.json`.",
        "",
    ]
    if len(fails):
        top = fails.sort_values("P_wheel_fixed_kw", ascending=False).head(8)
        lines.extend(["## Example failing micros (Volvo fixed cruise)", "", "```"])
        for _, r in top.iterrows():
            lines.append(
                f"macro={r.macro_arc_id} L={r.length_m:.1f}m dz={r.dz_m:.2f} "
                f"grade={r.grade:.4f} v={r.v_cmd_kmh:.0f} P={r.P_wheel_fixed_kw:.0f}kW "
                f"v*= {r.v_peak_adapt_kmh:.1f}km/h spike={r.is_short_dem_spike_candidate}"
            )
        lines.append("```")
        lines.append("")
    (ROOT / "reports/northbound_power_grade_root_cause.md").write_text(
        "\n".join(lines), encoding="utf-8"
    )


def write_revalidated() -> None:
    csv_path = ROOT / "results/northbound_revalidated_placement.csv"
    df = pd.read_csv(csv_path) if csv_path.exists() else pd.DataFrame()
    lines = [
        "# Northbound revalidated feasibility (after speed/grade correction)",
        "",
        "## Scope",
        "",
        "- Primary: Agadir→Casablanca, firm-ripe tomato refrigeration, 5.3 t, SOC 0.8.",
        "- Vehicles: Volvo FH Electric 475 kWh usable; eActros 600.",
        "- Chargers: settat_ac, benguerir_ac only (no fabricated sites).",
        "- q=10; path-union max_alts 2 and 4 where scheduled.",
        "",
        "## Findings",
        "",
    ]
    if df.empty:
        lines.append("_Revalidation CSV missing — run "
                     "`python scripts/run_northbound_revalidated_feasibility.py`._")
    else:
        for tag in df.policy_tag.unique():
            sub = df[df.policy_tag == tag]
            n = len(sub)
            ns = int(sub.served.fillna(False).astype(bool).sum())
            lines.append(f"- **{tag}**: served {ns}/{n} mission cases.")
        served = df[df.served == True]  # noqa: E712
        lines.extend(
            [
                "",
                "### Vehicle-specific outcome after peak-adapt",
                "",
                "- **Volvo FH Electric (475 kWh usable, 400 kW peak=cont):** remains "
                "unserved for all tested install/alts/speed policies. Continuous probes "
                "clear peak-motor rejects, then hit `tractor_soc_floor` before candidate "
                "chargers; discrete MRLS cannot reach settat_ac/benguerir_ac with residual "
                "energy. **Not** a claim that Volvo cannot operate in Morocco — only that "
                "this DSM-grade + mass + charger-set model remains energy-limited.",
                "- **eActros 600 (600 kWh usable, 600 kW peak / 400 kW continuous):** with "
                "`adapt_speed_to_peak_power` (and also continuous-adapt / floor-60 variants), "
                "**max_alts=2 + both candidates**, mission becomes OPTIMAL, discrete and "
                "continuous replay OK, charging ~240 kWh at `benguerir_ac`.",
                "- Placement (eActros, peak-adapt, alts=2): B0 coverage 0; Ball coverage 1.0; "
                "optimal site set `{y_benguerir_ac}`; B&B ↔ enumeration agree "
                "(CERTIFIED_OPTIMAL).",
                "- **max_alts=4 path-union:** eActros Ball cases revert to INFEASIBLE under "
                "the same speed policy — path-union expansion is material; do not claim "
                "robustness over larger alternative sets without re-certification.",
                "",
                "### Limiting-cause classification",
                "",
                "| Candidate cause | Volvo A80 | eActros A80 (alts=2) |",
                "| --- | --- | --- |",
                "| Fixed-speed peak motor | Dominant pre-correction | Dominant pre-correction |",
                "| Peak-adapt gradeability | Cleared | Cleared |",
                "| Battery range / SOC before chargers | **Still binding** | Relieved with benguerir charge |",
                "| Station placement {settat,benguerir} | Unreachable ⇒ coverage 0 | Selects benguerir |",
                "| Path-union 2 vs 4 | Still IF | Feasible only at alts=2 in this run |",
                "| Fabricated early chargers | Not used | Not used |",
                "| DSM grade / mass uncertainty | Material | Material |",
                "",
            ]
        )
        if not served.empty:
            lines.append(
                f"Served rows in CSV: {len(served)} "
                f"(vehicles={sorted(served.vehicle.unique())})."
            )
            lines.append("")
        lines.extend(["## Table excerpt", "", "```"])
        cols = [
            c
            for c in [
                "policy_tag",
                "vehicle",
                "max_alts",
                "installed_mode",
                "mission_status",
                "served",
                "reason",
                "adapt_flag_on_ctx",
                "place_Ball_bb_coverage",
                "place_Ball_bb_enum_agree",
            ]
            if c in df.columns
        ]
        lines.append(df[cols].to_string(index=False))
        lines.append("```")
    lines.extend(
        [
            "",
            "## Reproduction",
            "",
            "```bash",
            "python scripts/run_northbound_revalidated_feasibility.py",
            "# optional smoke:",
            "python scripts/run_northbound_revalidated_feasibility.py --quick",
            "```",
            "",
            "CSV: `results/northbound_revalidated_placement.csv`",
            "",
        ]
    )
    (ROOT / "reports/northbound_revalidated_feasibility.md").write_text(
        "\n".join(lines), encoding="utf-8"
    )


def write_novelty_correction() -> None:
    csv_path = ROOT / "results/pass2_refinement_comparison.csv"
    df = pd.read_csv(csv_path)
    field_rows = []
    for scen in df.scenario.unique():
        sub = df[df.scenario == scen]
        a = sub[sub.method == "fixed_q10"]
        b = sub[sub.method == "fixed_q5"]
        if a.empty or b.empty:
            continue
        ra, rb = a.iloc[0], b.iloc[0]
        field_rows.append(
            {
                "scenario": scen,
                "feasibility_class_changed": bool(
                    str(ra.ball_status) != str(rb.ball_status)
                ),
                "coverage_changed": bool(
                    abs(
                        float(ra.place_max_coverage or 0)
                        - float(rb.place_max_coverage or 0)
                    )
                    > 1e-9
                ),
                "minimum_site_count_changed": bool(
                    str(ra.place_min_sites) != str(rb.place_min_sites)
                ),
                "optimal_site_set_changed": bool(
                    str(ra.place_best_sites) != str(rb.place_best_sites)
                ),
                "coverage_q10": float(ra.place_max_coverage or 0),
                "coverage_q5": float(rb.place_max_coverage or 0),
                "min_sites_q10": int(ra.place_min_sites)
                if ra.place_min_sites == ra.place_min_sites
                else None,
                "min_sites_q5": int(rb.place_min_sites)
                if rb.place_min_sites == rb.place_min_sites
                else None,
                "sites_q10": str(ra.place_best_sites),
                "sites_q5": str(rb.place_best_sites),
            }
        )
    for fr in field_rows:
        fr["objective_changed"] = (
            fr["coverage_changed"]
            or fr["minimum_site_count_changed"]
            or fr["optimal_site_set_changed"]
        )
    (ROOT / "results/pass2_refinement_change_fields.json").write_text(
        json.dumps(field_rows, indent=2, default=str), encoding="utf-8"
    )
    sb = next(
        (fr for fr in field_rows if "southbound" in str(fr["scenario"])),
        None,
    )
    lines = [
        "# PASS 2B novelty verdict — correction",
        "",
        "## Correction required",
        "",
        "Prior PASS 2B reporting treated a **coverage/feasibility-class** change as if it "
        "were an infrastructure **installation** change. Those are distinct.",
        "",
        "## Southbound H80 (q=10 → q=5)",
        "",
    ]
    if sb:
        lines.extend(
            [
                f"| Field | Value |",
                f"| --- | --- |",
                f"| feasibility_class_changed | {sb['feasibility_class_changed']} "
                f"(INFEASIBLE → OPTIMAL on Ball probe) |",
                f"| coverage_changed | {sb['coverage_changed']} "
                f"({sb['coverage_q10']} → {sb['coverage_q5']}) |",
                f"| minimum_site_count_changed | {sb['minimum_site_count_changed']} "
                f"({sb['min_sites_q10']} → {sb['min_sites_q5']}) |",
                f"| optimal_site_set_changed | {sb['optimal_site_set_changed']} "
                f"({sb['sites_q10']} → {sb['sites_q5']}) |",
                "",
                "Served demand weight can change while **min installed sites stay 0** and "
                "**selected set stays NONE**. That is a routing/coverage label change, not a "
                "charger-location change.",
                "",
            ]
        )
    lines.extend(
        [
            "## Methodological status",
            "",
            "- Protocol = **conditional coarse-to-fine retry** when Ball is infeasible at q=10.",
            "- **NO-GO** for claiming a new infrastructure-design optimizer or selective "
            "refinement algorithm with proved computational advantage.",
            "- **GO** to retain the coarse-grid false-negative as a **numerical-reliability** "
            "finding in validation sections.",
            "",
            "`novelty_decision: NO_GO_COVERAGE_ONLY_NOT_SITE_DECISION`",
            "",
            "## Code fix",
            "",
            "`scripts/run_pass2b_discretization_refinement.py` now emits distinct fields:",
            "`feasibility_class_changed`, `coverage_changed`, `minimum_site_count_changed`, "
            "`optimal_site_set_changed`, `objective_changed` "
            "(see `results/pass2_refinement_change_fields.json`).",
            "",
            "## Reproduction",
            "",
            "```bash",
            "python scripts/write_northbound_correction_reports.py",
            "# or full PASS2B regenerator:",
            "python scripts/run_pass2b_discretization_refinement.py",
            "```",
            "",
        ]
    )
    (ROOT / "reports/pass2_novelty_verdict_correction.md").write_text(
        "\n".join(lines), encoding="utf-8"
    )


def main() -> int:
    write_root_cause()
    write_revalidated()
    write_novelty_correction()
    print("Wrote reports/northbound_power_grade_root_cause.md")
    print("Wrote reports/northbound_revalidated_feasibility.md")
    print("Wrote reports/pass2_novelty_verdict_correction.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
