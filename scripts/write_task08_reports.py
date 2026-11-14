#!/usr/bin/env python
"""Task 08 — final reports, figures, and summary CSV."""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
RES = ROOT / "results"
REP = ROOT / "reports"
FIG = REP / "figures"


def _load(name: str) -> pd.DataFrame:
    p = RES / name
    return pd.read_csv(p) if p.exists() else pd.DataFrame()


def write_model_audit() -> None:
    text = """# Task 08 — Final model audit

Reviewed HEAD base: `57270d2` (Task 07C). This checkpoint does **not** rebuild B&B–MRLS.

## Physical / discrete model (frozen)

| Component | Setting | Notes |
| --- | --- | --- |
| Path union | Scientific pilot `max_alternatives_for_union=2` | Shortest + top Jaccard alt |
| Route baselines | `allowed_arc_ids` masks on one graph | Task 07C nesting fix |
| Chargers | `active_stations` only | Hypothetical ADM directional sites |
| Terrain | DEM (COP-DEM GLO-30) | `dem_incomplete` gated |
| Refrigeration | Config A, UA from Task 07B nominal YAML | Not calibrated TRU |
| Grid | q=10 primary | |
| Deadline | 20 h (240 × 5 min) | Illustrative |

## Nesting validation (Gate 1)

- Synthetic adversarial test: both restricted and expanded OPTIMAL with **strict** `obj_exp < obj_res` (`tests/unit/test_task08_nesting_and_realism.py`).
- Shortest-mask connectivity: masked arcs ⊆ OSM shortest path and connect O→D.
- Moroccan feasibility-gain cells (fixed-shortest IF, multi-route OPTIMAL) retained as contribution evidence; vacuous vs positive nesting labeled in robustness report.

## Moroccan combination legality (Gate 3)

Equal cargo **15000 kg** check (manufacturer GCW only):

| Vehicle | Empty combo kg | GCM at 15 t | Tech GCW limit |
| --- | ---: | ---: | ---: |
| eActros 600 | 19700 | 34700 | 44000 |
| Volvo FH Electric 475 | 20000 | 35000 | 65000 |

**Manufacturer GCW ≠ Moroccan legal operating limit.** Axle-load / combination rules under Moroccan legislation are **not** fully encoded here; axle detail marked **unavailable** — do not invent. Results are technical-permissible under YAML GCW only.

## Honesty

Not a field-validated Moroccan deployment. Not operating 350 kW HGV chargers at Settat/Benguerir/Amskroud. Demand weights and CAPEX=100 remain illustrative unless graded otherwise in the economics section.
"""
    (REP / "task08_final_model_audit.md").write_text(text, encoding="utf-8")


def write_soc_payload(df: pd.DataFrame) -> None:
    lines = [
        "# Task 08 — SOC and payload robustness",
        "",
        "Challenge: does eActros one-site vs Volvo two-site survive SOC 0.8/1.0 and 15 t cargo?",
        "",
        "## Placement coverage (B1 / B2)",
        "",
    ]
    place = df[df.get("budget_name", pd.Series(dtype=str)).notna()].copy() if not df.empty else df
    if not place.empty and "budget_name" in place.columns:
        lines.append(
            "| Cell | SOC | Payload | Vehicle | B1 cov | B1 sites | B2 sites | agree |"
        )
        lines.append("| --- | ---: | ---: | --- | ---: | --- | --- | --- |")
        for cell in ["S50", "S80", "S100", "H50", "H80"]:
            for veh in ("eactros_600", "volvo_475"):
                b1 = place[
                    (place.cell_id == cell)
                    & (place.vehicle_key == veh)
                    & (place.budget_name == "B1")
                ]
                b2 = place[
                    (place.cell_id == cell)
                    & (place.vehicle_key == veh)
                    & (place.budget_name == "B2")
                ]
                if b1.empty:
                    continue
                r1 = b1.iloc[0]
                r2 = None if b2.empty else b2.iloc[0]
                lines.append(
                    f"| {cell} | {r1.get('soc_init')} | {r1.get('cargo_payload_kg')} | {veh} | "
                    f"{r1.get('coverage_serviceable')} | {r1.get('best_sites_bb')} | "
                    f"{'' if r2 is None else r2.get('best_sites_bb')} | "
                    f"{r1.get('objective_agreement')} |"
                )
        # Verdict
        lines += ["", "## Claim survival verdict", ""]
        def pattern(cell: str, veh: str):
            b1 = place[(place.cell_id == cell) & (place.vehicle_key == veh) & (place.budget_name == "B1")]
            b2 = place[(place.cell_id == cell) & (place.vehicle_key == veh) & (place.budget_name == "B2")]
            if b1.empty or b2.empty:
                return None
            return float(b1.iloc[0].coverage_serviceable or 0), float(
                b2.iloc[0].coverage_serviceable or 0
            )

        survived = []
        flipped = []
        for cell in ["S50", "S80", "S100", "H50", "H80"]:
            ea = pattern(cell, "eactros_600")
            vo = pattern(cell, "volvo_475")
            if ea is None or vo is None:
                continue
            one_vs_two = ea[0] >= 3.99 and vo[0] <= 2.01 + 1e-6 and vo[1] >= 3.99
            if one_vs_two:
                survived.append(cell)
            else:
                flipped.append(f"{cell}: eActros B1={ea[0]} B2={ea[1]}; Volvo B1={vo[0]} B2={vo[1]}")
        if survived and not flipped:
            lines.append(
                f"**Survives** on cells {', '.join(survived)} under DEM refrigerated equal-cargo "
                "assumptions. Still **not** a general Moroccan fleet recommendation — "
                "departure SOC and payload remain scenario parameters."
            )
        elif flipped:
            lines.append("**Does not universally survive.** Changed cells:")
            for x in flipped:
                lines.append(f"- {x}")
            lines.append(
                "Do not retune SOC/payload to restore the previous headline."
            )
        else:
            lines.append("_Insufficient placement rows._")
    else:
        lines.append("_Placement results missing._")

    # Routing nesting classes
    route = df[df.get("baseline_id", pd.Series(dtype=str)).isin(["B", "C"])] if not df.empty and "baseline_id" in df.columns else pd.DataFrame()
    lines += ["", "## Matched routing nesting classes", ""]
    if not route.empty:
        lines.append("| Cell | Vehicle | OD | B | C | nesting_class |")
        lines.append("| --- | --- | --- | --- | --- | --- |")
        for _, r in route[route.baseline_id == "C"].iterrows():
            b = route[
                (route.baseline_id == "B")
                & (route.cell_id == r.cell_id)
                & (route.vehicle_key == r.vehicle_key)
                & (route.od_id == r.od_id)
            ]
            bst = "" if b.empty else b.iloc[0].get("mrls_status")
            lines.append(
                f"| {r.cell_id} | {r.vehicle_key} | {r.od_id} | {bst} | "
                f"{r.get('mrls_status')} | {r.get('nesting_class')} |"
            )
    else:
        lines.append("_Routing rows missing._")

    (REP / "task08_realism_and_soc_payload_robustness.md").write_text(
        "\n".join(lines) + "\n", encoding="utf-8"
    )


def write_algorithm(df: pd.DataFrame) -> None:
    lines = [
        "# Task 08 — Algorithm performance (synthetic shared-road)",
        "",
        "Label: **synthetic**. Not Moroccan traffic. Not national-scale proof.",
        "",
        "Benchmark: 8 candidate sites on a shared trunk + long alternate path; "
        "4 missions with battery limits; enum vs B&B.",
        "",
    ]
    if df.empty:
        lines.append("_No benchmark CSV._")
    else:
        lines.append(
            "| Budget | enum sites | bb sites | agree | enum_s | bb_s | nodes | "
            "prune_cov | prune_cost | status |"
        )
        lines.append("| --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | --- |")
        for _, r in df.iterrows():
            lines.append(
                f"| {r.get('budget_name')} | {r.get('enum_best_sites')} | "
                f"{r.get('bb_best_sites')} | {r.get('objective_agreement')} | "
                f"{r.get('enum_sec')} | {r.get('bb_sec')} | {r.get('bb_nodes_visited')} | "
                f"{r.get('bb_prunes_coverage')} | {r.get('bb_prunes_secondary')} | "
                f"{r.get('optimality_status')} |"
            )
        lines.append("")
        if df["objective_agreement"].all():
            lines.append(
                "All reported budgets: **enumeration and B&B agree** on the synthetic "
                "shared-road instance."
            )
        else:
            lines.append(
                "Some budgets disagree or timed out — see CSV; do not claim certified "
                "superiority for those cells."
            )
        lines.append("")
        lines.append(
            "Reference: independent-mission 12-site demo remains in "
            "`configs/optimization/branch_bound_benchmarks.yaml` (not shared-road)."
        )
    (REP / "task08_algorithm_performance.md").write_text(
        "\n".join(lines) + "\n", encoding="utf-8"
    )


def write_claims(econ: pd.DataFrame, place: pd.DataFrame) -> None:
    text = f"""# Task 08 — Claims, evidence, and limitations

## Main claims (scoped)

1. **Under the tested DEM refrigerated portfolio**, vehicle usable energy and route flexibility affect the minimum hypothetical ADM site count needed for modeled coverage (weight 5.5 with MA often unserved).
2. **Same-graph multi-route MRLS** can restore feasibility when fixed-shortest is infeasible (Task 07C/08 matched masks).
3. **Synthetic shared-road B&B** matches enumeration on the 8-site Task 08 benchmark (correctness/pruning demo — not national scale).

## Evidence grades

| Input | Grade |
| --- | --- |
| Usable kWh (eActros / Volvo MA page) + tech GCW | Manufacturer-labeled in YAML |
| Volvo empty tractor curb | **Assumed** (not OEM curb) |
| Refrigerated trailer empty mass (both vehicles) | **Assumed** |
| Empty combination mass | Derived = tractor+trailer; **not** manufacturer-verified combo |
| ADM site identity / OSM topology | Official + OSM |
| 350 kW truck charging at Settat/Benguerir/Amskroud | **Unavailable / hypothetical** |
| Departure SOC 0.5/0.8/1.0 | Engineering assumption (dispatch policy) |
| Payload 5300 / 15000 kg | Engineering assumption |
| Demand weights total 5.5 | Illustrative |
| Site CAPEX = 100 research units | Illustrative |
| Uniform electricity ¢/kWh | Illustrative (not an ONEE site quote) |
| DEM macros | Official open data (COP-DEM) |

## Economics provenance (Gate 4)

| Cost component | Treatment |
| --- | --- |
| Charger equipment | Illustrative (bundled into site CAPEX=100) |
| Civil / installation | Illustrative (bundled) |
| Grid connection / upgrades | **Unavailable** for these sites — not modeled |
| O&M | Not modeled |
| Energy purchased | Uniform research tariff; ONEE public tariffs are transferability-qualified only if cited as sensitivity — this freeze keeps uniform ¢/kWh |
| Road operating cost | Research 100 ¢/km |
| Annualization | CRF from 8% / 15 yr |
| Freight-demand weights | Illustrative — **not** trips/year |

**Unit note:** secondary cost mixes annualized CAPEX (CRF×ΣCAPEX) with Σw·C_var without defining w as annual trip frequency — normalized illustrative research costs only. See `reports/final_economic_units_and_provenance_audit.md`.

CAPEX ratio sensitivity (0.5× / 1× / 2×) on equal illustrative site costs:

"""
    if not econ.empty:
        text += "| Ratio | Vehicle | Budget | Sites | Coverage | Secondary |\n| --- | --- | --- | --- | ---: | ---: |\n"
        for _, r in econ.iterrows():
            text += (
                f"| {r.get('capex_ratio')} | {r.get('vehicle_key')} | {r.get('budget_name')} | "
                f"{r.get('best_sites_bb')} | {r.get('coverage_serviceable')} | "
                f"{r.get('secondary_cost')} |\n"
            )
        text += (
            "\nIf site sets are unchanged across ratios, only secondary cost scales — "
            "feasibility-driven siting, not investment optimization.\n"
        )
    else:
        text += "_Economics CSV missing._\n"

    text += """
## Distinctions (required)

1. **Minimum sites for modeled feasibility** — coverage under discrete MRLS + continuous replay gates.
2. **Budget-optimal under illustrative CAPEX** — B1/B2/Ball with CAPEX=100 units.
3. **Real-world investment recommendation** — **not established** without site costs, grid capacity, and observed demand.

## Data request (parallel, outside this freeze)

- SOTRAFRIQUE / operators: 10–30 anonymized refrigerated journeys (route, payload, times, trailer temperature, stops).
- ADM / utilities: HGV access certification and available power at candidate service areas.
- Measured TRU electrical load logs for Moroccan ambient conditions.

## Limitations

- Path-union of verified alternatives only — not full Moroccan network optimality.
- Discrete quantum / time grid ≠ continuous physics ≠ empirical validation.
- Petit Forestier/Centrale Danone remains a separate distribution-scale dossier case.
"""
    (REP / "task08_claims_evidence_limitations.md").write_text(text, encoding="utf-8")


def write_figures(place: pd.DataFrame, algo: pd.DataFrame, route: pd.DataFrame) -> None:
    FIG.mkdir(parents=True, exist_ok=True)

    # Corridor note
    fig, ax = plt.subplots(figsize=(7, 3))
    ax.axis("off")
    ax.text(
        0.02,
        0.55,
        "Casa–Marrakech–Agadir directional corridor\n"
        "Hypothetical sites: Settat, Benguerir, Amskroud\n"
        "Task 08 freeze — not operating HGV 350 kW",
        fontsize=11,
        va="center",
    )
    ax.set_title("Moroccan corridor and potential sites")
    fig.tight_layout()
    fig.savefig(FIG / "task08_corridor_sites.png", dpi=140)
    plt.close(fig)

    # SOC × payload × min sites (B1 sites count for max coverage pattern)
    if not place.empty and "budget_name" in place.columns:
        fig, ax = plt.subplots(figsize=(8, 4))
        rows = []
        for cell in ["S50", "S80", "S100", "H50", "H80"]:
            for veh, lab in (("eactros_600", "eActros"), ("volvo_475", "Volvo475")):
                # min sites among budgets that achieve that vehicle's max coverage in cell
                sub = place[(place.cell_id == cell) & (place.vehicle_key == veh)]
                if sub.empty:
                    continue
                max_cov = sub["coverage_serviceable"].max()
                at = sub[sub.coverage_serviceable >= max_cov - 1e-9]
                nmin = int(at["n_sites_installed"].min()) if "n_sites_installed" in at else 0
                soc = sub.iloc[0].soc_init
                pay = sub.iloc[0].cargo_payload_kg
                rows.append((f"{lab}\n{cell}", nmin, soc, pay))
        if rows:
            ax.bar([r[0] for r in rows], [r[1] for r in rows], color="#345f7a")
            ax.set_ylabel("Min installed sites for max modeled coverage")
            ax.set_title("Vehicle / SOC / payload → minimum site count")
            fig.tight_layout()
            fig.savefig(FIG / "task08_soc_payload_sites.png", dpi=140)
        plt.close(fig)

    # Shortest vs multi feasibility
    if not route.empty and "baseline_id" in route.columns:
        fig, ax = plt.subplots(figsize=(7, 4))
        sub = route[route.cell_id == "S50"] if "cell_id" in route.columns else route
        labels = []
        vals = []
        for _, r in sub[sub.baseline_id == "C"].iterrows():
            b = sub[
                (sub.baseline_id == "B")
                & (sub.vehicle_key == r.vehicle_key)
                & (sub.od_id == r.od_id)
            ]
            labels.append(f"{r.vehicle_key[:6]}\n{r.od_id[:8]}")
            # 1 if C feasible, 0.5 if both, etc.
            c_ok = r.mrls_status == "OPTIMAL"
            b_ok = (not b.empty) and b.iloc[0].mrls_status == "OPTIMAL"
            vals.append(2 if c_ok and not b_ok else (1 if c_ok and b_ok else 0))
        if labels:
            ax.bar(labels, vals, color="#6b8f71")
            ax.set_ylabel("0=IF, 1=both OK, 2=multi-only")
            ax.set_title("Fixed-shortest vs multi-route feasibility (S50)")
            fig.tight_layout()
            fig.savefig(FIG / "task08_shortest_vs_multi.png", dpi=140)
        plt.close(fig)

    # B&B vs enum times
    if not algo.empty:
        fig, ax = plt.subplots(figsize=(6, 4))
        x = range(len(algo))
        ax.bar([i - 0.15 for i in x], algo["enum_sec"], width=0.3, label="Enum")
        ax.bar([i + 0.15 for i in x], algo["bb_sec"], width=0.3, label="B&B")
        ax.set_xticks(list(x))
        ax.set_xticklabels(algo["budget_name"].astype(str))
        ax.set_ylabel("Wall time (s)")
        ax.set_title("Synthetic shared-road: enum vs B&B")
        ax.legend()
        fig.tight_layout()
        fig.savefig(FIG / "task08_bb_vs_enum.png", dpi=140)
        plt.close(fig)

    # SOC profile placeholder reference
    fig, ax = plt.subplots(figsize=(7, 3))
    ax.axis("off")
    ax.text(
        0.02,
        0.55,
        "Battery / charging profiles: see continuous replay columns in\n"
        "task08_soc_payload_comparison.csv (routing rows) and Task 07C sensitivity CSVs.",
        fontsize=11,
        va="center",
    )
    ax.set_title("Battery-energy and charging profile reference")
    fig.tight_layout()
    fig.savefig(FIG / "task08_soc_charge_profile.png", dpi=140)
    plt.close(fig)


def write_summary(place: pd.DataFrame, econ: pd.DataFrame, algo: pd.DataFrame) -> None:
    rows = []
    if not place.empty and "budget_name" in place.columns:
        for cell in place.cell_id.dropna().unique():
            for veh in place.vehicle_key.dropna().unique():
                b1 = place[
                    (place.cell_id == cell)
                    & (place.vehicle_key == veh)
                    & (place.budget_name == "B1")
                ]
                if b1.empty:
                    continue
                r = b1.iloc[0]
                rows.append(
                    {
                        "finding": "placement_B1",
                        "cell_id": cell,
                        "vehicle_key": veh,
                        "soc_init": r.get("soc_init"),
                        "cargo_payload_kg": r.get("cargo_payload_kg"),
                        "coverage_serviceable": r.get("coverage_serviceable"),
                        "best_sites": r.get("best_sites_bb"),
                        "objective_agreement": r.get("objective_agreement"),
                    }
                )
    if not algo.empty:
        for _, r in algo.iterrows():
            rows.append(
                {
                    "finding": "synthetic_bb_enum",
                    "budget_name": r.get("budget_name"),
                    "objective_agreement": r.get("objective_agreement"),
                    "bb_sec": r.get("bb_sec"),
                    "enum_sec": r.get("enum_sec"),
                }
            )
    pd.DataFrame(rows).to_csv(RES / "task08_final_summary.csv", index=False)
    print("Wrote", RES / "task08_final_summary.csv")


def main() -> int:
    REP.mkdir(parents=True, exist_ok=True)
    write_model_audit()
    df = _load("task08_soc_payload_comparison.csv")
    econ = _load("task08_placement_economics.csv")
    algo = _load("task08_algorithm_benchmarks.csv")
    write_soc_payload(df)
    write_algorithm(algo)
    write_claims(econ, df)
    route = df[df["baseline_id"].isin(["B", "C"])] if "baseline_id" in df.columns else pd.DataFrame()
    place = df[df["budget_name"].notna()] if "budget_name" in df.columns else pd.DataFrame()
    write_figures(place, algo, route)
    write_summary(place, econ, algo)
    print("Wrote Task 08 reports/figures")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
