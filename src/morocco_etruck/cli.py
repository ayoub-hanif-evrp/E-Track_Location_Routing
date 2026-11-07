"""Console entry point (`build-pilot`)."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(description="Build Moroccan A3 pilot dataset")
    parser.add_argument(
        "--config",
        type=Path,
        default=root / "configs" / "pilot_corridor.yaml",
    )
    parser.add_argument(
        "--skip-download",
        action="store_true",
        help="Use cached OSM/ADM files only; never download",
    )
    args = parser.parse_args(argv)

    from morocco_etruck.build import run_build

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
