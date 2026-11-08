"""DEM sampling, grade estimation, and terrain quality audits along route geometries."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Sequence

from shapely.geometry import LineString

from morocco_etruck.road_network import geodesic_length_m

# Motorway DEM quality: consecutive sample grades above this flag as non-physical for A3-class roads.
# Typical motorway design grades are well below 10%; 12% over ~100–200 m samples allows DEM noise
# without accepting the ~150% spike that corrupted Task 02 profiles.
# DSM (not pavement) sampled every ~150 m: allow up to 15% consecutive grade before
# declaring non-physical. Motorway design grades are lower; this threshold targets
# sampling artifacts (e.g. Task 02 ~150% spikes), not gentle hills.
DEFAULT_MAX_ABS_GRADE = 0.15
DEFAULT_MAX_MISSING_FRAC = 0.02
DEFAULT_MIN_GRADE_SEGMENT_M = 50.0


@dataclass(frozen=True)
class TerrainSample:
    """Sampled elevation profile along a route (distances use WGS84 geodesic metres)."""

    distances_m: list[float]
    elevations_m: list[float]  # may contain NaN for missing samples
    source: str  # "flat" | "copdem_glo30" | "copdem_glo90" | "synthetic" | ...
    meta: dict[str, Any] = field(default_factory=dict)
    valid_mask: list[bool] | None = None  # True where elevation is an accepted sample


@dataclass(frozen=True)
class TerrainQuality:
    status: str  # "valid" | "invalid" | "flat" | "missing_data"
    max_abs_grade: float
    n_samples: int
    n_missing: int
    missing_frac: float
    n_grade_violations: int
    first_grade_violation_km: float | None
    notes: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class EdgeTerrain:
    length_m: float
    dz_m: float
    theta_rad: float


def densify_linestring(geom: LineString, step_m: float = 150.0) -> list[tuple[float, float]]:
    """Return (lon, lat) samples approximately every step_m along the line (geodesic spacing)."""
    if geom.is_empty:
        return []
    coords = list(geom.coords)
    total_m = geodesic_length_m([(c[0], c[1]) for c in coords])
    if total_m <= 0:
        return [(float(coords[0][0]), float(coords[0][1]))]
    n = max(2, int(math.ceil(total_m / step_m)) + 1)
    samples: list[tuple[float, float]] = []
    for i in range(n):
        d_m = min(total_m, i * step_m) if i < n - 1 else total_m
        frac = d_m / total_m
        pt = geom.interpolate(frac, normalized=True)
        xy = (float(pt.x), float(pt.y))
        # Avoid near-duplicate terminal samples that create infinite local grades
        if samples and geodesic_length_m([samples[-1], xy]) < 1.0:
            samples[-1] = xy
        else:
            samples.append(xy)
    # Ensure true endpoint is present
    end = (float(coords[-1][0]), float(coords[-1][1]))
    if geodesic_length_m([samples[-1], end]) >= 1.0:
        samples.append(end)
    else:
        samples[-1] = end
    return samples


def cumulative_geodesic_m(pts: Sequence[tuple[float, float]]) -> list[float]:
    dists = [0.0]
    for i in range(1, len(pts)):
        dists.append(dists[-1] + geodesic_length_m([pts[i - 1], pts[i]]))
    return dists


def moving_average(values: Sequence[float], window: int = 5) -> list[float]:
    """Moving average that preserves NaNs (does not invent elevations across gaps)."""
    if window < 1:
        raise ValueError("window must be >= 1")
    if not values:
        return []
    w = min(window, len(values))
    half = w // 2
    out: list[float] = []
    for i in range(len(values)):
        if not math.isfinite(values[i]):
            out.append(float("nan"))
            continue
        lo = max(0, i - half)
        hi = min(len(values), i + half + 1)
        chunk = [values[j] for j in range(lo, hi) if math.isfinite(values[j])]
        out.append(sum(chunk) / len(chunk) if chunk else float("nan"))
    return out


def flat_profile(geom: LineString, step_m: float = 150.0) -> TerrainSample:
    pts = densify_linestring(geom, step_m=step_m)
    dists = cumulative_geodesic_m(pts)
    elev = [0.0] * len(pts)
    return TerrainSample(
        distances_m=dists,
        elevations_m=elev,
        source="flat",
        meta={"step_m": step_m, "n_samples": len(pts), "quality_status": "flat"},
        valid_mask=[True] * len(pts),
    )


def profile_from_elevations(
    pts: Sequence[tuple[float, float]],
    elevations_m: Sequence[float],
    *,
    source: str,
    smooth_window: int = 5,
    meta: dict[str, Any] | None = None,
    valid_mask: Sequence[bool] | None = None,
) -> TerrainSample:
    if len(pts) != len(elevations_m):
        raise ValueError("pts and elevations_m length mismatch")
    dists = cumulative_geodesic_m(pts)
    elev = moving_average(list(elevations_m), window=smooth_window)
    mask = list(valid_mask) if valid_mask is not None else [math.isfinite(z) for z in elev]
    return TerrainSample(
        distances_m=dists,
        elevations_m=elev,
        source=source,
        meta={**(meta or {}), "smooth_window": smooth_window, "n_samples": len(pts)},
        valid_mask=mask,
    )


def assess_terrain_quality(
    profile: TerrainSample,
    *,
    max_abs_grade: float = DEFAULT_MAX_ABS_GRADE,
    max_missing_frac: float = DEFAULT_MAX_MISSING_FRAC,
    min_segment_m: float = DEFAULT_MIN_GRADE_SEGMENT_M,
) -> TerrainQuality:
    """Flag unrealistic grades and missing-data intervals. Flat profiles are labeled flat (valid for flat scenarios)."""
    notes: list[str] = []
    z = profile.elevations_m
    d = profile.distances_m
    n = len(z)
    if profile.source == "flat":
        return TerrainQuality(
            status="flat",
            max_abs_grade=0.0,
            n_samples=n,
            n_missing=0,
            missing_frac=0.0,
            n_grade_violations=0,
            first_grade_violation_km=None,
            notes=["Labeled flat-road baseline (no DEM)."],
        )

    missing = sum(1 for v in z if not math.isfinite(v))
    missing_frac = missing / n if n else 1.0
    if missing_frac > max_missing_frac:
        notes.append(f"Missing elevation fraction {missing_frac:.3f} exceeds {max_missing_frac}.")

    max_g = 0.0
    n_viol = 0
    first_km: float | None = None
    for i in range(1, n):
        if not math.isfinite(z[i]) or not math.isfinite(z[i - 1]):
            continue
        ds = d[i] - d[i - 1]
        # Skip tiny densification stubs (numerical grade blow-ups)
        if ds < min_segment_m:
            continue
        g = abs(z[i] - z[i - 1]) / ds
        max_g = max(max_g, g)
        if g > max_abs_grade:
            n_viol += 1
            if first_km is None:
                first_km = d[i] / 1000.0
    if n_viol:
        notes.append(
            f"{n_viol} consecutive sample grade(s) exceed {max_abs_grade:.0%} "
            f"over ≥{min_segment_m:.0f} m (max={max_g:.1%}); first at ~{first_km:.3f} km."
        )

    if missing_frac > max_missing_frac or n_viol > 0:
        status = "invalid"
    elif missing > 0:
        status = "missing_data"
        notes.append("Some missing samples remain below the invalidation threshold.")
    else:
        status = "valid"
        notes.append("No grade or missing-data threshold violations.")

    return TerrainQuality(
        status=status,
        max_abs_grade=max_g,
        n_samples=n,
        n_missing=missing,
        missing_frac=missing_frac,
        n_grade_violations=n_viol,
        first_grade_violation_km=first_km,
        notes=notes,
    )


def elevation_at_distance(profile: TerrainSample, s_m: float) -> float:
    d = profile.distances_m
    z = profile.elevations_m
    if not d:
        return float("nan")
    if s_m <= d[0]:
        return z[0]
    if s_m >= d[-1]:
        return z[-1]
    for i in range(1, len(d)):
        if s_m <= d[i]:
            if not math.isfinite(z[i - 1]) or not math.isfinite(z[i]):
                return float("nan")
            t = (s_m - d[i - 1]) / max(1e-9, d[i] - d[i - 1])
            return z[i - 1] + t * (z[i] - z[i - 1])
    return z[-1]


def edge_dz_from_profile(profile: TerrainSample, s0_m: float, length_m: float) -> float:
    z0 = elevation_at_distance(profile, s0_m)
    z1 = elevation_at_distance(profile, s0_m + length_m)
    if not math.isfinite(z0) or not math.isfinite(z1):
        return float("nan")
    return z1 - z0


def split_route_into_edges(
    geom: LineString,
    *,
    max_edge_m: float = 2000.0,
) -> list[tuple[LineString, float]]:
    """
    Split a route LineString into sub-edges of approximately max_edge_m.

    Lengths are WGS84 geodesic metres (same convention as Task 01 road network).
    """
    coords = list(geom.coords)
    if len(coords) < 2:
        raise ValueError("geometry needs at least 2 coordinates")
    edges: list[tuple[LineString, float]] = []
    chunk = [coords[0]]
    acc = 0.0
    for i in range(1, len(coords)):
        seg_len = geodesic_length_m([(coords[i - 1][0], coords[i - 1][1]), (coords[i][0], coords[i][1])])
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
        "elevations_m": [None if not math.isfinite(z) else z for z in profile.elevations_m],
        "source": profile.source,
        "meta": profile.meta,
        "valid_mask": profile.valid_mask,
        "coords_lonlat": coords,
    }
    path.write_text(json.dumps(payload), encoding="utf-8")


def load_profile(path: Path) -> TerrainSample:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    elevs = [float("nan") if v is None else float(v) for v in raw["elevations_m"]]
    mask = raw.get("valid_mask")
    return TerrainSample(
        distances_m=[float(x) for x in raw["distances_m"]],
        elevations_m=elevs,
        source=str(raw["source"]),
        meta=dict(raw.get("meta") or {}),
        valid_mask=[bool(x) for x in mask] if mask is not None else None,
    )


def profile_distance_agrees(
    profile: TerrainSample,
    route_distance_m: float,
    *,
    rel_tol: float = 0.002,
    abs_tol_m: float = 500.0,
) -> bool:
    """True if profile end distance matches route geodesic distance within tolerance."""
    if not profile.distances_m:
        return False
    end = profile.distances_m[-1]
    return abs(end - route_distance_m) <= max(abs_tol_m, rel_tol * route_distance_m)


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


def _point_in_bounds(lon: float, lat: float, bounds, *, eps: float = 1e-8) -> bool:
    return (
        bounds.left - eps <= lon <= bounds.right + eps
        and bounds.bottom - eps <= lat <= bounds.top + eps
    )


def sample_elevations_rasterio(
    pts: Sequence[tuple[float, float]],
    tile_paths: Sequence[Path],
) -> tuple[list[float], list[bool]]:
    """
    Sample elevations at lon/lat points from local GeoTIFF tiles (requires rasterio).

    Out-of-bounds or masked/nodata samples are left as NaN (never coerced to 0).
    Returns (elevations, valid_mask).
    """
    import rasterio

    elevs = [float("nan")] * len(pts)
    valid = [False] * len(pts)
    remaining = set(range(len(pts)))

    for tpath in tile_paths:
        if not remaining:
            break
        with rasterio.open(tpath) as ds:
            idxs = [i for i in sorted(remaining) if _point_in_bounds(pts[i][0], pts[i][1], ds.bounds)]
            if not idxs:
                continue
            coords = [(pts[i][0], pts[i][1]) for i in idxs]
            # Prefer masked sampling so nodata / outside coverage is not accepted as 0.
            try:
                samples = list(ds.sample(coords, masked=True))
            except TypeError:
                samples = list(ds.sample(coords))

            for i, val in zip(idxs, samples):
                if val is None:
                    continue
                arr = val[0]
                # numpy masked scalar
                if hasattr(arr, "mask") and bool(getattr(arr, "mask", False)):
                    continue
                try:
                    v = float(arr)
                except (TypeError, ValueError):
                    continue
                if not math.isfinite(v):
                    continue
                if ds.nodata is not None and v == ds.nodata:
                    continue
                # Extra guard: some COP-DEM COGs report nodata=None but return 0 outside coverage.
                # Reject exact 0 only when the point is NOT in bounds (already filtered) —
                # in-bounds zeros can be legitimate near sea level; keep them.
                elevs[i] = v
                valid[i] = True
                remaining.discard(i)

    return elevs, valid
