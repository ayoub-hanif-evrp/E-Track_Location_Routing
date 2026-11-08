#!/usr/bin/env python3
"""Run Task 03A synthetic MRLS benchmarks vs reference solver."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from morocco_etruck.optimization.instances import load_synthetic_instances  # noqa: E402
from morocco_etruck.optimization.label_setting import solve_mrls  # noqa: E402
from morocco_etruck.optimization.reference_solver import solve_reference  # noqa: E402


def _charge_total(actions: list) -> int:
    return sum(int(a.get("delta_e_kwh", 0)) for a in actions if a.get("type") == "CHARGE")


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--config",
        type=Path,
        default=ROOT / "configs" / "optimization" / "synthetic_instances.yaml",
    )
    p.add_argument(
        "--out",
        type=Path,
        default=ROOT / "results" / "routing_benchmarks.csv",
    )
    args = p.parse_args()

    instances = load_synthetic_instances(args.config)
    rows = []
    ok_all = True
    for inst in instances:
        mrls = solve_mrls(inst, use_dominance=True)
        ref = solve_reference(inst)
        match = mrls.status == ref.status and mrls.objective == ref.objective
        exp = inst.expected
        exp_ok = True
        if exp.get("status") and mrls.status.value != exp["status"]:
            exp_ok = False
        if "objective" in exp and mrls.objective != exp["objective"]:
            exp_ok = False
        if "path" in exp and mrls.path_nodes != list(exp["path"]):
            exp_ok = False
        ch = _charge_total(mrls.actions)
        if "charge_total_kwh" in exp and ch != int(exp["charge_total_kwh"]):
            exp_ok = False

        dom_off_obj = ""
        dom_same = ""
        if inst.name == "I_dominance":
            off = solve_mrls(inst, use_dominance=False)
            dom_off_obj = off.objective if off.objective is not None else off.status.value
            dom_same = bool(off.status == mrls.status and off.objective == mrls.objective)
            if not dom_same:
                exp_ok = False

        print(
            f"{inst.name:24s} MRLS={mrls.status.value}/{mrls.objective} "
            f"REF={ref.status.value}/{ref.objective} match={match} expected={exp_ok}"
        )
        if not match or not exp_ok:
            ok_all = False

        rows.append(
            {
                "instance": inst.name,
                "mrls_status": mrls.status.value,
                "ref_status": ref.status.value,
                "mrls_objective": mrls.objective,
                "ref_objective": ref.objective,
                "mrls_path": "->".join(mrls.path_nodes),
                "ref_path": "->".join(ref.path_nodes),
                "mrls_charge_kwh": ch,
                "match_ref": match,
                "match_expected": exp_ok,
                "mrls_generated": mrls.stats.get("labels_generated"),
                "mrls_expanded": mrls.stats.get("labels_expanded"),
                "mrls_dominated": mrls.stats.get("labels_dominated"),
                "mrls_runtime_s": round(float(mrls.stats.get("runtime_s", 0.0)), 6),
                "ref_runtime_s": round(float(ref.stats.get("runtime_s", 0.0)), 6),
                "dominance_off_objective": dom_off_obj,
                "dominance_same_opt": dom_same,
            }
        )

    df = pd.DataFrame(rows)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(args.out, index=False)
    print(f"Wrote {args.out}")
    return 0 if ok_all else 1


if __name__ == "__main__":
    raise SystemExit(main())
