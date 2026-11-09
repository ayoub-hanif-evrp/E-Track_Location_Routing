# Task 06A — Speed and physics audit

Date: 2026-11-09  
Base: `83c6f81`

## Defect

Decision-graph scenario speeds stopped in `macro.meta["scenario_speed_kmh"]`.  
`simulate_drive_from_soc()` called `apply_drive()` without `speed_mps`, so physics used `vehicle.cruise_mps` (~80 km/h) on every segment.

## Correction

1. `EdgeInput` carries per-micro-edge `speed_mps`, `highway`, `speed_source`.
2. `build_micro_edges_from_path(..., speed_policy=)` assigns class-default (or OSM) speeds; densified chunks inherit the parent hop speed.
3. `simulate_drive_from_soc` passes `edge.speed_mps` into `apply_drive`.
4. DRIVE-table fingerprint version **`06a.1`** includes `speed_schedule_hash` + `speed_policy_digest`.

## Speed policy (locked scientific default)

Pilot `speed_policy.use_osm_maxspeed: **false**`.

Class defaults (research HGV cruise assumptions, **not** observed speeds):

| Highway | Assumed cruise |
| --- | --- |
| motorway | 80 km/h |
| trunk | 70 km/h |
| primary | 60 km/h |
| default | 50 km/h |

**Why not OSM maxspeed as cruise?** Enabling OSM maxspeed treated many motorway edges as 120 km/h. That overstates HGV cruise/aero load and incorrectly rendered low-battery Casa→Marrakech/Agadir missions infeasible. Archived sensitivity: `results/multiroute_numerical_sensitivity_osm_maxspeed.csv`.

## Initial battery validation

`multiroute_adapter` and A3 `_quantize_capacity` no longer bump `E_init` to `E_min`. Sub-minimum starts raise `INVALID_INPUT`; grid-only drops raise `NUMERICAL_GRID_REJECT`.

## Tests

`tests/unit/test_multiroute_speed_and_grid.py` — dual-speed duration/energy, class-default assignment, fingerprint invalidation, invalid E_init, road-cost allocation.
