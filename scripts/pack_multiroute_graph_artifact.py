"""Pack multiroute graph CSVs into a CI-downloadable compressed artifact.

Prefer this over committing ~95MB nodes/edges.csv (HTTP push often fails).
CI downloads the release asset when GRAPH_ARTIFACT_URL is set, else skips.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "data" / "processed" / "multiroute"
OUT_DIR = ROOT / "artifacts"
FILES = ("nodes.csv", "edges.csv", "road_nodes.csv", "road_edges.csv", "build_manifest.json")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=OUT_DIR / "multiroute_graph.zip")
    args = ap.parse_args()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    missing = [f for f in FILES if not (BASE / f).exists()]
    if missing:
        raise SystemExit(f"Missing graph files: {missing}")
    with zipfile.ZipFile(args.out, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for name in FILES:
            zf.write(BASE / name, arcname=name)
    digest = hashlib.sha256(args.out.read_bytes()).hexdigest()
    meta = {
        "artifact": str(args.out.relative_to(ROOT)).replace("\\", "/"),
        "sha256": digest,
        "bytes": args.out.stat().st_size,
        "members": FILES,
    }
    meta_path = args.out.with_suffix(".json")
    meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")
    print(json.dumps(meta, indent=2))


if __name__ == "__main__":
    main()
