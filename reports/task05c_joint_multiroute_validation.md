# Task 05C — Joint multi-route validation (Stage 1 gate + coupling)

Date: 2026-11-09

## Stage 1 acceptance gate

| Gate | Status | Evidence |
| --- | --- | --- |
| Direction-specific facility tests | PASS | `test_multiroute_station_direction.py` |
| Road-attachment (no unsafe snap) | PASS | unresolved when `connected_node_id ∉ union` |
| Fixed-graph monotonicity | PASS | `test_multiroute_station_monotonicity.py` |
| DEM after splitting | PASS | parent-slice note `dem_parent_slice`; unavailable ≠ silent DEM label |
| Continuous-replay feasibility | PASS | deadline, SOC floors, DEM completeness, weather provenance |
| Existing Task 03–05A unit tests | PASS | placement + multiroute suites green |

## Fixed-graph architecture

1. Contract OD path-union once.
2. Resolve **all** direction-compatible attachable candidates.
3. Split macros **once** at those OSM nodes; store `parent_arc_id` + `macro_s0_m`.
4. Build/cache DRIVE tables once with `active_stations=∅`.
5. Infrastructure subsets only clone templates and change `active_stations`.

Monotonicity: A ⊂ B ⇒ DRIVE-only feasible journeys under A remain feasible under B (same arcs/tables). Optional charging cannot raise the discrete objective when prices are nonnegative.

## DEM inheritance

Child macros after charger insertion:

1. Prefer `arc_{child_id}.json` if present.
2. Else window parent `arc_{parent_arc_id}.json` at `macro_s0_m` via `terrain_for_macro_arc`.
3. DEM mode with missing terrain ⇒ `dem_unavailable` / `dem_complete=False` → continuous replay fails (`dem_incomplete`). Never label silent flat as DEM-certified.

Regenerated `casa_marrakech_full_dem_nochg`: OPTIMAL + continuous replay OK on the fixed (pre-split) graph.

## Continuous replay certification

`continuous_replay_multiroute` now checks directed continuity, tractor/trailer floors, SOC ceilings, peak-motor (via simulator), active/compatible charger, charge duration + stationary loads, deadline, DEM completeness, and refuses historical certification under synthetic weather (`weather_assumed`).

OPTIMAL + failed replay ⇒ uncertified / not served.

## Corrected Task 05B pilot deltas (vs `780774a`)

Focus row: **`casa_marrakech_low_flat_chg`**

| Field | Previous (wrong-carriageway risk) | Corrected (05C) |
| --- | --- | --- |
| Station keys | `settat`, `benguerir` | `settat_ca`, `benguerir_ca` |
| OSM ids | risk of `127661105` / `127661098` via snap | **`127661106` / `127661099`** |
| Road distance | ≈ 257.76 km | ≈ **257.76 km** (unchanged length class) |
| Charge | Settat ~200 kWh | **`settat_ca` 200 kWh** |
| Shortest? | false | **false** |
| Continuous replay | true | **true** |

The non-shortest Casa→Marrakech choice **survives** under direction-correct facilities. It is now valid evidence of a direction-specific charging decision on the forward carriageway.

### Other honest deltas

- All missions now use the **fixed split graph** even when chargers are inactive (B&B monotonicity requirement).
- `casa_agadir_full_flat_nochg` becomes **INFEASIBLE** on that fixed graph (extra energy-quantization boundaries). This is documented, not masked. With chargers active, `casa_agadir_low_flat_chg` is OPTIMAL on the shortest path with a Settat charge.
- `marrakech_agadir_low_flat_chg` remains INFEASIBLE (only Amskroud on that OD; insufficient for E_init=200).

## Stage 2 coupling

- Config: `configs/optimization/multiroute_placement_pilot.yaml`
- Engine: `multiroute_placement.py` + `multiroute_placement_evaluation.py`
- Script: `scripts/run_multiroute_placement.py`
- One install decision per physical directional site (`y_settat_ca`, …), shared across ODs.
- Objective unchanged (Task 04B lex coverage then annualized CAPEX + weighted opex).
- B&B core reused; leaves evaluated by physics multi-route MRLS + continuous replay.
- Synthetic unit problem: install enables previously infeasible short route; enum certifies B&B.

See `task05c_comparative_results.md` for enum↔B&B agreement and baseline comparisons.
