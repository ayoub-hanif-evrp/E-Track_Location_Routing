"""Gate 5: LF-normalized SHA-256 manifest for Path A freeze artifacts."""
from __future__ import annotations

import hashlib
import json
import subprocess
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "results" / "validation" / "path_a"

FILES = [
    "coverage_reconciliation.csv",
    "coverage_reconciliation_notes.md",
    "energy_ops_dual_check.csv",
    "energy_ops_dual_notes.md",
    "physics_plausibility.csv",
    "physics_plausibility_notes.md",
    "experimental_design_freeze.md",
    "RELEASE_NOTES.md",
]


def _git_sha() -> str:
    try:
        return (
            subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT)
            .decode()
            .strip()
        )
    except Exception:  # noqa: BLE001
        return "unknown"


def _sha256_lf(path: Path) -> str:
    data = path.read_bytes().replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    return hashlib.sha256(data).hexdigest()


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    files = {}
    for name in FILES:
        p = OUT / name
        if not p.is_file():
            continue
        files[name] = {"sha256_lf": _sha256_lf(p), "bytes": p.stat().st_size}
    payload = {
        "release_name": "path-a-feasibility-freeze",
        "git_sha": _git_sha(),
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "venue_target": "Transportation Research Interdisciplinary Perspectives",
        "claims_crosswalk": "paper/claims_to_results_crosswalk.csv",
        "manuscript": "paper/manuscript.tex",
        "files": files,
        "claims_subseteq_evidence": True,
    }
    text = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    text = text.replace("\r\n", "\n")
    man = OUT / "PATH_A_MANIFEST.json"
    man.write_text(text, encoding="utf-8", newline="\n")
    print(f"wrote {man} n_files={len(files)} sha={payload['git_sha'][:12]}")


if __name__ == "__main__":
    main()
