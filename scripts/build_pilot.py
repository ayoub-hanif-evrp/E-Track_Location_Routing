#!/usr/bin/env python3
"""Build the Casablanca–Agadir pilot network dataset."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from morocco_etruck.build import run_build

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Build Moroccan A3 pilot dataset")
    parser.add_argument(
        "--config",
        type=Path,
        default=ROOT / "configs" / "pilot_corridor.yaml",
    )
    parser.add_argument(
        "--skip-download",
        action="store_true",
        help="Use cached OSM/ADM files only; never open network connections for downloads",
    )
    args = parser.parse_args()
    try:
        run_build(args.config, skip_download=args.skip_download)
    except FileNotFoundError as exc:
        logging.error("%s", exc)
        return 2
    except Exception:  # noqa: BLE001
        logging.exception("Build failed")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
