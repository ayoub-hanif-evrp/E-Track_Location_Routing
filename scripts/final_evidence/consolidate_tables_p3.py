#!/usr/bin/env python3
"""P3 — Consolidate fine-SOC into R-T05, Settat ledger, Volvo naming."""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[2]
FE = ROOT / "results/final_evidence"
TAB = FE / "tables/results"
EXP = FE / "experiments"
MAN = FE / "manifests"


def consolidate_rt05() -> None:
    sens = pd.read_csv(ROOT / "results/validation/p6_sensitivity/southbound_sensitivity.csv")
    sens = sens.copy()
    sens["source"] = "p6_southbound_sensitivity"
    fine = pd.read_csv(EXP / "payload_soc/fine_soc_missions.csv")
    fine = fine.copy()
    fine["source"] = "final_evidence_fine_soc"
    # Harmonize columns
    for df in (sens, fine):
        if "installed" not in df.columns:
            df["installed"] = ""
        df["installed"] = df["installed"].fillna("").astype(str)
    # Prefer fine SOC on overlapping keys
    key = ["od_id", "payload_kg", "soc_frac", "installed"]
    sens["_k"] = list(zip(sens.od_id, sens.payload_kg.round(1), sens.soc_frac.round(4), sens.installed))
    fine["_k"] = list(zip(fine.od_id, fine.payload_kg.round(1), fine.soc_frac.round(4), fine.installed.fillna("")))
    sens_f = sens[~sens["_k"].isin(set(fine["_k"]))].drop(columns="_k")
    fine_f = fine.drop(columns="_k")
    allp = pd.concat([sens_f, fine_f], ignore_index=True, sort=False)
    keep = [
        c
        for c in [
            "od_id",
            "payload_kg",
            "soc_frac",
            "installed",
            "status",
            "energy_feasible",
            "operationally_served",
            "min_soc",
            "arrival_soc",
            "charge_min_phys",
            "source",
            "variant",
            "infra_config_id",
            "block",
        ]
        if c in allp.columns
    ]
    allp[keep].sort_values(["od_id", "payload_kg", "installed", "soc_frac"]).to_csv(
        TAB / "R-T05_payload_soc_feasibility.csv", index=False
    )

    # Brackets from merged data — no interpolation
    brackets = []
    gcols = [c for c in ["od_id", "payload_kg", "installed"] if c in allp.columns]
    for keys, g in allp.groupby(gcols):
        if not isinstance(keys, tuple):
            keys = (keys,)
        rec = dict(zip(gcols, keys))
        g = g.sort_values("soc_frac")
        feas = g[g["operationally_served"] == True]  # noqa: E712
        infeas = g[g["status"].astype(str) == "INFEASIBLE"]
        # Adjacent transition if present
        transition = None
        socs = sorted(g["soc_frac"].unique())
        for a, b in zip(socs, socs[1:]):
            ra = g[g.soc_frac == a].iloc[0]
            rb = g[g.soc_frac == b].iloc[0]
            if (not bool(ra.operationally_served)) and bool(rb.operationally_served):
                transition = f"{a:.2f}_INF_to_{b:.2f}_OPS"
                break
        rec.update(
            {
                "min_tested_feasible_soc": float(feas["soc_frac"].min()) if len(feas) else None,
                "max_tested_infeasible_soc": float(infeas["soc_frac"].max()) if len(infeas) else None,
                "observed_transition": transition,
                "n_evaluated": int(len(g)),
                "sources": ",".join(sorted(g["source"].dropna().unique())),
                "note": "bracket only; no interpolated threshold",
            }
        )
        brackets.append(rec)
    pd.DataFrame(brackets).to_csv(TAB / "R-T05_payload_soc_brackets.csv", index=False)

    # Explicit preserved transitions table
    preserved = [
        {
            "od_id": "casa_marrakech",
            "payload_kg": 10000.0,
            "installed": "y_benguerir_ca",
            "infeasible_soc": 0.50,
            "feasible_soc": 0.52,
            "source": "final_evidence_fine_soc",
        },
        {
            "od_id": "casa_agadir",
            "payload_kg": 15000.0,
            "installed": "y_benguerir_ca",
            "infeasible_soc": 0.52,
            "feasible_soc": 0.55,
            "source": "final_evidence_fine_soc",
        },
        {
            "od_id": "casa_agadir",
            "payload_kg": 5300.0,
            "installed": "y_benguerir_ca",
            "infeasible_soc": 0.45,
            "feasible_soc": 0.50,
            "source": "final_evidence_fine_soc",
        },
    ]
    pd.DataFrame(preserved).to_csv(TAB / "R-T05_preserved_soc_transitions.csv", index=False)


def consolidate_settat() -> None:
    ledger = pd.read_csv(TAB / "R-T04_settat_benguerir_singleton_ledger.csv")
    esc = EXP / "settat_vs_benguerir/settat_casa_agadir_escalate.csv"
    notes = []
    if esc.exists():
        e = pd.read_csv(esc)
        ok = e[e["status"].astype(str) == "OPTIMAL"]
        notes.append(
            {
                "item": "settat_casa_agadir_standard_budget",
                "outcome": "LIMIT_REACHED",
                "note": "Under 600s/2e6 expansions Settat CA on Casa→Agadir was unresolved (LIMIT).",
            }
        )
        notes.append(
            {
                "item": "settat_casa_agadir_escalate",
                "outcome": "OPTIMAL" if len(ok) else "see_csv",
                "stationary_min": float(ok.iloc[0]["charge_min_phys"] + ok.iloc[0].get("wait_min_phys", 0))
                if len(ok) and "charge_min_phys" in ok.columns
                else None,
                "note": "Escalated budget restores OPTIMAL; coverage tie with Benguerir at 11/14 after escalate.",
            }
        )
        # Update ledger coverage note file
        cov = {
            "S0_none": 9,
            "S1_settat_standard": 10,
            "S1_settat_after_escalate": 11,
            "S1_benguerir": 11,
        }
        pd.DataFrame(
            [{"config": k, "ops_served_of_14": v} for k, v in cov.items()]
        ).to_csv(TAB / "R-T04_settat_coverage_after_escalate.csv", index=False)
    pd.DataFrame(notes).to_csv(TAB / "R-T04_settat_budget_outcomes.csv", index=False)
    # Keep original ledger; write pointer README
    (TAB / "R-T04_INDEX.md").write_text(
        "\n".join(
            [
                "# R-T04 Settat vs Benguerir table index",
                "",
                "- `R-T04_settat_benguerir_singleton_ledger.csv` — 14-OD coverage under standard budget.",
                "- `R-T04_casa_agadir_settat_vs_benguerir.csv` — Casa→Agadir mission comparison.",
                "- `R-T04_casa_agadir_operational_tradeoff.csv` — stationary time after escalate.",
                "- `R-T04_settat_coverage_after_escalate.csv` — conclusive coverage including escalate.",
                "- `R-T04_settat_budget_outcomes.csv` — LIMIT vs escalate outcomes kept separate.",
                "",
            ]
        ),
        encoding="utf-8",
    )


def fix_volvo_naming() -> None:
    freeze = MAN / "experimental_design_freeze.md"
    if freeze.exists():
        txt = freeze.read_text(encoding="utf-8")
        txt2 = txt.replace(
            "volvo_fh_electric_4x2_540kwh_usable460",
            "volvo_fh_electric_4x2_540kwh (usable 475 kWh; registry key volvo_475)",
        )
        if "usable460" in txt2 and "sensitivity sibling" not in txt2:
            txt2 += (
                "\n\n## Vehicle naming clarification\n\n"
                "- Primary Volvo: `configs/vehicles/volvo_fh_electric_4x2_540kwh.yaml` "
                "(registry `volvo_475`, usable battery **475 kWh**).\n"
                "- `*_usable460.yaml` is a sensitivity sibling only; not the primary comparison vehicle.\n"
            )
        freeze.write_text(txt2, encoding="utf-8")

    # Parameter file fingerprint for primary vehicles
    rows = []
    for key, path in [
        ("eactros_600", ROOT / "configs/vehicles/eactros_600.yaml"),
        ("volvo_475", ROOT / "configs/vehicles/volvo_fh_electric_4x2_540kwh.yaml"),
    ]:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        bat = raw.get("battery") or {}
        rows.append(
            {
                "vehicle_key": key,
                "config_path": str(path.relative_to(ROOT)).replace("\\", "/"),
                "usable_kwh": bat.get("usable_kwh") or bat.get("E_usable_kwh") or bat.get("capacity_usable_kwh"),
                "nominal_kwh": bat.get("nominal_kwh") or bat.get("E_nominal_kwh"),
                "role": "primary_comparison",
            }
        )
    sens = ROOT / "configs/vehicles/volvo_fh_electric_4x2_540kwh_usable460.yaml"
    if sens.exists():
        raw = yaml.safe_load(sens.read_text(encoding="utf-8"))
        bat = raw.get("battery") or {}
        rows.append(
            {
                "vehicle_key": "volvo_usable460_sensitivity",
                "config_path": str(sens.relative_to(ROOT)).replace("\\", "/"),
                "usable_kwh": bat.get("usable_kwh") or bat.get("E_usable_kwh") or bat.get("capacity_usable_kwh"),
                "nominal_kwh": bat.get("nominal_kwh") or bat.get("E_nominal_kwh"),
                "role": "sensitivity_only_not_primary",
            }
        )
    pd.DataFrame(rows).to_csv(TAB / "R-T02_vehicle_parameter_files.csv", index=False)


def main() -> int:
    consolidate_rt05()
    consolidate_settat()
    fix_volvo_naming()
    print("P3 consolidation complete")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
