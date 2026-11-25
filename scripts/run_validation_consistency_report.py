#!/usr/bin/env python
"""Consistency report: portfolio aggregates vs missions vs ablation."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "results" / "paper_campaign"
VAL = ROOT / "results" / "validation"
REPORT = VAL / "consistency_report.json"


def _mean_bool(s: pd.Series) -> float | None:
    if s.empty:
        return None
    return float(s.astype(bool).mean())


def main() -> None:
    VAL.mkdir(parents=True, exist_ok=True)
    issues: list[dict] = []
    checks: list[dict] = []

    port_path = OUT / "q2_critical_portfolio.csv"
    miss_path = OUT / "q2_critical_missions.csv"
    abl_path = OUT / "placement_flexibility_ablation.csv"

    if not port_path.exists():
        issues.append({"level": "error", "msg": "missing q2_critical_portfolio.csv"})
        REPORT.write_text(json.dumps({"issues": issues}, indent=2), encoding="utf-8")
        print("FAIL: missing portfolio", flush=True)
        return

    port = pd.read_csv(port_path)
    for _, r in port.iterrows():
        pipe = str(r.get("pipeline", ""))
        if "full_enum" in pipe and int(r.get("enum_cardinality_cap") or 0) < 9:
            issues.append(
                {
                    "level": "warning",
                    "msg": f"pipeline claims full_enum but cap={r.get('enum_cardinality_cap')}",
                    "row": f"{r.vehicle_key}/{r.budget}",
                }
            )
        checks.append(
            {
                "kind": "portfolio_row",
                "vehicle_key": r.vehicle_key,
                "budget": str(r.budget),
                "C_ops": float(r.C_ops),
                "E_ops": float(r.E_ops),
                "pipeline": pipe,
                "E_n_limit": r.get("E_n_limit"),
            }
        )

    if miss_path.exists():
        miss = pd.read_csv(miss_path)
        for (vk, bud, method), g in miss.groupby(["vehicle_key", "budget", "method_id"]):
            if "operationally_served" not in g.columns:
                continue
            ops = float(g["operationally_served"].astype(bool).mean())
            n_limit = int((g["status"].astype(str).str.upper() == "LIMIT_REACHED").sum()) if "status" in g.columns else None
            checks.append(
                {
                    "kind": "mission_aggregate",
                    "vehicle_key": vk,
                    "budget": str(bud),
                    "method_id": method,
                    "ops": ops,
                    "n_limit": n_limit,
                }
            )
            # Match E / C portfolio
            pref = port[(port.vehicle_key == vk) & (port.budget.astype(str) == str(bud))]
            if pref.empty:
                continue
            if method == "E_joint_multi_enum":
                ref = float(pref.iloc[0]["E_ops"])
                if abs(ops - ref) > 1e-9:
                    issues.append(
                        {
                            "level": "error",
                            "msg": f"E mission aggregate {ops} ≠ portfolio E_ops {ref}",
                            "row": f"{vk}/{bud}",
                        }
                    )
            if method == "C_fixed_optimized":
                ref = float(pref.iloc[0]["C_ops"])
                if abs(ops - ref) > 1e-9:
                    issues.append(
                        {
                            "level": "error",
                            "msg": f"C mission aggregate {ops} ≠ portfolio C_ops {ref}",
                            "row": f"{vk}/{bud}",
                        }
                    )

    if abl_path.exists():
        abl = pd.read_csv(abl_path)
        for (vk, bud), g in abl.groupby(["vehicle_key", "budget"]):
            multi_e = _mean_bool(g["ops_multi_on_E"])
            fixed_c = _mean_bool(g["ops_fixed_on_C"])
            multi_c = _mean_bool(g["ops_multi_on_C"]) if "ops_multi_on_C" in g.columns else None
            pref = port[(port.vehicle_key == vk) & (port.budget.astype(str) == str(bud))]
            if pref.empty:
                continue
            e_ops = float(pref.iloc[0]["E_ops"])
            checks.append(
                {
                    "kind": "ablation_vs_portfolio",
                    "vehicle_key": vk,
                    "budget": str(bud),
                    "ablation_multi_E": multi_e,
                    "portfolio_E": e_ops,
                    "ablation_fixed_C": fixed_c,
                    "ablation_multi_C": multi_c,
                    "portfolio_C": float(pref.iloc[0]["C_ops"]),
                }
            )
            if multi_e is not None and abs(multi_e - e_ops) > 1e-9:
                issues.append(
                    {
                        "level": "warning",
                        "msg": f"ablation multi_on_E {multi_e} ≠ E_ops {e_ops}",
                        "row": f"{vk}/{bud}",
                    }
                )
            # Better-evaluated portfolio than screened E (e.g. multi on C sites)
            if multi_c is not None and multi_c > e_ops + 1e-12:
                issues.append(
                    {
                        "level": "warning",
                        "msg": (
                            f"better_evaluated_than_E: ablation multi_on_C={multi_c} > "
                            f"screened E_ops={e_ops} — do not claim E as best-known B2 coverage"
                        ),
                        "row": f"{vk}/{bud}",
                    }
                )
            if "nesting_class_on_C" in g.columns:
                n_lim = int((g["nesting_class_on_C"] == "LIMIT_ARTIFACT").sum())
                if n_lim:
                    issues.append(
                        {
                            "level": "warning",
                            "msg": f"{n_lim} LIMIT_ARTIFACT nesting rows on C — do not claim certified flex loss",
                            "row": f"{vk}/{bud}",
                        }
                    )

    # Incorrect solver-status interpretations: energy OPTIMAL + ops false under LIMIT
    if miss_path.exists():
        miss = pd.read_csv(miss_path)
        lim = miss[miss["status"].astype(str).str.upper() == "LIMIT_REACHED"].copy()
        energy_col = (
            "energy_feasible_energy_only"
            if "energy_feasible_energy_only" in lim.columns
            else "energy_feasible"
            if "energy_feasible" in lim.columns
            else None
        )
        if energy_col and "operationally_served" in lim.columns:
            bad = lim[
                lim[energy_col].astype(bool) & ~lim["operationally_served"].astype(bool)
            ]
        else:
            bad = lim.iloc[0:0]
        n_bad = int(len(bad))
        checks.append(
            {
                "kind": "limit_vs_energy_ops",
                "n_limit_energy_true_ops_false": n_bad,
                "ods": sorted(bad["od_id"].astype(str).unique().tolist())[:12]
                if n_bad and "od_id" in bad.columns
                else [],
            }
        )
        if n_bad:
            issues.append(
                {
                    "level": "warning",
                    "msg": (
                        f"{n_bad} LIMIT_REACHED cells have energy feasible but ops false — "
                        "do not interpret as HOS/physical infeasibility without conclusive re-solve"
                    ),
                    "row": "missions/LIMIT_REACHED",
                }
            )

    # Observed infra ladder vs historical E (if Path A ladder exists)
    infra = VAL / "path_a" / "infra_ladder" / "infra_ladder_summary.csv"
    if infra.exists() and not port.empty:
        il = pd.read_csv(infra)
        e_b2 = port[(port.vehicle_key == "eactros_600") & (port.budget.astype(str) == "B2")]
        if not e_b2.empty and not il.empty:
            e_ops = float(e_b2.iloc[0]["E_ops"])
            for _, r in il.iterrows():
                ops_frac = float(r["ops_frac"])
                checks.append(
                    {
                        "kind": "infra_ladder_vs_E",
                        "infra_config_id": r["infra_config_id"],
                        "ops_frac": ops_frac,
                        "historical_E_ops": e_ops,
                        "n_limit": int(r.get("n_limit_reached") or 0),
                    }
                )
                if ops_frac > e_ops + 1e-12:
                    issues.append(
                        {
                            "level": "warning",
                            "msg": (
                                f"observed {r['infra_config_id']} ops={ops_frac} > "
                                f"historical E={e_ops} — report observed ladder separately"
                            ),
                            "row": str(r["infra_config_id"]),
                        }
                    )
                if int(r.get("n_limit_reached") or 0) > 0:
                    issues.append(
                        {
                            "level": "warning",
                            "msg": (
                                f"{r['infra_config_id']} still has "
                                f"{int(r['n_limit_reached'])} LIMIT — unresolved"
                            ),
                            "row": str(r["infra_config_id"]),
                        }
                    )

    payload = {
        "n_checks": len(checks),
        "n_issues": len(issues),
        "n_errors": sum(1 for i in issues if i["level"] == "error"),
        "issues": issues,
        "checks": checks,
    }
    REPORT.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(
        f"consistency: checks={len(checks)} issues={len(issues)} "
        f"errors={payload['n_errors']} -> {REPORT}",
        flush=True,
    )


if __name__ == "__main__":
    main()
