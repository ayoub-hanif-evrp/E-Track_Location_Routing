"""DEM sampling and grade estimation along route geometries."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

from shapely.geometry import LineString


@dataclass(frozen=True)
class TerrainSample:
    """Sampled elevation profile along a route."""

    distances_m: list[float]
    elevations_m: list[float]
    source: str  # "flat" | "copdem_glo30" | "copdem_glo90" | "synthetic"
    meta: dict[str, Any]


@dataclass(frozen=True)
class EdgeTerrain:
    length_m: float
    dz_m: float
    theta_rad: float


def haversine_m(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    r = 6_371_000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(min(1.0, math.sqrt(a)))


def densify_linestring(geom: LineString, step_m: float = 150.0) -> list[tuple[float, float]]:
    """Return (lon, lat) samples approximately every step_m along the line."""
    if geom.is_empty:
        return []
    # Estimate total metres from consecutive vertices
    coords = list(geom.coords)
    total_m = 0.0
    for i in range(1, len(coords)):
        total_m += haversine_m(coords[i - 1][0], coords[i - 1][1], coords[i][0], coords[i][1])
    if total_m <= 0:
        return [(coords[0][0], coords[0][1])]
    n = max(2, int(math.ceil(total_m / step_m)) + 1)
    samples: list[tuple[float, float]] = []
    for i in range(n):
        d_m = min(total_m, i * step_m) if i < n - 1 else total_m
        frac = d_m / total_m
        # shapely substring uses normalized distance on geometric length
        pt = geom.interpolate(frac, normalized=True)
        samples.append((float(pt.x), float(pt.y)))
    return samples


def moving_average(values: Sequence[float], window: int = 5) -> list[float]:
    if window < 1:
        raise ValueError("window must be >= 1")
    if not values:
        return []
    w = min(window, len(values))
    half = w // 2
    out: list[float] = []
    for i in range(len(values)):
        lo = max(0, i - half)
        hi = min(len(values), i + half + 1)
        chunk = values[lo:hi]
        out.append(sum(chunk) / len(chunk))
    return out


def flat_profile(geom: LineString, step_m: float = 150.0) -> TerrainSample:
    pts = densify_linestring(geom, step_m=step_m)
    dists = [0.0]
    for i in range(1, len(pts)):
        dists.append(dists[-1] + haversine_m(pts[i - 1][0], pts[i - 1][1], pts[i][0], pts[i][1]))
    elev = [0.0] * len(pts)
    return TerrainSample(
        distances_m=dists,
        elevations_m=elev,
        source="flat",
        meta={"step_m": step_m, "n_samples": len(pts)},
    )


def profile_from_elevations(
    pts: Sequence[tuple[float, float]],
    elevations_m: Sequence[float],
    *,
    source: str,
    smooth_window: int = 5,
    meta: dict[str, Any] | None = None,
) -> TerrainSample:
    if len(pts) != len(elevations_m):
        raise ValueError("pts and elevations_m length mismatch")
    dists = [0.0]
    for i in range(1, len(pts)):
        dists.append(dists[-1] + haversine_m(pts[i - 1][0], pts[i - 1][1], pts[i][0], pts[i][1]))
    elev = moving_average(list(elevations_m), window=smooth_window)
    return TerrainSample(
        distances_m=dists,
        elevations_m=elev,
        source=source,
        meta={**(meta or {}), "smooth_window": smooth_window, "n_samples": len(pts)},
    )


def elevation_at_distance(profile: TerrainSample, s_m: float) -> float:
    d = profile.distances_m
    z = profile.elevations_m
    if not d:
        return 0.0
    if s_m <= d[0]:
        return z[0]
    if s_m >= d[-1]:
        return z[-1]
    # linear interpolate
    for i in range(1, len(d)):
        if s_m <= d[i]:
            t = (s_m - d[i - 1]) / max(1e-9, d[i] - d[i - 1])
            return z[i - 1] + t * (z[i] - z[i - 1])
    return z[-1]


def edge_dz_from_profile(
    profile: TerrainSample,
    s0_m: float,
    length_m: float,
) -> float:
    z0 = elevation_at_distance(profile, s0_m)
    z1 = elevation_at_distance(profile, s0_m + length_m)
    return z1 - z0


def split_route_into_edges(
    geom: LineString,
    *,
    max_edge_m: float = 2000.0,
) -> list[tuple[LineString, float]]:
    """
    Split a route LineString into sub-edges of approximately max_edge_m.

    Returns list of (sub_linestring, length_m).
    """
    coords = list(geom.coords)
    if len(coords) < 2:
        raise ValueError("geometry needs at least 2 coordinates")
    # Walk vertices accumulating length; emit chunks
    edges: list[tuple[LineString, float]] = []
    chunk = [coords[0]]
    acc = 0.0
    for i in range(1, len(coords)):
        seg_len = haversine_m(coords[i - 1][0], coords[i - 1][1], coords[i][0], coords[i][1])
        if acc + seg_len > max_edge_m and len(chunk) >= 2:
            ls = LineString(chunk)
            edges.append((ls, acc))
            chunk = [chunk[-1], coords[i]]
            acc = seg_len
        else:
            chunk.append(coords[i])
            acc += seg_len
    if len(chunk) >= 2 and acc > 0:
        edges.append((LineString(chunk), acc))
    return edges


def save_profile(path: Path, profile: TerrainSample, coords: list[tuple[float, float]] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "distances_m": profile.distances_m,
        "elevations_m": profile.elevations_m,
        "source": profile.source,
        "meta": profile.meta,
        "coords_lonlat": coords,
    }
    path.write_text(json.dumps(payload), encoding="utf-8")


def load_profile(path: Path) -> TerrainSample:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    return TerrainSample(
        distances_m=[float(x) for x in raw["distances_m"]],
        elevations_m=[float(x) for x in raw["elevations_m"]],
        source=str(raw["source"]),
        meta=dict(raw.get("meta") or {}),
    )


# --- AWS COP-DEM helpers (optional rasterio) ---

def copdem_tile_name(lat: float, lon: float, *, res: str = "30") -> str:
    """
    Copernicus DSM COG tile folder/file stem for AWS open data.

    res: "30" -> COG_10 (GLO-30), "90" -> COG_30 (GLO-90) naming on AWS buckets.
    """
    lat_i = math.floor(lat)
    lon_i = math.floor(lon)
    ns = "N" if lat_i >= 0 else "S"
    ew = "E" if lon_i >= 0 else "W"
    lat_abs = abs(lat_i)
    lon_abs = abs(lon_i)
    cog = "10" if res == "30" else "30"
    return f"Copernicus_DSM_COG_{cog}_{ns}{lat_abs:02d}_00_{ew}{lon_abs:03d}_00_DEM"


def copdem_https_url(lat: float, lon: float, *, res: str = "30") -> str:
    stem = copdem_tile_name(lat, lon, res=res)
    bucket = "copernicus-dem-30m" if res == "30" else "copernicus-dem-90m"
    return f"https://{bucket}.s3.amazonaws.com/{stem}/{stem}.tif"


def sample_elevations_rasterio(
    pts: Sequence[tuple[float, float]],
    tile_paths: Sequence[Path],
) -> list[float]:
    """Sample elevations at lon/lat points from local GeoTIFF tiles (requires rasterio)."""
    import rasterio
    from rasterio.sample import sample_gen

    elevs = [float("nan")] * len(pts)
    remaining = set(range(len(pts)))
    for tpath in tile_paths:
        if not remaining:
            break
        with rasterio.open(tpath) as ds:
            idxs = sorted(remaining)
            coords = [(pts[i][0], pts[i][1]) for i in idxs]
            for i, val in zip(idxs, sample_gen(ds, coords)):
                v = float(val[0]) if val is not None else float("nan")
                # nodata check
                if ds.nodata is not None and v == ds.nodata:
                    continue
                if math.isnan(v):
                    continue
                elevs[i] = v
                remaining.discard(i)
    if remaining:
        # fill gaps with nearest successful neighbor
        for i in sorted(remaining):
            elevs[i] = _nearest_finite(elevs, i)
    return elevs


def _nearest_finite(elevs: list[float], i: int) -> float:
    for d in range(1, len(elevs)):
        for j in (i - d, i + d):
            if 0 <= j < len(elevs) and math.isfinite(elevs[j]):
                return elevs[j]
    return 0.0
