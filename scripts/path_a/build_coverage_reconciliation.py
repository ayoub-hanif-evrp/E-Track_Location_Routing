"""Gate 0 correction: coverage reconciliation with honest B labels and dual tables.

Two separate tables:
1. historical_enum_selection — screened E/C portfolio (preserve E=11/14)
2. observed_infra_ladder — matched multi-route I0/I1/I2 (from infra_ladder run if present)

B_fixed_conventional is NOT "no sites": B0=empty, B1=y_settat_ca, B2=y_settat_ca+y_settat_ac,
always fixed-route conventional order — never label as B_baseline_none.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "results" / "validation" / "path_a"
INFRA = OUT / "infra_ladder"


def _frac(n: int, d: int = 14) -> float:
    return n / d if d else 0.0


def _b_sites(budget: str) -> str:
    b = str(budget)
    if b == "B0":
        return ""
    if b == "B1":
        return "y_settat_ca"
    if b == "B2":
        return "y_settat_ca,y_settat_ac"
    if b == "B3":
        return "y_settat_ca,y_settat_ac,y_benguerir_ca"
    return "conventional_prefix"


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    port = pd.read_csv(ROOT / "results" / "paper_campaign" / "q2_critical_portfolio.csv")
    abl = pd.read_csv(
        ROOT / "results" / "paper_campaign" / "placement_flexibility_ablation.csv"
    )
    miss = pd.read_csv(ROOT / "results" / "paper_campaign" / "q2_critical_missions.csv")
    ea = port[port["vehicle_key"] == "eactros_600"].copy()

    rows: list[dict] = []

    def add(**kw) -> None:
        rows.append(kw)

    for _, r in ea.iterrows():
        budget = str(r["budget"])
        # B = conventional fixed-route with Settat-first installs (NOT "none")
        add(
            table="historical_enum_selection",
            vehicle_key="eactros_600",
            budget=budget,
            method="B_fixed_conventional",
            route_mode="fixed",
            sites=_b_sites(budget),
            ops_served=int(round(float(r["B_ops"]) * 14)),
            ops_frac=_frac(int(round(float(r["B_ops"]) * 14))),
            energy_served=int(round(float(r["B_energy"]) * 14)),
            energy_frac=_frac(int(round(float(r["B_energy"]) * 14))),
            n_missions=14,
            n_limit_reached=None,
            authoritative_for_manuscript=False,
            note=(
                "conventional fixed routing; B0=no sites; B1=y_settat_ca; "
                "B2=y_settat_ca+y_settat_ac — NOT baseline_none"
            ),
            source_csv="results/paper_campaign/q2_critical_portfolio.csv",
        )
        add(
            table="historical_enum_selection",
            vehicle_key="eactros_600",
            budget=budget,
            method="C_fixed_route_opt",
            route_mode="fixed",
            sites=str(r.get("C_sites") or ""),
            ops_served=int(round(float(r["C_ops"]) * 14)),
            ops_frac=_frac(int(round(float(r["C_ops"]) * 14))),
            energy_served=int(round(float(r["C_energy"]) * 14)),
            energy_frac=_frac(int(round(float(r["C_energy"]) * 14))),
            n_missions=14,
            n_limit_reached=int(r.get("C_n_limit") or 0),
            authoritative_for_manuscript=budget in {"B0", "B1", "B2"},
            note="historical fixed-route optimized selection",
            source_csv="results/paper_campaign/q2_critical_portfolio.csv",
        )
        add(
            table="historical_enum_selection",
            vehicle_key="eactros_600",
            budget=budget,
            method="E_joint_multi_enum",
            route_mode="multi",
            sites=str(r.get("E_sites") or ""),
            ops_served=int(round(float(r["E_ops"]) * 14)),
            ops_frac=_frac(int(round(float(r["E_ops"]) * 14))),
            energy_served=int(round(float(r["E_energy"]) * 14)),
            energy_frac=_frac(int(round(float(r["E_energy"]) * 14))),
            n_missions=14,
            n_limit_reached=int(r.get("E_n_limit") or 0),
            authoritative_for_manuscript=budget in {"B0", "B1", "B2"},
            note=(
                "historical screened enum_cap<=2 selection; preserve E=11/14 as "
                "algorithm-selection result — not best observed infra coverage"
            ),
            source_csv="results/paper_campaign/q2_critical_portfolio.csv",
        )

    # Ablation multi_on_C = better evaluated config at B2 sites (per-OD bools)
    abl_b2 = abl[
        (abl["vehicle_key"] == "eactros_600") & (abl["budget"].astype(str) == "B2")
    ]
    if not abl_b2.empty and "ops_multi_on_C" in abl_b2.columns:
        n_multi_c = int(abl_b2["ops_multi_on_C"].astype(bool).sum())
        n_lim_c = (
            int((abl_b2["status_multi_on_C"].astype(str).str.upper() == "LIMIT_REACHED").sum())
            if "status_multi_on_C" in abl_b2.columns
            else 0
        )
        sites_c = str(abl_b2.iloc[0].get("C_sites") or "y_benguerir_ca,y_larache_rt")
        add(
            table="ablation_matched_corners",
            vehicle_key="eactros_600",
            budget="B2",
            method="ablation_multi_on_C",
            route_mode="multi",
            sites=sites_c,
            ops_served=n_multi_c,
            ops_frac=_frac(n_multi_c),
            energy_served=None,
            energy_frac=None,
            n_missions=int(len(abl_b2)),
            n_limit_reached=n_lim_c,
            authoritative_for_manuscript=True,
            note=(
                "better-evaluated B2 multi on Benguerir+Larache; report separately "
                "from historical E (Benguerir-only 11/14)"
            ),
            source_csv="results/paper_campaign/placement_flexibility_ablation.csv",
        )
        n_multi_e = int(abl_b2["ops_multi_on_E"].astype(bool).sum())
        add(
            table="ablation_matched_corners",
            vehicle_key="eactros_600",
            budget="B2",
            method="ablation_multi_on_E",
            route_mode="multi",
            sites=str(abl_b2.iloc[0].get("E_sites") or "y_benguerir_ca"),
            ops_served=n_multi_e,
            ops_frac=_frac(n_multi_e),
            energy_served=None,
            energy_frac=None,
            n_missions=int(len(abl_b2)),
            n_limit_reached=0,
            authoritative_for_manuscript=True,
            note="matched multi on Benguerir alone (aligned with historical E sites)",
            source_csv="results/paper_campaign/placement_flexibility_ablation.csv",
        )

    # Observed infra ladder if regenerated
    infra_sum = INFRA / "infra_ladder_summary.csv"
    if infra_sum.exists():
        for _, r in pd.read_csv(infra_sum).iterrows():
            add(
                table="observed_infra_ladder",
                vehicle_key="eactros_600",
                budget=str(r["infra_config_id"]),
                method="matched_multi_route",
                route_mode="multi",
                sites=str(r.get("sites") or ""),
                ops_served=int(r["ops_served"]),
                ops_frac=float(r["ops_frac"]),
                energy_served=int(r["energy_served"]),
                energy_frac=float(r["energy_frac"]),
                n_missions=int(r["n_missions"]),
                n_limit_reached=int(r["n_limit_reached"]),
                authoritative_for_manuscript=True,
                note=str(r.get("note") or "matched multi infra ladder"),
                source_csv=str(infra_sum.relative_to(ROOT)).replace("\\", "/"),
            )

    # Mission-level energy≠ops diagnosis (LIMIT contamination)
    limit_energy_rows = []
    sub = miss[
        (miss["vehicle_key"] == "eactros_600")
        & (miss["budget"].astype(str).isin(["B1", "B2"]))
        & (miss["method_id"] == "B_fixed_conventional")
    ]
    for _, m in sub.iterrows():
        st = str(m.get("status") or "")
        en = bool(m.get("energy_feasible_energy_only") or m.get("energy_feasible"))
        ops = bool(m.get("operationally_served"))
        if st.upper() == "LIMIT_REACHED" and en and not ops:
            limit_energy_rows.append(
                {
                    "budget": m["budget"],
                    "method_id": m["method_id"],
                    "od_id": m["od_id"],
                    "installed": m.get("installed"),
                    "status": st,
                    "energy_status": m.get("energy_status"),
                    "energy_feasible": en,
                    "operationally_served": ops,
                    "interpretation": (
                        "energy≠ops due to HOS-on LIMIT_REACHED — unresolved, "
                        "NOT certified HOS/physical infeasibility"
                    ),
                }
            )

    out_csv = OUT / "coverage_reconciliation.csv"
    pd.DataFrame(rows).to_csv(out_csv, index=False, lineterminator="\n")
    lim_csv = OUT / "energy_ops_limit_contamination.csv"
    pd.DataFrame(limit_energy_rows).to_csv(lim_csv, index=False, lineterminator="\n")

    notes = OUT / "coverage_reconciliation_notes.md"
    notes.write_text(
        "\n".join(
            [
                "# Coverage reconciliation (Path A corrected)",
                "",
                "## Do not confuse these tables",
                "",
                "1. **historical_enum_selection** — screened E/C under card_cap≤2 "
                "(E at Benguerir = **11/14**). Preserve as algorithm-selection history.",
                "2. **observed_infra_ladder / ablation_multi_on_C** — matched multi-route "
                "evaluation of infrastructure configs. Benguerir+Larache multi can be "
                "**12/14**; that is better observed coverage than screened E and must be reported.",
                "",
                "## B_fixed_conventional (not baseline_none)",
                "",
                "- B0: no sites, fixed route",
                "- B1: `y_settat_ca`, fixed route",
                "- B2: `y_settat_ca,y_settat_ac`, fixed route",
                "",
                "## Energy ≠ ops on B1/B2 conventional",
                "",
                f"Mission cells where energy OPTIMAL but ops false under LIMIT: "
                f"**{len(limit_energy_rows)}** (see `{lim_csv.name}`).",
                "Typical OD: `casa_agadir` with Settat. Do not attribute to HOS physics "
                "without a conclusive OPTIMAL/INFEASIBLE re-solve.",
                "",
                f"Source: `{out_csv.relative_to(ROOT).as_posix()}`",
                "",
            ]
        ),
        encoding="utf-8",
    )
    print(f"wrote {out_csv} rows={len(rows)}")
    print(f"wrote {lim_csv} limit_energy_cells={len(limit_energy_rows)}")
    print(pd.DataFrame(rows)[["table", "budget", "method", "ops_served", "sites"]].to_string(index=False))


if __name__ == "__main__":
    main()
