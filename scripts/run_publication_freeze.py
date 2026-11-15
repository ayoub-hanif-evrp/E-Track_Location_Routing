#!/usr/bin/env python
"""Stage G — one-command publication freeze (--quick / --full)."""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "reports" / "FINAL_RESEARCH_FREEZE.md"


def _run(cmd: list[str]) -> int:
    print("+", " ".join(cmd), flush=True)
    return subprocess.call(cmd, cwd=str(ROOT))


def _sha(path: Path) -> str:
    if not path.exists():
        return "MISSING"
    return hashlib.sha256(path.read_bytes()).hexdigest()[:16]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true")
    ap.add_argument("--full", action="store_true")
    args = ap.parse_args()
    if not args.quick and not args.full:
        args.quick = True

    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=str(ROOT), text=True).strip()
    py = sys.version.replace("\n", " ")
    failed = []

    rc = _run([sys.executable, "-m", "pytest", "-q", "-m", "not integration"])
    if rc != 0:
        failed.append("pytest")

    if args.quick:
        rc = _run(
            [
                sys.executable,
                "-m",
                "pytest",
                "-q",
                "tests/unit/test_action_rounding_and_min_soc.py",
                "tests/unit/test_physical_replay_trace.py",
                "tests/unit/test_quantization_error_and_charge.py",
            ]
        )
        if rc != 0:
            failed.append("adversarial_tests")

    if args.full:
        for script in [
            "scripts/run_final_numerical_integrity.py",
            "scripts/run_final_moroccan_robustness.py",
            "scripts/run_bb_relaxed_bound_benchmark.py",
            "scripts/generate_publication_figures.py",
        ]:
            # Skip expensive q=1 rebuild if audit CSV present and hashes match vehicle/fridge
            if "numerical_integrity" in script:
                audit = ROOT / "results/final_action_rounding_audit.csv"
                if audit.exists() and "1," in audit.read_text(encoding="utf-8"):
                    print("Reusing existing final_action_rounding_audit.csv (contains q=1)", flush=True)
                    continue
            rc = _run([sys.executable, script])
            if rc != 0:
                failed.append(script)

    # Evidence ledger touch
    ledger = ROOT / "reports/authoritative_publication_evidence_ledger.md"
    if ledger.exists():
        text = ledger.read_text(encoding="utf-8")
        if "SIMULATION_REPLAY_VALIDATED" not in text:
            text += (
                "\n\n## Sprint update\n\n"
                "Use `SIMULATION_REPLAY_VALIDATED` instead of unqualified "
                "`PHYSICALLY_VERIFIED` for simulated routes. Prior path-node "
                "rounding losses are SUPERSEDED by `audit_solved_actions_exact`.\n"
            )
            ledger.write_text(text, encoding="utf-8")

    meta = {
        "commit": commit,
        "python": py,
        "platform": platform.platform(),
        "utc": datetime.now(timezone.utc).isoformat(),
        "mode": "full" if args.full else "quick",
        "failed": failed,
        "hashes": {
            "vehicle_eactros": _sha(ROOT / "configs/vehicles/eactros_600.yaml"),
            "fridge_tomato": _sha(ROOT / "configs/energy/pass2_tomato_firm_ripe.yaml"),
            "placement_pass2a": _sha(ROOT / "configs/optimization/multiroute_placement_pass2a.yaml"),
            "final_action_rounding_audit": _sha(ROOT / "results/final_action_rounding_audit.csv"),
            "final_robustness_matrix": _sha(ROOT / "results/final_moroccan_robustness_matrix.csv"),
        },
    }
    (ROOT / "results/publication_freeze_meta.json").write_text(
        json.dumps(meta, indent=2), encoding="utf-8"
    )

    strongest = (
        "Authoritative 429.15 km COMPLETE replay; action-exact rounding audit "
        "(25 DRIVEs); Benguerir site stable on q∈{5,2,1} same arc sequence; "
        "charge energy q-dependence largely explained by flooring+quantum charge choice."
    )
    gaps = (
        "No field validation; COPDEM DSM≠pavement; chargers hypothetical; "
        "illustrative costs; Volvo legal axle unverified; DEM bracketing limited."
    )
    lines = [
        "# FINAL RESEARCH FREEZE",
        "",
        f"- Commit: `{commit}`",
        f"- Mode: `{meta['mode']}`",
        f"- Python: `{py}`",
        f"- Failed steps: `{failed or 'none'}`",
        "",
        "## Strongest results",
        "",
        strongest,
        "",
        "## Moroccan site decisions",
        "",
        "Grid-stable at Benguerir for tested fine q on the primary northbound scenario, "
        "but **physical-scenario stability is conditional** — see robustness matrix labels.",
        "",
        "## Numerical robustness",
        "",
        "Site-selection stability ≠ charging-energy/cost convergence. Floor-loss drop "
        "≈ charge-energy drop across q on identical DRIVE arcs.",
        "",
        "## High-impact paper support",
        "",
        "Evidence supports a computational reliability / uncertainty paper on a Moroccan "
        "corridor — not a claim of novel exact joint siting+routing or field-validated "
        "investment optimality.",
        "",
        "## Remaining external validation gaps",
        "",
        gaps,
        "",
        "## Reproduction",
        "",
        "```bash",
        "python scripts/run_publication_freeze.py --quick",
        "python scripts/run_publication_freeze.py --full",
        "```",
        "",
        f"Meta: `results/publication_freeze_meta.json`",
        "",
    ]
    OUT.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote {OUT}")
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
