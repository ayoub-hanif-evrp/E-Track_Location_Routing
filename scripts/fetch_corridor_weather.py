#!/usr/bin/env python3
"""Fetch Open-Meteo historical weather for A3 corridor points; cache + select hot/cool days."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import requests
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from morocco_etruck.energy.weather import (  # noqa: E402
    load_or_fetch_point,
    select_hot_cool_dates,
)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--config",
        type=Path,
        default=ROOT / "configs" / "energy" / "pilot_scenarios.yaml",
    )
    p.add_argument(
        "--cache-dir",
        type=Path,
        default=ROOT / "data" / "raw" / "weather",
    )
    p.add_argument(
        "--year",
        type=int,
        default=2025,
        help="Calendar year to scan for hot/cool day selection",
    )
    p.add_argument(
        "--scan-point",
        default="marrakech_mid",
        help="Corridor point used to pick hot/cool dates",
    )
    p.add_argument(
        "--fixture-dir",
        type=Path,
        default=ROOT / "tests" / "fixtures" / "weather",
        help="Also write small offline fixtures for CI",
    )
    args = p.parse_args()

    cfg = yaml.safe_load(args.config.read_text(encoding="utf-8"))
    points = cfg["corridor_weather_points"]
    cache_dir: Path = args.cache_dir
    cache_dir.mkdir(parents=True, exist_ok=True)

    session = requests.Session()
    scan = points[args.scan_point]
    print(f"Scanning {args.year} daily means at {args.scan_point} ...")

    # Monthly mid-month probes to limit API calls, then refine around extrema months
    probe_dates = [f"{args.year}-{m:02d}-15" for m in range(1, 13)]
    series: list[tuple[str, float]] = []
    for date in probe_dates:
        wp = load_or_fetch_point(
            args.scan_point,
            float(scan["lat"]),
            float(scan["lon"]),
            date,
            cache_dir,
            session=session,
            allow_fetch=True,
        )
        series.append((date, wp.T_mean_c))
        print(f"  {date}: T_mean={wp.T_mean_c:.2f} C")

    hot, cool = select_hot_cool_dates(series)
    # Allow config defaults to override if probes fail oddly
    selection = {
        "year": args.year,
        "scan_point": args.scan_point,
        "probe_series": [{"date": d, "T_mean_c": t} for d, t in series],
        "hot_date": hot,
        "cool_date": cool,
        "attribution": "Open-Meteo Historical Weather API (https://open-meteo.com/)",
        "note": "Hot/cool days selected from mid-month probes in the scan year; not invented.",
    }
    sel_path = cache_dir / "selection.json"
    sel_path.write_text(json.dumps(selection, indent=2), encoding="utf-8")
    print(f"Selected hot={hot} cool={cool} -> {sel_path}")

    # Fetch all three points for both days
    for day_id, date in (("hot", hot), ("cool", cool)):
        for pid, pcfg in points.items():
            wp = load_or_fetch_point(
                pid,
                float(pcfg["lat"]),
                float(pcfg["lon"]),
                date,
                cache_dir,
                session=session,
                allow_fetch=True,
            )
            print(
                f"  cached {day_id}/{pid} {date}: "
                f"T={wp.T_mean_c:.2f}C wind={wp.wind_speed_mean_mps:.2f}m/s"
            )

    # Write compact fixtures for pytest (the two days × three points)
    args.fixture_dir.mkdir(parents=True, exist_ok=True)
    fixture_sel = {
        "hot_date": hot,
        "cool_date": cool,
        "points": {k: {"lat": v["lat"], "lon": v["lon"]} for k, v in points.items()},
    }
    (args.fixture_dir / "selection.json").write_text(
        json.dumps(fixture_sel, indent=2), encoding="utf-8"
    )
    for date in (hot, cool):
        for pid, pcfg in points.items():
            src = cache_dir / f"{pid}_{date}.json"
            dst = args.fixture_dir / f"{pid}_{date}.json"
            dst.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
    print(f"Fixtures written under {args.fixture_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
