# Task 08 — Final model audit

Reviewed HEAD base: `57270d2` (Task 07C). This checkpoint does **not** rebuild B&B–MRLS.

## Physical / discrete model (frozen)

| Component | Setting | Notes |
| --- | --- | --- |
| Path union | Scientific pilot `max_alternatives_for_union=2` | Shortest + top Jaccard alt |
| Route baselines | `allowed_arc_ids` masks on one graph | Task 07C nesting fix |
| Chargers | `active_stations` only | Hypothetical ADM directional sites |
| Terrain | DEM (COP-DEM GLO-30) | `dem_incomplete` gated |
| Refrigeration | Config A, UA from Task 07B nominal YAML | Not calibrated TRU |
| Grid | q=10 primary | |
| Deadline | 20 h (240 × 5 min) | Illustrative |

## Nesting validation (Gate 1)

- Synthetic adversarial test: both restricted and expanded OPTIMAL with **strict** `obj_exp < obj_res` (`tests/unit/test_task08_nesting_and_realism.py`).
- Shortest-mask connectivity: masked arcs ⊆ OSM shortest path and connect O→D.
- Moroccan feasibility-gain cells (fixed-shortest IF, multi-route OPTIMAL) retained as contribution evidence; vacuous vs positive nesting labeled in robustness report.

## Moroccan combination legality (Gate 3)

Equal cargo **15000 kg** check (manufacturer GCW only):

| Vehicle | Empty combo kg | GCM at 15 t | Tech GCW limit |
| --- | ---: | ---: | ---: |
| eActros 600 | 19700 | 34700 | 44000 |
| Volvo FH Electric 475 | 20000 | 35000 | 65000 |

**Manufacturer GCW ≠ Moroccan legal operating limit.** Axle-load / combination rules under Moroccan legislation are **not** fully encoded here; axle detail marked **unavailable** — do not invent. Results are technical-permissible under YAML GCW only.

## Honesty

Not a field-validated Moroccan deployment. Not operating 350 kW HGV chargers at Settat/Benguerir/Amskroud. Demand weights and CAPEX=100 remain illustrative unless graded otherwise in the economics section.
