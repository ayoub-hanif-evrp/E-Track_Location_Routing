# Task 05B — Physics integration

## What changed vs Task 05A

Task 05A Moroccan experiments used artificial `O → R_i → D` halves with flat `1 kWh/km`.

Task 05B scientific path:

1. OD-local path-union contraction (`contract_od_path_union`)
2. Per-macro `build_macro_arc` on multiroute OSM geometry
3. State-dependent DRIVE tables (`build_drive_table`) with Task 02B physics
4. Continuous replay keyed by `arc_id` (`continuous_replay_multiroute`)
5. Grounded ADM chargers only (`multiroute_charging`; **R_i midpoints rejected**)

## Terrain

Default pilot mode: **flat** (documented). Per-arc DEM profiles may be placed under `data/processed/multiroute/elevation/arc_{arc_id}.json`. A3 corridor elevation profiles are **never** reused for trunk/primary macros. Missing DEM → flat fallback noted in context (not fabricated elevations).

## Discretization

- Macros contracted **before** quantization
- Pilot grid: `energy_quantum_kwh=10`, `time_step_min=5` (sensitivity mission uses 5 kWh)
- DRIVE conservatism: floor ending energy, ceil travel time
- Discrete optimum ≠ continuous physical optimum ≠ empirical validation

## Charging

Candidates from `candidate_sites.csv` with `entrance_and_exit` only (Settat, Benguerir, Amskroud when on the OD union). `hypothetical_access=True`. No invented midpoints.

## Cache

`data/processed/multiroute/drive_tables/` fingerprinted via existing `drive_table_cache` helpers.

## Modules

- `src/morocco_etruck/optimization/multiroute_physics.py`
- `src/morocco_etruck/optimization/multiroute_charging.py`
- `src/morocco_etruck/optimization/multiroute_replay.py`
- Updated `multiroute_adapter.py`, `route_choice_graph.py`, `problem.ArcData.arc_id`
