#!/usr/bin/env python
"""Task 05B — Sample per-macro COP-DEM profiles for multiroute decision arcs.

Never reuses A3 corridor elevation_profile_{direction}.json. Writes
data/processed/multiroute/elevation/arc_{arc_id}.json when sampling succeeds;
records blockers honestly when tiles/quality fail.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import pandas as pd
import requests
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from morocco_etruck.energy.terrain import (  # noqa: E402
    TerrainSample,
    assess_terrain_quality,
    densify_linestring,
    flat_profile,
    save_profile,
)
from morocco_etruck.optimization.arc_preprocessing import build_micro_edges_from_path  # noqa: E402
from morocco_etruck.optimization.multiroute_adapter import load_multiroute_pilot_config  # noqa: E402
from morocco_etruck.optimization.multiroute_physics import contract_od_path_union  # noqa: E402
from morocco_etruck.road_network import load_graph_from_csv  # noqa: E402

# Reuse tile helpers from A3 DEM script without importing as module name clash
sys.path.insert(0, str(ROOT / "scripts"))
from fetch_corridor_dem import _needed_tiles, download_tile, sample_route  # noqa: E402


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--config",
        type=Path,
        default=ROOT / "configs/optimization/multiroute_pilot.yaml",
    )
    p.add_argument("--step-m", type=float, default=150.0)
    p.add_argument("--skip-download", action="store_true", help="Only use existing local tiles")
    args = p.parse_args()

    cfg = load_multiroute_pilot_config(args.config, root=ROOT)
    out_dir = cfg.elevation_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    raw_dir = ROOT / "data" / "raw" / "dem"
    raw_dir.mkdir(parents=True, exist_ok=True)

    G = load_graph_from_csv(cfg.nodes_csv, cfg.edges_csv)
    path_rows = pd.read_csv(cfg.path_alternatives_csv).to_dict(orient="records")
    pilot = list(cfg.raw.get("pilot_od_pairs") or ["casa_marrakech", "casa_agadir", "marrakech_agadir"])
    max_alts = int((cfg.raw.get("physics") or {}).get("max_alternatives_for_union") or 2)

    try:
        import rasterio  # noqa: F401

        rasterio_ok = True
    except ImportError:
        rasterio_ok = False

    session = requests.Session()
    meta: dict = {
        "attribution": "Copernicus DEM DOI 10.5270/ESA-c5d3d65; AWS Open Data",
        "note": "Per-macro geometry-owned DEM; not A3 corridor distance profiles.",
        "arcs": {},
        "blockers": [],
    }
    if not rasterio_ok:
        meta["blockers"].append("rasterio not installed")

    seen_arcs: set[str] = set()
    for od_id in pilot:
        od_rows = [r for r in path_rows if str(r.get("od_id")) == od_id]
        if max_alts > 0 and len(od_rows) > max_alts:
            short = [r for r in od_rows if str(r.get("method")) == "shortest_distance"]
            rest = sorted(
                [r for r in od_rows if str(r.get("method")) != "shortest_distance"],
                key=lambda r: -float(r.get("jaccard_distance_vs_shortest") or 0.0),
            )
            od_rows = (short[:1] + rest)[:max_alts]
        arcs, _, _, _ = contract_od_path_union(
            G, od_rows, od_id, speed_policy=cfg.speed_policy
        )
        print(f"{od_id}: {len(arcs)} macros", flush=True)
        for arc in arcs:
            if arc.arc_id in seen_arcs:
                continue
            seen_arcs.add(arc.arc_id)
            geom, _L, _micro, _pairs = build_micro_edges_from_path(G, arc.path_nodes)
            pts = densify_linestring(geom, step_m=args.step_m)
            tiles = _needed_tiles(pts)
            source = "flat"
            tile_paths: list[Path] = []
            if rasterio_ok:
                for res, label in (("30", "copdem_glo30"), ("90", "copdem_glo90")):
                    tile_paths = []
                    ok_all = True
                    for lat_i, lon_i in sorted(tiles):
                        dest = raw_dir / f"glo{res}"
                        if args.skip_download:
                            # Match naming from download_tile without fetching
                            from morocco_etruck.energy.terrain import copdem_https_url

                            url = copdem_https_url(lat_i + 0.5, lon_i + 0.5, res=res)
                            stem = url.rsplit("/", 2)[-2]
                            path = dest / f"{stem}.tif"
                            if not path.exists() or path.stat().st_size < 1000:
                                ok_all = False
                                break
                            tile_paths.append(path)
                        else:
                            path = download_tile(
                                lat_i, lon_i, dest, res=res, session=session
                            )
                            if path is None:
                                ok_all = False
                                break
                            tile_paths.append(path)
                    if ok_all and tile_paths:
                        source = label
                        break
                    tile_paths = []

            out_path = out_dir / f"arc_{arc.arc_id}.json"
            if source == "flat" or not tile_paths:
                profile = flat_profile(geom, step_m=args.step_m)
                coords = pts
                meta["blockers"].append(f"{arc.arc_id}: DEM unavailable → not writing dem profile")
                # Do not write flat as dem; leave missing so physics uses flat fallback
                meta["arcs"][arc.arc_id] = {
                    "od_id": od_id,
                    "u": arc.u,
                    "v": arc.v,
                    "source": "unavailable",
                    "length_m": arc.length_m,
                }
                print(f"  {arc.arc_id}: DEM unavailable", flush=True)
                continue

            profile, coords = sample_route(
                geom, tile_paths, source=source, step_m=args.step_m
            )
            quality = assess_terrain_quality(profile)
            profile = TerrainSample(
                distances_m=profile.distances_m,
                elevations_m=profile.elevations_m,
                source=profile.source,
                meta={
                    **dict(profile.meta or {}),
                    "arc_id": arc.arc_id,
                    "quality": {
                        "status": quality.status,
                        "max_abs_grade": quality.max_abs_grade,
                        "notes": quality.notes,
                    },
                    "step_m": args.step_m,
                },
                valid_mask=profile.valid_mask,
            )
            if quality.status == "invalid":
                meta["blockers"].append(
                    f"{arc.arc_id}: terrain quality INVALID — skipped"
                )
                meta["arcs"][arc.arc_id] = {
                    "od_id": od_id,
                    "source": profile.source,
                    "quality": quality.status,
                    "skipped": True,
                }
                print(f"  {arc.arc_id}: INVALID quality", flush=True)
                continue

            save_profile(out_path, profile, coords=coords)
            z_finite = [z for z in profile.elevations_m if math.isfinite(z)]
            meta["arcs"][arc.arc_id] = {
                "od_id": od_id,
                "u": arc.u,
                "v": arc.v,
                "profile": str(out_path.relative_to(ROOT)).replace("\\", "/"),
                "source": profile.source,
                "quality": quality.status,
                "z_min": min(z_finite) if z_finite else None,
                "z_max": max(z_finite) if z_finite else None,
                "max_abs_grade": quality.max_abs_grade,
                "length_m": arc.length_m,
            }
            print(
                f"  wrote {out_path.name} source={profile.source} "
                f"quality={quality.status} grade={quality.max_abs_grade:.3f}",
                flush=True,
            )

    meta_path = out_dir / "dem_sampling_meta.json"
    meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")
    n_ok = sum(1 for a in meta["arcs"].values() if a.get("profile"))
    print(f"Wrote {meta_path}; dem_profiles={n_ok}/{len(meta['arcs'])}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
