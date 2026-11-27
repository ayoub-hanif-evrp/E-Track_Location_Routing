#!/usr/bin/env python3
"""Read-only verification of release_manifest_sha256.json.

FAILS if any listed file is missing or its SHA-256 differs.
Does NOT regenerate the manifest. Excludes the manifest from its own inventory
(enforced by checking it is not listed).
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MAN = ROOT / "results/final_evidence/manifests/release_manifest_sha256.json"
MAN_REL = "results/final_evidence/manifests/release_manifest_sha256.json"


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _write_lf(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(text.replace("\r\n", "\n").replace("\r", "\n").encode("utf-8"))


def main() -> int:
    if not MAN.exists():
        print("FAIL: manifest missing", MAN)
        return 2
    man = json.loads(MAN.read_text(encoding="utf-8"))
    arts = man.get("artifacts") or []
    fails = []
    if any(a.get("path") == MAN_REL for a in arts):
        fails.append({"path": MAN_REL, "reason": "manifest_included_in_self"})
    for a in arts:
        rel = a["path"]
        p = ROOT / rel
        if not p.exists():
            fails.append({"path": rel, "reason": "missing"})
            continue
        actual = _sha256(p)
        if actual != a.get("sha256"):
            fails.append(
                {
                    "path": rel,
                    "reason": "hash_mismatch",
                    "expected": a.get("sha256"),
                    "actual": actual,
                    "bytes_listed": a.get("bytes"),
                    "bytes_actual": p.stat().st_size,
                }
            )
    report = {
        "manifest": MAN_REL,
        "n_artifacts": len(arts),
        "n_failures": len(fails),
        "passed": len(fails) == 0,
        "failures": fails[:50],
        "read_only": True,
    }
    # Outside hashed evidence package (avoid circular dependency with manifests/)
    vdir = ROOT / "results/final_evidence/validation"
    vdir.mkdir(parents=True, exist_ok=True)
    out = vdir / "clean_checkout_verification.json"
    _write_lf(out, json.dumps(report, indent=2) + "\n")
    md = vdir / "clean_checkout_verification.md"
    _write_lf(
        md,
        f"""# Clean-checkout manifest verification (read-only)

## Commands (do not invert)

```bash
# 1) Generate (writes reports then hashes; excludes manifest from inventory)
python scripts/final_evidence/executable_validation.py

# 2) Verify read-only (must FAIL on any change/missing file; nonzero exit)
python scripts/final_evidence/verify_release_manifest.py
```

Never regenerate the manifest immediately before verification merely to clear mismatches.

## This run

- Artifacts listed: **{len(arts)}**
- Failures: **{len(fails)}**
- Passed: **{len(fails) == 0}**

Verification reports live under `results/final_evidence/validation/clean_checkout_verification.*`
(outside the hashed package).

`.gitattributes` enforces `eol=lf` for scientific text artifacts.
""",
    )
    if fails:
        print("MANIFEST_VERIFY_FAIL", fails[:5])
        print("FAILED")
        return 1
    print(f"VERIFIED ok n={len(arts)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
