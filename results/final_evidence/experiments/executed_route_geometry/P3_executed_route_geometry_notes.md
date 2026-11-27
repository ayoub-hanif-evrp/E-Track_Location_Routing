# P3 — Executed-route geometry verification (final)

Scope: all **operationally served** eActros `stressed_mixed` missions in the
I0–I3 primary panel (**45** itineraries plotted on R-Figure 2).

## Coverage

- Missions audited: **45/45** (`executed_route_summary.csv`).
- Arc rows: **464** with ordered `u`/`v`, parent_arc_id, macro_s0_m.
- Geometry complete (`n_geom_points ≥ 2`): **464/464** arcs.
- DEM elevation coverage (per-arc + parent-slice, no flat fallback): **100%** of route length.

## DEM source (solver = visualization)

Policy: `macros_by_arc_id` → child `arc_{id}.json` → parent window at `macro_s0_m` → `dem_unavailable`.
- `dem_per_arc` arcs: **369**
- `dem_parent_slice` arcs: **95** (child JSON absent; physics uses parent slice — not flat)
- `dem_unavailable` / solver flat fallback arcs: **0** viz / **0** solver

Representative steep arc `343a5225681579e5`: **copdem_glo30** per-arc file;
`terrain_note_solver=dem_per_arc`, `dem_ok=True`.

## Length checks

- `route_length_m` equals sum of trace `length_m` per mission (max |Δ| 0.000 m).
- Geographic polyline length (densified lon/lat) vs macro `length_m`:
  max |Δ| = **965.6 m** across arcs; **0** arcs with |Δ|>1 km
  (expected when DEM coords are denser than graph macro length).
  See `executed_route_length_check.csv` and per-arc `polyline_vs_macro_*` columns.

## Steep gradient `343a5225681579e5` (raw vs processed)

- **Raw** max |grade| ≈ **0.230** over **2.61 m** (Δz=0.60 m); see P1 note.
- **Filtered** (≥5 m segments, QC-style): max |grade| ≈ **0.032**.
- **No auto-clip** in solver traces; artifact is sub-resolution sampling at junction end.
- Gravity-only extra work on spike (40 t): **≈0.065 kWh** (≪ single-arc traction **~6.65 kWh** on Casa departures in primary traces).
- Peak-motor flags on this arc in served traces: **none** observed.

## Directional charging

R-Figure 2/5 resolve CHARGE sites via directional keys (`y_benguerir_ca`, `y_benguerir_ac`,
`y_larache_rt`) against `D-T04_candidate_inventory.csv` — not collapsed to generic city labels.

## Files

- `executed_arc_geometry_audit.csv` — per-arc geometry + terrain source
- `executed_route_summary.csv` — per-mission coverage
- `executed_route_length_check.csv` — trace vs polyline reconciliation
- `P1_steep_gradient_343a5225681579e5.md` — steep-grade context
