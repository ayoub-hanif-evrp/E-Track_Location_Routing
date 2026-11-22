#!/usr/bin/env python
"""Full 14-OD B2 eActros ablation at 2e6 expansions (remaining validation)."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import run_stage_c_hos_national as stage_c  # noqa: E402

OUT = ROOT / "results" / "validation" / "p1_nesting" / "full_b2_2e6"


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    print(
        f"[ablation-full] B2 eActros all ODs expansions={stage_c.ABLATION_MAX_EXPANSIONS}",
        flush=True,
    )
    stage_c.ablation_live(
        budgets=("B2",),
        vehicle_filter={"eactros_600"},
        out_dir=OUT,
    )
    print(f"[ablation-full] done -> {OUT}", flush=True)


if __name__ == "__main__":
    main()
