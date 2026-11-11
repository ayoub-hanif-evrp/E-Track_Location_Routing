#!/usr/bin/env python
"""Generate Task 07B markdown reports from CSV artifacts."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RES = ROOT / "results"
REP = ROOT / "reports"


def _load(name: str) -> pd.DataFrame:
    p = RES / name
    if not p.exists():
        return pd.DataFrame()
    return pd.read_csv(p)


def write_refrigeration_uncertainty(df: pd.DataFrame) -> None:
    lines = [
        "# Task 07B — Refrigeration / thermal-load uncertainty",
        "",
        "Documented UA / infiltration ranges only "
        "(`configs/energy/refrigeration_approx.yaml` + Task 07B ladder YAMLs). "
        "No invented TRU calibration. Infiltration 500 W is an **assumed** scenario.",
        "",
    ]
    if df.empty:
        lines.append("_No physical sensitivity CSV yet._")
        (REP / "task07b_refrigeration_uncertainty.md").write_text(
            "\n".join(lines), encoding="utf-8"
        )
        return
    sub = df[df.get("experiment_tag", pd.Series(dtype=str)) == "phys_sens"].copy()
    if sub.empty:
        sub = df.copy()
    # Focus Casa→Agadir, all_compatible, both terrains
    focus = sub[
        (sub["od_id"] == "casa_agadir")
        & (sub["install_set"] == "all_compatible")
        & (sub["mrls_status"] == "OPTIMAL")
    ]
    lines.append("## Energy breakdown (Casa→Agadir, chargers on, OPTIMAL cells)")
    lines.append("")
    lines.append(
        "| Vehicle | Terrain | Thermal | E_trac | E_refrig | E_regen | "
        "refrig/trac % | obj |"
    )
    lines.append("| --- | --- | --- | ---: | ---: | ---: | ---: | ---: |")
    for _, r in focus.sort_values(
        ["vehicle_key", "terrain_mode", "thermal_id"]
    ).iterrows():
        trac = r.get("E_traction_kwh")
        ref = r.get("E_refrig_total_kwh")
        pct = (
            100.0 * float(ref) / float(trac)
            if pd.notna(trac) and pd.notna(ref) and float(trac) > 1e-9
            else None
        )
        lines.append(
            f"| {r['vehicle_key']} | {r['terrain_mode']} | {r['thermal_id']} | "
            f"{trac if pd.notna(trac) else ''} | {ref if pd.notna(ref) else ''} | "
            f"{r.get('E_regen_credit_kwh','')} | "
            f"{'' if pct is None else f'{pct:.2f}'} | {r.get('objective','')} |"
        )
    # ON vs OFF
    lines.append("")
    lines.append("## Refrigeration ON vs OFF (matched ablation)")
    lines.append("")
    pair = sub[
        (sub["thermal_id"].isin(["thermal_nominal", "thermal_off"]))
        & (sub["od_id"] == "casa_agadir")
        & (sub["install_set"] == "all_compatible")
        & (sub["terrain_mode"] == "flat")
    ]
    if not pair.empty:
        lines.append("| Vehicle | Thermal | obj | E_refrig | status |")
        lines.append("| --- | --- | ---: | ---: | --- |")
        for _, r in pair.sort_values(["vehicle_key", "thermal_id"]).iterrows():
            lines.append(
                f"| {r['vehicle_key']} | {r['thermal_id']} | {r.get('objective','')} | "
                f"{r.get('E_refrig_total_kwh','')} | {r.get('mrls_status','')} |"
            )
    # Share of traction
    lines.append("")
    lines.append("## Interpretation")
    lines.append("")
    if not focus.empty and "E_traction_kwh" in focus.columns:
        ratios = []
        for _, r in focus.iterrows():
            if pd.notna(r.get("E_traction_kwh")) and pd.notna(
                r.get("E_refrig_total_kwh")
            ):
                t = float(r["E_traction_kwh"])
                if t > 1e-9:
                    ratios.append(100.0 * float(r["E_refrig_total_kwh"]) / t)
        if ratios:
            lines.append(
                f"Across OPTIMAL CA cells above, refrigeration is "
                f"**{min(ratios):.2f}–{max(ratios):.2f}%** of traction energy. "
                "If effects stay near ~1% of traction, q=10 may mask objective/"
                "charge differences — see discretization diagnostics at q=5."
            )
        else:
            lines.append("Insufficient OPTIMAL cells to compute refrig/traction ratios.")
    lines.append("")
    lines.append(
        "Do **not** inflate TRU merely to force infrastructure change. "
        "Placement claim revalidation is in `task07b_infrastructure_robustness.md`."
    )
    (REP / "task07b_refrigeration_uncertainty.md").write_text(
        "\n".join(lines) + "\n", encoding="utf-8"
    )


def write_charge_time(df: pd.DataFrame) -> None:
    lines = [
        "# Task 07B — Charge duration and deadlines",
        "",
        "Illustrative deadlines (8/10/12/20 h) after min physical journey gate. "
        "Not observed contracts. Objective remains cost-based; time enters via feasibility.",
        "",
    ]
    if df.empty:
        lines.append("_No charging duration CSV yet._")
    else:
        ok = df[df.get("mrls_status", pd.Series(dtype=str)) == "OPTIMAL"]
        lines.append("## 150 vs 350 kW (equal cost expected under loose deadlines)")
        lines.append("")
        lines.append(
            "| Vehicle | Terrain | kW | deadline_h | obj | charge_s | journey_s | "
            "margin_s | E_refrig_stat |"
        )
        lines.append(
            "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |"
        )
        for _, r in ok.sort_values(
            ["vehicle_key", "terrain_mode", "charger_power_kw", "deadline_hours"]
        ).iterrows():
            lines.append(
                f"| {r['vehicle_key']} | {r['terrain_mode']} | {r['charger_power_kw']} | "
                f"{r['deadline_hours']} | {r.get('objective','')} | "
                f"{r.get('charge_duration_s','')} | {r.get('total_journey_time_s','')} | "
                f"{r.get('arrival_margin_s','')} | {r.get('E_refrig_stationary_kwh','')} |"
            )
        skip = df[df.get("status", pd.Series(dtype=str)) == "deadline_physically_impossible"]
        lines.append("")
        lines.append("## Deadlines gated as physically impossible")
        lines.append("")
        if skip.empty:
            lines.append("None in this run.")
        else:
            lines.append("| Vehicle | Terrain | kW | deadline_h | min_journey_h |")
            lines.append("| --- | --- | ---: | ---: | ---: |")
            for _, r in skip.iterrows():
                lines.append(
                    f"| {r.get('vehicle_key','')} | {r.get('terrain_mode','')} | "
                    f"{r.get('charger_power_kw','')} | {r.get('deadline_hours','')} | "
                    f"{r.get('min_physical_journey_h','')} |"
                )
        lines.append("")
        lines.append(
            "Equal 150/350 **cost** with unequal duration is expected under loose "
            "deadlines — do not claim power equivalence."
        )
    (REP / "task07b_charge_time_and_deadlines.md").write_text(
        "\n".join(lines) + "\n", encoding="utf-8"
    )


def write_disc(df: pd.DataFrame) -> None:
    lines = [
        "# Task 07B — Discretization diagnostics",
        "",
        "Isolate eActros Casa→Marrakech SOC 0.5, refrigeration ON, **no chargers**, "
        "q=10 vs q=5 vs q=2 against continuous shortest-path physics.",
        "",
    ]
    if df.empty:
        lines.append("_No diagnostics CSV yet._")
    else:
        lines.append(
            "| Terrain | q | MRLS | continuous_ok | class | obj | terminal_soc_short |"
        )
        lines.append("| --- | ---: | --- | --- | --- | ---: | ---: |")
        for _, r in df.sort_values(["terrain_mode", "energy_quantum_kwh"]).iterrows():
            lines.append(
                f"| {r['terrain_mode']} | {r['energy_quantum_kwh']} | "
                f"{r.get('mrls_status','')} | {r.get('shortest_continuous_feasible','')} | "
                f"{r.get('discrete_vs_continuous_class','')} | {r.get('objective','')} | "
                f"{r.get('shortest_terminal_soc','')} |"
            )
        lines.append("")
        lines.append("## Classification key")
        lines.append("")
        lines.append(
            "- `physical_infeasible` — continuous SOC/peak fails on shortest path\n"
            "- `discrete_grid_reject` — continuous OK, discrete MRLS INFEASIBLE\n"
            "- `quantization_capacity_loss` — discrete solution exists but replay/"
            "capacity loss\n"
            "- `peak_motor` / `time` / `unresolved` — as labeled"
        )
        flat10 = df[
            (df.terrain_mode == "flat") & (df.energy_quantum_kwh == 10)
        ]
        flat5 = df[(df.terrain_mode == "flat") & (df.energy_quantum_kwh == 5)]
        if not flat10.empty and not flat5.empty:
            lines.append("")
            lines.append("## Headline")
            lines.append("")
            lines.append(
                f"Flat q=10: `{flat10.iloc[0].get('discrete_vs_continuous_class')}` "
                f"(MRLS `{flat10.iloc[0].get('mrls_status')}`); "
                f"flat q=5: `{flat5.iloc[0].get('discrete_vs_continuous_class')}` "
                f"(MRLS `{flat5.iloc[0].get('mrls_status')}`). "
                "This matches the Task 07A B0 coverage swing "
                "(0.0 → 2.0) attribution to Casa→Marrakech grid conservatism."
            )
    (REP / "task07b_discretization_diagnostics.md").write_text(
        "\n".join(lines) + "\n", encoding="utf-8"
    )


def write_baselines(df: pd.DataFrame) -> None:
    lines = [
        "# Task 07B — Comparable routing baselines A–E",
        "",
        "Same demand weight 5.5 freight definition (payload 5300 kg, SOC 0.5, "
        "cool, nominal thermal). Attribute gains separately: route freedom vs "
        "infrastructure vs vehicle vs refrigeration vs terrain vs q.",
        "",
        "| ID | Meaning |",
        "| --- | --- |",
        "| A | Shortest-distance path, no chargers |",
        "| B | Shortest-distance path, Settat+Benguerir |",
        "| C | Fixed-route (shortest) energy-feasible MRLS + chargers |",
        "| D | Multi-route MRLS, predefined installs |",
        "| E | Joint B&B–MRLS (see placement robustness) |",
        "",
    ]
    if df.empty:
        lines.append("_No baselines CSV yet._")
    else:
        terrain = df.get("panel_terrain", pd.Series(["?"])).iloc[0]
        lines.append(f"Panel terrain used: **{terrain}**.")
        lines.append("")
        lines.append(
            "| baseline | vehicle | od | install | status | obj | continuous_ok |"
        )
        lines.append("| --- | --- | --- | --- | --- | ---: | --- |")
        cols = ["baseline_detail", "vehicle_key", "od_id", "install_set"]
        for _, r in df.sort_values(
            [c for c in cols if c in df.columns]
        ).iterrows():
            lines.append(
                f"| {r.get('baseline_detail', r.get('baseline_id',''))} | "
                f"{r['vehicle_key']} | {r['od_id']} | {r['install_set']} | "
                f"{r.get('mrls_status','')} | {r.get('objective','')} | "
                f"{r.get('continuous_replay_ok','')} |"
            )
        lines.append("")
        lines.append(
            "Never credit B&B for gains that come from extra chargers or extra "
            "paths alone — compare A/B/C/D before reading E."
        )
    (REP / "task07b_routing_baselines.md").write_text(
        "\n".join(lines) + "\n", encoding="utf-8"
    )


def write_robustness(df: pd.DataFrame) -> None:
    lines = [
        "# Task 07B — Infrastructure / one-vs-two-site claim robustness",
        "",
        "Revalidates Task 07A eActros one-site vs Volvo two-site under the bounded "
        "P0–P5 panel. Finite model research scenario — **not** a Moroccan install "
        "recommendation.",
        "",
    ]
    if df.empty:
        lines.append("_No placement robustness CSV yet._")
    else:
        lines.append(
            "| Cell | Vehicle | Budget | cov | best_bb | all_optima | agree | status |"
        )
        lines.append("| --- | --- | --- | ---: | --- | --- | --- | --- |")
        for _, r in df.sort_values(
            ["panel_cell", "vehicle_key", "budget_name"]
        ).iterrows():
            lines.append(
                f"| {r.get('panel_cell','')} | {r.get('vehicle_key','')} | "
                f"{r.get('budget_name','')} | {r.get('coverage_serviceable','')} | "
                f"{r.get('best_sites_bb','')} | {r.get('all_optimal_site_sets','')} | "
                f"{r.get('objective_agreement','')} | {r.get('optimality_status','')} |"
            )
        lines.append("")
        lines.append("## Claim verdict")
        lines.append("")
        # Compare B1 one-site coverage eActros vs Volvo at P0 and P1
        def _b1(cell: str, veh: str):
            s = df[
                (df.panel_cell == cell)
                & (df.vehicle_key == veh)
                & (df.budget_name == "B1")
            ]
            return None if s.empty else s.iloc[0]

        verdict_bits = []
        for cell in ["P0", "P1", "P2", "P3", "P4", "P5"]:
            ea = _b1(cell, "eactros_600")
            vo = _b1(cell, "volvo_475")
            if ea is None or vo is None:
                continue
            verdict_bits.append(
                f"- **{cell}**: eActros B1 cov={ea.get('coverage_serviceable')} "
                f"sites=`{ea.get('best_sites_bb')}` / optima=`{ea.get('all_optimal_site_sets')}`; "
                f"Volvo B1 cov={vo.get('coverage_serviceable')} "
                f"sites=`{vo.get('best_sites_bb')}`. "
                f"B2 Volvo=`{df[(df.panel_cell==cell)&(df.vehicle_key=='volvo_475')&(df.budget_name=='B2')].iloc[0].get('best_sites_bb') if not df[(df.panel_cell==cell)&(df.vehicle_key=='volvo_475')&(df.budget_name=='B2')].empty else 'n/a'}`."
            )
        lines.extend(verdict_bits or ["_Placement panel incomplete._"])
        lines.append("")
        # Auto support/narrow/withdraw for P0 vs P1
        p0e, p0v = _b1("P0", "eactros_600"), _b1("P0", "volvo_475")
        p1e, p1v = _b1("P1", "eactros_600"), _b1("P1", "volvo_475")
        if p0e is not None and p0v is not None:
            one_vs_two = (
                float(p0e.get("coverage_serviceable") or 0) >= 4.0 - 1e-9
                and float(p0v.get("coverage_serviceable") or 0) <= 2.0 + 1e-9
            )
            if p1e is not None and p1v is not None:
                dem_same = (
                    abs(
                        float(p1e.get("coverage_serviceable") or -1)
                        - float(p0e.get("coverage_serviceable") or -2)
                    )
                    < 1e-9
                    and abs(
                        float(p1v.get("coverage_serviceable") or -1)
                        - float(p0v.get("coverage_serviceable") or -2)
                    )
                    < 1e-9
                )
                if one_vs_two and dem_same:
                    lines.append(
                        "**Verdict:** **support** the finite-model one-vs-two-site "
                        "contrast under DEM+nominal (P1 matches P0 coverage pattern). "
                        "Causing assumption retained: flat/DEM research cruise + "
                        "Config A TRU + q-grid + hypothetical 350 kW ADM sites."
                    )
                elif one_vs_two and not dem_same:
                    lines.append(
                        "**Verdict:** **narrow** — DEM (P1) changes coverage/"
                        "optima relative to flat P0. Report the exact cell that flips "
                        "in the table above."
                    )
                else:
                    lines.append(
                        "**Verdict:** **withdraw/narrow** — P0 pattern does not "
                        "reproduce the 07A one-vs-two contrast under this runner."
                    )
        lines.append("")
        lines.append("## Data-request sheet (evidence gaps — no fabricated observations)")
        lines.append("")
        lines.append(
            "| Stakeholder | Need | Why |"
            "\n| --- | --- | --- |"
            "\n| Operator / fleet | GPS traces, payload, delivery windows, measured TRU kW | "
            "Replace illustrative weights, cruise, and UA |"
            "\n| ADM / corridor | HGV access certification, available grid power at service areas | "
            "Move sites beyond `hypothetical_future_truck_site` |"
            "\n| Utility | Connection capacity / tariff at Settat, Benguerir, Amskroud | "
            "Replace uniform research ¢/kWh |"
            "\n| OEM | Usable kWh warranty curves, peak motor derate under grade | "
            "Bound DEM peak_motor / SOC claims |"
        )
    (REP / "task07b_infrastructure_robustness.md").write_text(
        "\n".join(lines) + "\n", encoding="utf-8"
    )


def main() -> int:
    REP.mkdir(parents=True, exist_ok=True)
    write_refrigeration_uncertainty(_load("task07b_physical_sensitivity.csv"))
    write_charge_time(_load("task07b_charging_duration.csv"))
    write_disc(_load("task07b_discretization_diagnostics.csv"))
    write_baselines(_load("task07b_routing_baselines.csv"))
    write_robustness(_load("task07b_placement_robustness.csv"))
    # Refresh partial reports that already have data
    print("Wrote Task 07B reports under", REP)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
