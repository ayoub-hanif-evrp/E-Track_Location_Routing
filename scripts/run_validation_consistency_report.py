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
            pref = port[(port.vehicle_key == vk) & (port.budget.astype(str) == str(bud))]
            if pref.empty:
                continue
            checks.append(
                {
                    "kind": "ablation_vs_portfolio",
                    "vehicle_key": vk,
                    "budget": str(bud),
                    "ablation_multi_E": multi_e,
                    "portfolio_E": float(pref.iloc[0]["E_ops"]),
                    "ablation_fixed_C": fixed_c,
                    "portfolio_C": float(pref.iloc[0]["C_ops"]),
                }
            )
            if multi_e is not None and abs(multi_e - float(pref.iloc[0]["E_ops"])) > 1e-9:
                issues.append(
                    {
                        "level": "warning",
                        "msg": f"ablation multi_on_E {multi_e} ≠ E_ops {float(pref.iloc[0]['E_ops'])}",
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
