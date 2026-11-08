#!/usr/bin/env python3
"""Download AWS open COP-DEM tiles along baseline routes and sample elevation profiles."""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import requests
from shapely.geometry import shape

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from morocco_etruck.energy.terrain import (  # noqa: E402
    copdem_https_url,
    densify_linestring,
    flat_profile,
    profile_from_elevations,
    save_profile,
)


def _needed_tiles(pts: list[tuple[float, float]]) -> set[tuple[int, int]]:
    tiles: set[tuple[int, int]] = set()
    for lon, lat in pts:
        tiles.add((math.floor(lat), math.floor(lon)))
    return tiles


def download_tile(
    lat_i: int,
    lon_i: int,
    dest_dir: Path,
    *,
    res: str,
    session: requests.Session,
) -> Path | None:
    url = copdem_https_url(lat_i + 0.5, lon_i + 0.5, res=res)
    stem = url.rsplit("/", 2)[-2]
    out = dest_dir / f"{stem}.tif"
    if out.exists() and out.stat().st_size > 1000:
        return out
    print(f"  GET {url}")
    try:
        r = session.get(url, timeout=120, stream=True)
        if r.status_code != 200:
            print(f"  FAIL HTTP {r.status_code} for {url}")
            return None
        dest_dir.mkdir(parents=True, exist_ok=True)
        tmp = out.with_suffix(".partial")
        with tmp.open("wb") as f:
            for chunk in r.iter_content(chunk_size=1 << 20):
                if chunk:
                    f.write(chunk)
        tmp.replace(out)
        return out
    except requests.RequestException as e:
        print(f"  FAIL {e}")
        return None


def sample_route(
    geom,
    tile_paths: list[Path],
    *,
    source: str,
    step_m: float,
) -> tuple:
    pts = densify_linestring(geom, step_m=step_m)
    try:
        from morocco_etruck.energy.terrain import sample_elevations_rasterio

        elevs = sample_elevations_rasterio(pts, tile_paths)
        profile = profile_from_elevations(pts, elevs, source=source, smooth_window=5)
        return profile, pts
    except Exception as e:  # noqa: BLE001 — record blocker honestly
        print(f"  rasterio sampling failed: {e}")
        return flat_profile(geom, step_m=step_m), pts


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--geojson",
        type=Path,
        default=ROOT / "results" / "baseline_routes.geojson",
    )
    p.add_argument(
        "--out-dir",
        type=Path,
        default=ROOT / "data" / "processed" / "energy",
    )
    p.add_argument(
        "--raw-dir",
        type=Path,
        default=ROOT / "data" / "raw" / "dem",
    )
    p.add_argument("--step-m", type=float, default=150.0)
    args = p.parse_args()

    if not args.geojson.exists():
        print(f"Missing {args.geojson}; run Task 01 baseline build first.")
        return 1

    import json as _json

    gj = _json.loads(args.geojson.read_text(encoding="utf-8"))
    session = requests.Session()
    meta: dict = {
        "attribution": "Copernicus DEM DOI 10.5270/ESA-c5d3d65; AWS Open Data copernicus-dem-30m / 90m",
        "note": "DEM is a DSM (terrain/surface), not pavement elevation.",
        "routes": {},
        "blockers": [],
    }

    rasterio_ok = True
    try:
        import rasterio  # noqa: F401
    except ImportError:
        rasterio_ok = False
        meta["blockers"].append("rasterio not installed; DEM sampling unavailable → flat profiles")

    for feat in gj["features"]:
        route = feat["properties"]["route"]
        geom = shape(feat["geometry"])
        pts = densify_linestring(geom, step_m=args.step_m)
        tiles = _needed_tiles(pts)
        print(f"Route {route}: {len(pts)} samples, {len(tiles)} candidate tiles")

        tile_paths: list[Path] = []
        source = "flat"
        if rasterio_ok:
            # Try GLO-30 then GLO-90
            for res, label in (("30", "copdem_glo30"), ("90", "copdem_glo90")):
                tile_paths = []
                ok_all = True
                for lat_i, lon_i in sorted(tiles):
                    path = download_tile(lat_i, lon_i, args.raw_dir / f"glo{res}", res=res, session=session)
                    if path is None:
                        ok_all = False
                        break
                    tile_paths.append(path)
                if ok_all and tile_paths:
                    source = label
                    break
                meta["blockers"].append(f"{route}: incomplete GLO-{res} tile set")
                tile_paths = []

        if source == "flat" or not tile_paths:
            profile = flat_profile(geom, step_m=args.step_m)
            coords = densify_linestring(geom, step_m=args.step_m)
            if "flat-road fallback" not in str(meta["blockers"]):
                meta["blockers"].append(
                    f"{route}: using labeled flat-road baseline (DEM unavailable or incomplete)"
                )
        else:
            profile, coords = sample_route(geom, tile_paths, source=source, step_m=args.step_m)
            if profile.source == "flat":
                meta["blockers"].append(f"{route}: sampling failed → flat")

        out_path = args.out_dir / f"elevation_profile_{route}.json"
        save_profile(out_path, profile, coords=coords)
        meta["routes"][route] = {
            "profile": str(out_path.relative_to(ROOT)).replace("\\", "/"),
            "source": profile.source,
            "n_samples": len(profile.distances_m),
            "z_min": min(profile.elevations_m) if profile.elevations_m else None,
            "z_max": max(profile.elevations_m) if profile.elevations_m else None,
        }
        print(f"  wrote {out_path} source={profile.source}")

    meta_path = args.out_dir / "dem_sampling_meta.json"
    args.out_dir.mkdir(parents=True, exist_ok=True)
    meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")
    print(f"Meta: {meta_path}")
    if meta["blockers"]:
        print("Blockers:")
        for b in meta["blockers"]:
            print(f"  - {b}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
