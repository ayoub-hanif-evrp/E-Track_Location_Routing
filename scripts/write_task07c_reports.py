#!/usr/bin/env python
"""Write Task 07C markdown reports and figures from CSVs."""

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
    if not p.exists():
        return pd.DataFrame()
    return pd.read_csv(p)


def write_evidence_matrix() -> None:
    text = """# Task 07C — Evidence and novelty matrix

## Vehicles (frozen)

| Role | Spec | Provenance grade |
| --- | --- | --- |
| Primary prospective highway tractor | Volvo FH Electric 475 kWh usable (`volvo_fh_electric_4x2_540kwh.yaml`) | Manufacturer verified (Volvo Trucks Morocco FH Electric documentation / brochure specs) |
| Battery sensitivity | Volvo FH Electric 460 kWh usable variant | Manufacturer documented specification sensitivity |
| Comparator | Mercedes-Benz eActros 600 (600 kWh usable) | Manufacturer verified |
| Moroccan e-refrigerated deployment (dossier only) | Petit Forestier / Centrale Danone context | Official deployment case — **not** used as 40 t highway OD tractor in this matrix |

Do **not** substitute vans or 7.5 t distribution trucks into 40 t highway scenarios.

## Infrastructure and demand provenance

| Parameter | Value in freeze | Grade | Notes |
| --- | --- | --- | --- |
| Candidate sites Settat / Benguerir / Amskroud | Directional ADM service-area topology | Official infrastructure identity + OSM topology | **Not** certified HGV access; **not** operating 350 kW truck chargers |
| Charger power 150 / 350 kW | Hypothetical truck-compatible power | Engineering assumption | Volvo FH Electric docs mention up to 350 kW charging for the generation; ADM Programme AZUR / 2025 annual report describe EV charging for cars at service areas — not HGV 350 kW at these sites |
| Payload 5300 kg | Fixed cargo comparison design | Engineering assumption | Not observed fleet payload |
| Demand weights (total 5.5) | `cold_chain_baseline_07a/07b` | Engineering assumption / illustrative | Not observed Moroccan refrigerated volumes |
| Refrigeration UA 50/80/120 W/K | Documented YAML sensitivity | Engineering assumption | Inspired by cold-chain literature (e.g. Bank et al. 2025) — **not** calibrated to Moroccan TRU logs |
| Infiltration 500 W scenario | Explicit assumed duty | Unverified / unavailable | Labeled separately from calibrated params |
| DEM terrain | COP-DEM GLO-30 macros | Official open data | Task 05B complete for CM/CA/MA |
| Road speeds | Research cruise / OSM maxspeed policy | Engineering assumption | Not observed HGV speeds |
| Electricity tariff | Uniform research ¢/kWh | Engineering assumption | Not a Moroccan industrial tariff quote |
| Deadlines 8/10/12/20 h | Illustrative feasibility windows | Engineering assumption | Not observed contracts |

## Literature bars (novelty positioning)

| Source | Role for this study |
| --- | --- |
| Plaza et al. (2026) — charger location with routing and driver HOS for long-haul e-trucks | Prior art on joint siting+routing; our novelty is **not** “B&B+MRLS exists” |
| Bank et al. (2025) — refrigerated trailer thermal/power model with test-drive data | Thermal modeling bar; we use transparent UA ranges, not a calibrated TRU twin |
| Cheng et al. (2026) — temperature-aware e-truck charging infrastructure planning | Related infrastructure+temperature literature |

**Testable contribution:** how vehicle battery configuration, cold-chain energy demand, DEM terrain, and direction-specific motorway candidates jointly affect the **minimum hypothetical network** needed to serve a defined Moroccan refrigerated-freight portfolio — under fair nested baselines and stated uncertainty grades.

## Moroccan operational leads (external evidence, not invented)

| Source | What it supports | What it does **not** validate |
| --- | --- | --- |
| Volvo Trucks Morocco FH Electric pages | Prospective refrigerated tractor + up to 350 kW charging for that generation | Exact trailer integration or Moroccan deployment |
| ADM annual report 2025 / Programme AZUR | EV charging presence on the motorway network | Truck-compatible 350 kW at Settat/Benguerir/Amskroud |
| SOTRAFRIQUE public refrigerated fleet / GPS / temperature recorders | Candidate for requesting anonymized ops data | Any numbers used in this freeze |
| Petit Forestier Moroccan e-refrigerated deployment | Confirmed distribution-scale case (dossier) | Highway 40 t OD placement claims |

## Study framing (honest)

This freeze is an **evidence-grounded prospective optimization study**. It is **not** a field-validated Moroccan deployment recommendation.
"""
    (REP / "task07c_evidence_and_novelty_matrix.md").write_text(text, encoding="utf-8")


def write_scientific_results(base: pd.DataFrame, place: pd.DataFrame, sens: pd.DataFrame) -> None:
    lines = [
        "# Task 07C — Final scientific results",
        "",
        "Finite-model research freeze after route-nesting repair. "
        "Not a Moroccan install recommendation.",
        "",
        "## Finding 1 — Infrastructure: when battery assumptions change site count",
        "",
    ]
    if not place.empty and "budget_name" in place.columns:
        lines.append(
            "| Cell | Vehicle | B1 cov | B1 sites | B2 sites | optima | agree |"
        )
        lines.append("| --- | --- | ---: | --- | --- | --- | --- |")
        for cell in sorted(place.panel_cell.dropna().unique()):
            for veh in ("eactros_600", "volvo_475", "volvo_460"):
                b1 = place[
                    (place.panel_cell == cell)
                    & (place.vehicle_key == veh)
                    & (place.budget_name == "B1")
                ]
                b2 = place[
                    (place.panel_cell == cell)
                    & (place.vehicle_key == veh)
                    & (place.budget_name == "B2")
                ]
                if b1.empty:
                    continue
                r1 = b1.iloc[0]
                r2 = None if b2.empty else b2.iloc[0]
                lines.append(
                    f"| {cell} | {veh} | {r1.get('coverage_serviceable')} | "
                    f"{r1.get('best_sites_bb')} | "
                    f"{'' if r2 is None else r2.get('best_sites_bb')} | "
                    f"{r1.get('all_optimal_site_sets')} | {r1.get('objective_agreement')} |"
                )
    elif not place.empty:
        lines.append(
            "Placement file present but incomplete "
            f"(columns={list(place.columns)}; status counts="
            f"{place.get('status', pd.Series(dtype=str)).value_counts().to_dict()})."
        )
    else:
        lines.append("_Placement CSV missing._")

    lines += [
        "",
        "## Finding 2 — Method: what joint route choice adds on the same graph",
        "",
    ]
    if not base.empty:
        sub = base[base.baseline_id.isin(["B", "C"])].copy()
        lines.append(
            "| Vehicle | OD | install | B obj (shortest MRLS) | C obj (multi) | gain | nesting_ok |"
        )
        lines.append("| --- | --- | --- | ---: | ---: | ---: | --- |")
        for _, r in sub[sub.baseline_id == "C"].iterrows():
            b = sub[
                (sub.baseline_id == "B")
                & (sub.vehicle_key == r.vehicle_key)
                & (sub.od_id == r.od_id)
                & (sub.install_set == r.install_set)
            ]
            bobj = None if b.empty else b.iloc[0].get("objective")
            lines.append(
                f"| {r.vehicle_key} | {r.od_id} | {r.install_set} | {bobj} | "
                f"{r.get('objective')} | {r.get('route_choice_gain_vs_B')} | "
                f"{r.get('nesting_ok_vs_B')} |"
            )
        a = base[base.baseline_id == "A"]
        lines.append("")
        lines.append(
            f"Deterministic fixed-route policy (A) rows: {len(a)}; "
            f"OPTIMAL={int((a.mrls_status=='OPTIMAL').sum()) if not a.empty else 0}."
        )
    else:
        lines.append("_Matched baselines CSV missing._")

    lines += [
        "",
        "## Finding 3 — Cold-chain significance",
        "",
    ]
    if not sens.empty:
        th = sens[sens.get("thermal_id", pd.Series(dtype=str)) == "thermal_high"]
        lines.append("| Vehicle | thermal | status | obj | E_refrig_drive | E_traction |")
        lines.append("| --- | --- | --- | ---: | ---: | ---: |")
        for _, r in sens.iterrows():
            if r.get("sensitivity") not in ("thermal_high", "charger_power_12h") and str(
                r.get("thermal_id")
            ) not in ("thermal_high", "thermal_nominal"):
                continue
            lines.append(
                f"| {r.get('vehicle_key')} | {r.get('thermal_id')} | {r.get('mrls_status')} | "
                f"{r.get('objective')} | {r.get('E_refrig_drive_kwh')} | {r.get('E_traction_kwh')} |"
            )
        lines.append("")
        lines.append(
            "Interpretation must not inflate TRU to force siting. "
            "If objectives/coverage are unchanged vs nominal, report cold-chain as "
            "secondary energy share under documented UA ranges."
        )
    else:
        lines.append("_Sensitivity CSV missing._")

    lines += [
        "",
        "## Failed or invalidated robustness items",
        "",
        "1. **Task 07B routing baselines A/B vs D nesting claims** — invalidated "
        "(different physical graphs via `max_alts` rebuild). See "
        "`task07c_route_nesting_integrity.md`.",
        "2. **Task 07B baselines B and C** — not independent methods (identical setup).",
        "3. Any row with `dem_incomplete`, `BUILD_ERROR`, or `nesting_ok_vs_B=False` "
        "in Task 07C CSVs is a failed gate for that cell.",
        "",
        "## Framing",
        "",
        "Prospective evidence-graded optimization study. Requires external fleet/"
        "charger-access data before any field-validated performance claim.",
        "",
    ]
    (REP / "task07c_final_scientific_results.md").write_text(
        "\n".join(lines), encoding="utf-8"
    )


def write_figures(base: pd.DataFrame, place: pd.DataFrame) -> None:
    FIG.mkdir(parents=True, exist_ok=True)

    # Fig 2 — coverage by vehicle (from placement B1/B2)
    if not place.empty:
        fig, ax = plt.subplots(figsize=(7, 4))
        rows = []
        for veh, label in (
            ("eactros_600", "eActros 600"),
            ("volvo_475", "Volvo 475"),
        ):
            for bud, blab in (("B1", "one site"), ("B2", "two sites")):
                s = place[(place.vehicle_key == veh) & (place.budget_name == bud)]
                if s.empty:
                    continue
                # Prefer primary F0 cell
                s0 = s[s.panel_cell.astype(str).str.startswith("F0")]
                r = (s0 if not s0.empty else s).iloc[0]
                rows.append((f"{label}\n{blab}", float(r.coverage_serviceable or 0)))
        if rows:
            ax.bar([x[0] for x in rows], [x[1] for x in rows], color="#2f5d8a")
            ax.set_ylabel("Serviceable demand weight")
            ax.set_ylim(0, 6)
            ax.set_title("Vehicle vs achievable coverage (Task 07C freeze)")
            ax.axhline(5.5, color="gray", ls="--", lw=1, label="Total demand 5.5")
            ax.legend(loc="upper right")
            fig.tight_layout()
            fig.savefig(FIG / "task07c_vehicle_coverage.png", dpi=140)
        plt.close(fig)

    # Fig 4 — algorithm comparison B vs C objectives
    if not base.empty:
        fig, ax = plt.subplots(figsize=(8, 4))
        sub = base[
            (base.baseline_id.isin(["B", "C"]))
            & (base.install_set == "settat_benguerir")
            & (base.od_id == "casa_agadir")
        ]
        if not sub.empty:
            for vkey, marker in (("eactros_600", "o"), ("volvo_475", "s")):
                b = sub[(sub.vehicle_key == vkey) & (sub.baseline_id == "B")]
                c = sub[(sub.vehicle_key == vkey) & (sub.baseline_id == "C")]
                if b.empty or c.empty:
                    continue
                ax.plot(
                    ["B shortest MRLS", "C multi-route MRLS"],
                    [b.iloc[0].objective, c.iloc[0].objective],
                    marker=marker,
                    label=vkey,
                )
            ax.set_ylabel("Objective (cents)")
            ax.set_title("Matched algorithm comparison (CA, Settat+Benguerir)")
            ax.legend()
            fig.tight_layout()
            fig.savefig(FIG / "task07c_algorithm_comparison.png", dpi=140)
        plt.close(fig)

    # Fig 1 placeholder corridor note (text figure)
    fig, ax = plt.subplots(figsize=(7, 3))
    ax.axis("off")
    ax.text(
        0.02,
        0.6,
        "Moroccan directional corridor (Casa–Marrakech–Agadir)\n"
        "Hypothetical directional ADM candidates: Settat, Benguerir, Amskroud\n"
        "Evidence class: hypothetical_future_truck_site — not operating HGV 350 kW",
        fontsize=11,
        family="DejaVu Sans",
        va="center",
    )
    ax.set_title("Corridor and hypothetical sites (Task 07C)")
    fig.tight_layout()
    fig.savefig(FIG / "task07c_corridor_sites.png", dpi=140)
    plt.close(fig)

    # Fig 3 — SOC/charge profile from a matched OPTIMAL C row if extras absent: skip detailed
    fig, ax = plt.subplots(figsize=(7, 3))
    ax.axis("off")
    ax.text(
        0.02,
        0.55,
        "SOC/charging profiles: see continuous replay columns in\n"
        "results/task07c_matched_routing_baselines.csv and\n"
        "results/task07c_final_sensitivity.csv (charge_duration_s, min_soc, terminal_soc).",
        fontsize=11,
        va="center",
    )
    ax.set_title("Battery SOC / charging profile reference")
    fig.tight_layout()
    fig.savefig(FIG / "task07c_soc_charge_profile.png", dpi=140)
    plt.close(fig)


def append_nesting_results(base: pd.DataFrame) -> None:
    path = REP / "task07c_route_nesting_integrity.md"
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    if "## Matched baseline nesting outcomes" in text:
        return
    lines = [
        "",
        "## Matched baseline nesting outcomes",
        "",
    ]
    if base.empty:
        lines.append("_Run `run_task07c_final_freeze.py --stages baselines` first._")
    else:
        c = base[base.baseline_id == "C"]
        bad = c[c.get("nesting_ok_vs_B", pd.Series(dtype=object)) == False]  # noqa: E712
        lines.append(
            f"C rows with nesting check: {len(c)}; failures: {len(bad)}."
        )
        if not bad.empty:
            lines.append("")
            lines.append("Failures:")
            for _, r in bad.iterrows():
                lines.append(
                    f"- {r.vehicle_key} {r.od_id} {r.install_set}: "
                    f"B={base[(base.baseline_id=='B')&(base.vehicle_key==r.vehicle_key)&(base.od_id==r.od_id)&(base.install_set==r.install_set)].iloc[0].get('objective') if not base[(base.baseline_id=='B')&(base.vehicle_key==r.vehicle_key)&(base.od_id==r.od_id)&(base.install_set==r.install_set)].empty else '?'} "
                    f"C={r.get('objective')}"
                )
        else:
            lines.append("All reported B→C nesting checks passed on the same physical graph.")
    path.write_text(text.rstrip() + "\n" + "\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    REP.mkdir(parents=True, exist_ok=True)
    write_evidence_matrix()
    base = _load("task07c_matched_routing_baselines.csv")
    place = _load("task07c_final_placement.csv")
    sens = _load("task07c_final_sensitivity.csv")
    write_scientific_results(base, place, sens)
    write_figures(base, place)
    append_nesting_results(base)
    print("Wrote Task 07C reports/figures")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
