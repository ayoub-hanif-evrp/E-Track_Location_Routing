"""Gate 0: authoritative budget × method coverage reconciliation (Path A).

Resolves the 11/14 vs 12/14 confusion:
- Headline B2 C_ops = 11/14 (fixed route on Benguerir+Larache)
- Ablation ops_multi_on_C = 12/14 (multi route on same C sites; casa_marrakech FLEX_GAIN)
- Headline B2 E_ops = 11/14 (multi on Benguerir alone; casa_tangier needs Larache)
- Ball D_energy = 12/14 is energy-only under open charger set — NOT B2 ops

Writes results/validation/path_a/coverage_reconciliation.csv (+ notes.md).
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "results" / "validation" / "path_a"


def _frac(n: int, d: int = 14) -> float:
    return n / d if d else 0.0


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    port = pd.read_csv(ROOT / "results" / "paper_campaign" / "q2_critical_portfolio.csv")
    abl = pd.read_csv(
        ROOT / "results" / "paper_campaign" / "placement_flexibility_ablation.csv"
    )
    ea = port[port["vehicle_key"] == "eactros_600"].copy()

    rows: list[dict] = []

    def add(
        *,
        vehicle: str,
        budget: str,
        method: str,
        route_mode: str,
        sites: str,
        ops_n: int,
        energy_n: int | None,
        n_limit: int,
        n_infeas: int | None,
        n_optimal: int | None,
        source: str,
        authoritative: bool,
        note: str,
    ) -> None:
        rows.append(
            {
                "vehicle_key": vehicle,
                "budget": budget,
                "method": method,
                "route_mode": route_mode,
                "sites": sites,
                "ops_served": ops_n,
                "ops_frac": _frac(ops_n),
                "energy_served": energy_n,
                "energy_frac": None if energy_n is None else _frac(energy_n),
                "n_missions": 14,
                "n_limit_reached": n_limit,
                "n_infeasible": n_infeas,
                "n_optimal": n_optimal,
                "source_csv": source,
                "authoritative_for_manuscript": authoritative,
                "note": note,
            }
        )

    for _, r in ea.iterrows():
        budget = str(r["budget"])
        add(
            vehicle="eactros_600",
            budget=budget,
            method="B_baseline_none",
            route_mode="multi",
            sites="",
            ops_n=int(round(float(r["B_ops"]) * 14)),
            energy_n=int(round(float(r["B_energy"]) * 14)),
            n_limit=int(r.get("n_limit_reached") or 0),
            n_infeas=None,
            n_optimal=None,
            source="results/paper_campaign/q2_critical_portfolio.csv",
            authoritative=budget in {"B0", "B1", "B2"},
            note="frozen headline portfolio",
        )
        add(
            vehicle="eactros_600",
            budget=budget,
            method="C_fixed_route_opt",
            route_mode="fixed",
            sites=str(r.get("C_sites") or ""),
            ops_n=int(round(float(r["C_ops"]) * 14)),
            energy_n=int(round(float(r["C_energy"]) * 14)),
            n_limit=int(r.get("C_n_limit") or 0),
            n_infeas=None,
            n_optimal=None,
            source="results/paper_campaign/q2_critical_portfolio.csv",
            authoritative=budget in {"B0", "B1", "B2"},
            note="frozen headline portfolio",
        )
        add(
            vehicle="eactros_600",
            budget=budget,
            method="E_joint_multi_enum",
            route_mode="multi",
            sites=str(r.get("E_sites") or ""),
            ops_n=int(round(float(r["E_ops"]) * 14)),
            energy_n=int(round(float(r["E_energy"]) * 14)),
            n_limit=int(r.get("E_n_limit") or 0),
            n_infeas=None,
            n_optimal=None,
            source="results/paper_campaign/q2_critical_portfolio.csv",
            authoritative=budget in {"B0", "B1", "B2"},
            note="frozen headline portfolio; card_cap<=2 screen45 final600",
        )

    # Ablation corners at B2 (matched 600s / 2e6)
    for corner, ops_col, status_col, sites_col, mode in [
        ("ablation_fixed_on_C", "ops_fixed_on_C", "status_fixed_on_C", "C_sites", "fixed"),
        ("ablation_multi_on_C", "ops_multi_on_C", "status_multi_on_C", "C_sites", "multi"),
        ("ablation_fixed_on_E", "ops_fixed_on_E", "status_fixed_on_E", "E_sites", "fixed"),
        ("ablation_multi_on_E", "ops_multi_on_E", "status_multi_on_E", "E_sites", "multi"),
    ]:
        ops_n = int(abl[ops_col].sum())
        st = abl[status_col].astype(str).str.upper()
        sites = str(abl[sites_col].iloc[0]) if len(abl) else ""
        add(
            vehicle="eactros_600",
            budget="B2",
            method=corner,
            route_mode=mode,
            sites=sites,
            ops_n=ops_n,
            energy_n=None,
            n_limit=int((st == "LIMIT_REACHED").sum()),
            n_infeas=int((st == "INFEASIBLE").sum()),
            n_optimal=int((st == "OPTIMAL").sum()),
            source="results/paper_campaign/placement_flexibility_ablation.csv",
            authoritative=(corner == "ablation_multi_on_E"),
            note=(
                "12/14 appears ONLY as multi-on-C (casa_marrakech FLEX_GAIN); "
                "NOT interchangeable with headline E (Benguerir alone=11/14) "
                "or headline C fixed (11/14)"
                if corner == "ablation_multi_on_C"
                else "matched ablation corner; 0 LIMIT at 2e6"
            ),
        )

    # Explicit OD footnotes
    flex = abl[(abl["ops_multi_on_C"]) & (~abl["ops_fixed_on_C"])]
    larache_only = abl[(abl["ops_multi_on_C"]) & (~abl["ops_multi_on_E"])]
    od_notes = []
    if len(flex):
        od_notes.append(
            "FLEX_GAIN on C sites: " + ",".join(flex["od_id"].astype(str).tolist())
        )
    if len(larache_only):
        od_notes.append(
            "served with Larache on C but not Benguerir-only E: "
            + ",".join(larache_only["od_id"].astype(str).tolist())
        )

    df = pd.DataFrame(rows)
    out_csv = OUT / "coverage_reconciliation.csv"
    df.to_csv(out_csv, index=False)

    notes = OUT / "coverage_reconciliation_notes.md"
    notes.write_text(
        "\n".join(
            [
                "# Coverage reconciliation (Path A Gate 0)",
                "",
                "## Authoritative manuscript ladder (eActros ops)",
                "",
                "| Budget | C fixed | E multi | Sites C | Sites E |",
                "|--------|---------|---------|---------|---------|",
                "| B0 | 9/14 | 9/14 | — | — |",
                "| B1 | 10/14 (Larache) | 11/14 (Benguerir CA) | y_larache_rt | y_benguerir_ca |",
                "| B2 | 11/14 (Benguerir+Larache) | 11/14 (Benguerir CA) | both | y_benguerir_ca |",
                "",
                "## Why 12/14 must not be the B2 headline",
                "",
                "- Ablation **multi_on_C** = **12/14** because `casa_marrakech` is "
                "INFEASIBLE under fixed but OPTIMAL under multi on C sites (FLEX_GAIN).",
                "- Headline **C** optimizes the **fixed-route** mask → still **11/14**.",
                "- Headline **E** installs only Benguerir → `casa_tangier` fails "
                "(needs Larache direction) → **11/14**.",
                "- Ball `D_energy=12/14` is an energy-only figure under a larger "
                "charger set — not B2 operational coverage.",
                "",
                "## OD footnotes",
                "",
            ]
            + [f"- {n}" for n in (od_notes or ["(none)"])]
            + [
                "",
                f"Source table: `{out_csv.relative_to(ROOT).as_posix()}`",
                "",
            ]
        ),
        encoding="utf-8",
    )
    print(f"wrote {out_csv}")
    print(f"wrote {notes}")
    print(df[df["authoritative_for_manuscript"]][
        ["budget", "method", "ops_served", "ops_frac", "sites"]
    ].to_string(index=False))


if __name__ == "__main__":
    main()
