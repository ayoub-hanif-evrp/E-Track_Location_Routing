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
    }
    out = ROOT / "results/final_evidence/manifests/clean_checkout_verification.json"
    out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    md = ROOT / "results/final_evidence/manifests/clean_checkout_verification.md"
    md.write_text(
        f"""# P8 — Clean-checkout / remanifest verification

## Commands (separate)

```bash
# 1) Generate (writes reports then hashes; excludes manifest from inventory)
python scripts/final_evidence/executable_validation.py

# 2) Verify read-only (must FAIL on any change/missing file)
python scripts/final_evidence/verify_release_manifest.py
```

## This run

- Artifacts listed: **{len(arts)}**
- Failures: **{len(fails)}**
- Passed: **{len(fails) == 0}**

`.gitattributes` enforces `eol=lf` for scientific text artifacts to reduce Windows CRLF vs Git LF size mismatches.

If verifying from a fresh clone: checkout the freeze commit, run only the verify command against the committed manifest (do not regenerate first).
""",
        encoding="utf-8",
    )
    if fails:
        print("MANIFEST_VERIFY_FAIL", fails[:5])
        print("FAILED")
        return 1
    print(f"VERIFIED ok n={len(arts)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
