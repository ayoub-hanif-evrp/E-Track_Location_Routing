# Task 02B — DEM diagnostics

## Confirmed Task 02 anomaly

Committed profile `elevation_profile_casablanca_to_agadir.json` (Task 02) contained a non-physical climb near **km 341**:

| Distance (km) | Elevation (m) |
|---|---|
| 341.1 | 0 |
| 341.3 | 249 |
| 341.4 | 499 |
| 341.6 | 748 |
| 341.7 | 997 |
| 341.9 | 1246 |

Local grades ≈ **158%**. A motorway cannot climb ~249 m in ~158 m of road.

**Global symptom:** 2277 of 2785 samples were exact **0 m**, then real elevations appeared abruptly. The reverse Agadir→Casablanca profile showed the symmetric artifact.

Before snapshot retained at:
`data/processed/energy/elevation_profile_casablanca_to_agadir_task02_before.json`

Figure: `reports/figures/dem_before_after_casa_agadir.png`

---

## Root cause

AWS COP-DEM GLO-30 COGs report **`nodata=None`**. When Rasterio samples a coordinate **outside a tile’s bounds**, the returned value is **0.0**, not a masked/null sample.

Task 02 `sample_elevations_rasterio` accepted every finite value, including those out-of-bounds zeros, and removed the point from the “remaining” set. The first tile in the loop therefore painted most of the corridor as sea-level zeros until a later tile that actually covered the southern mountains wrote real elevations — producing the cliff.

This is **not** legitimate near-coast 0 m elevation. Zero metres can be valid **inside** bounds; out-of-bounds zeros must never be accepted.

Contributing factors:

- No `masked=True` sampling / bounds gate before accepting values.
- Nearest-neighbor fill for remaining gaps could further invent terrain (removed in 02B).
- Tiny densification stubs at the route end (~0.4 m) could inflate local grades; quality checks now require ≥50 m segments.

All six required corridor tiles were present; the bug was sampling logic, not missing tiles.

---

## Correction

1. Accept a sample only if the lon/lat lies inside the dataset bounds.
2. Prefer `ds.sample(..., masked=True)`; reject masked/nodata values.
3. Leave unsampled points as **NaN** (do not invent elevations).
4. Automatic quality gate: missing-fraction and consecutive grade >15% over ≥50 m → `terrain_quality_status=invalid`.
5. Distances use WGS84 **geodesic** metres (Task 01 convention).

---

## After (Task 02B)

| Route | Valid samples | Quality | Max \|grade\| (over ≥50 m) | Profile end vs geodesic |
|---|---|---|---|---|
| Casablanca→Agadir | 2781/2781 | **valid** | 13.95% | 417.000 km vs 417.000 km |
| Agadir→Casablanca | 2782/2782 | **valid** | 11.46% | matches 417.113 km |

Meta: `data/processed/energy/dem_sampling_meta.json`.

---

## Remaining uncertainty

- COP-DEM is a **DSM** (surface), not pavement; vegetation/structures remain.
- Max consecutive grades ~12–14% may include DEM noise over ~150 m samples; they pass the 15% artifact gate but are not certified road grades.
- No claim of centimetre vertical accuracy.

If quality had remained invalid after bounds-aware sampling, DEM scenarios would be marked **indeterminate** and only flat-road scenarios would support boolean mission feasibility. That fallback was not required after the fix.
