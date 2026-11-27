#!/usr/bin/env python3
"""Normalize scientific evidence text artifacts to canonical LF (no BOM).

Does not touch binary exports (png/pdf/jpg/...). Safe to re-run.
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FE = ROOT / "results/final_evidence"
TEXT_SUFFIX = {".md", ".csv", ".json", ".yaml", ".yml", ".txt", ".svg", ".py"}


def normalize_file(path: Path) -> bool:
    raw = path.read_bytes()
    if b"\0" in raw[:4096]:
        return False
    text = raw.decode("utf-8-sig")
    fixed = text.replace("\r\n", "\n").replace("\r", "\n")
    out = fixed.encode("utf-8")
    if out != raw:
        path.write_bytes(out)
        return True
    return False


def main() -> int:
    n = 0
    changed = 0
    for p in sorted(FE.rglob("*")):
        if not p.is_file() or p.suffix.lower() not in TEXT_SUFFIX:
            continue
        n += 1
        if normalize_file(p):
            changed += 1
            print("LF", p.relative_to(ROOT))
    print(f"normalized changed={changed} scanned={n}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
