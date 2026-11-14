# Northbound route-expansion integrity (eActros A80)

## Question

Why was eActros Agadir→Casablanca OPTIMAL at `max_alts=2` but INFEASIBLE at `max_alts=4` under the same peak-adapt physics?

## Method

1. Select the same OD alternatives used by the adapter (shortest + most diverse).
2. Verify directed OSM edge containment: 2-alt union ⊆ 4-alt union.
3. Build **one canonical** `max_alts=4` physical graph (DEM, peak-adapt, q∈{10,5}).
4. Compare on that graph: full union vs `allowed_arc_ids` mask = 2-alt edge union.
5. Separately rebuild `max_alts=2` (different junction/macro segmentation) for diagnosis only.
6. Quantify cumulative kWh lost to per-macro energy flooring along the feasible path.

## Path containment

- 2-alt edges ⊆ 4-alt edges: **True**
- |E₂|=see CSV, details in diagnostics CSV.

## Solve comparison (peak-adapt, both chargers)

| q | Rebuild max_alts=2 | Mask(2) on canonical4 | Full canonical4 | Nesting class |
| --- | --- | --- | --- | --- |
| 10 | OPTIMAL | INFEASIBLE | INFEASIBLE | `rebuild2_optimal_mask2_IF_segmentation_artifact` |
| 5 | OPTIMAL | OPTIMAL | OPTIMAL | `equal_cost` |

- Rebuild2 macros (q10): n=33, mean length 18247 m
- Canonical4 macros (q10): n=51, mean length 12312 m
- Rounding loss along rebuild2 node walk (q10): **58.5 kWh** over 14 floors
- Same decision-node sequence on canonical4 floors (q10): **85.6 kWh** over 16 floors (~27.1 kWh extra conservatism from finer segmentation)
- At q=5 the same-graph mask vs full costs are equal (46614 vs 46614) and both OPTIMAL.

## Interpretation

The prior 2-vs-4 discrepancy compared **two different physical decision graphs**.
Extra alternatives introduce new branch/merge junctions on shared roads, which **splits macros** and inserts additional conservative energy-floor boundaries.
Measured at q=10: walking the rebuild-2 decision-node sequence accumulates **58.5 kWh** of flooring on the coarse graph vs **85.6 kWh** on the canonical 4-alt segmentation — enough to flip discrete feasibility.

On the **canonical 4-alt graph** at q=10, the 2-alt edge mask is also INFEASIBLE (same tables as full4) — so this is **not** an MRLS bug where adding arcs deletes a feasible masked route. At **q=5**, mask2 and full4 are both OPTIMAL with equal objective → nesting restored on one physical graph.

**Claim discipline:** do not treat rebuild-`max_alts=2` OPTIMAL as nested inside rebuild-`max_alts=4`. Nested comparisons must use `allowed_arc_ids` on one graph. Publication placement for the expanded union uses **q=5 on canonical max_alts=4**.

## eActros feasible route metrics (rebuild max_alts=2, q=10, if OPTIMAL)

- Road distance (drive micros): **353.6 km**
- Driving time: **4.42 h** (excl. charge/wait unless included in replay length)
- Speed mean/min/p05: 79.7 / 50.0 / 80.0 km/h
- Motorway min speed: 50.0 km/h; segments below 60 km/h: 33 (Decree 2-10-420 Art.18 normal min — flagged, not asserted illegal)
- Max / p95 wheel power: 600.0 / 309.52133585416635 kW (ratings peak 600.0 / cont 400.0)
- Charge energy / duration (replay): 240.0 kWh / 45.0 min
- Min SOC (replay) / arrival SOC (profile): 0.23530976814106477 / 0.10000813173406403
- Discrete replay OK: True; continuous replay OK: True
- Acceleration/deceleration between micro speeds: **not modeled** (limitation).

## Placement (final reported graph)

- canonical4_full_q5 / B0: coverage=0, bb_sites=, enum_sites=, agree=True, opt_sets=['NONE'], optimality=CERTIFIED_OPTIMAL
- canonical4_full_q5 / B1: coverage=1.0, bb_sites=y_benguerir_ac, enum_sites=y_benguerir_ac, agree=True, opt_sets=['y_benguerir_ac'], optimality=CERTIFIED_OPTIMAL
- canonical4_full_q5 / B2: coverage=1.0, bb_sites=y_benguerir_ac, enum_sites=y_benguerir_ac, agree=True, opt_sets=['y_benguerir_ac'], optimality=CERTIFIED_OPTIMAL
- canonical4_full_q5 / Ball: coverage=1.0, bb_sites=y_benguerir_ac, enum_sites=y_benguerir_ac, agree=True, opt_sets=['y_benguerir_ac'], optimality=CERTIFIED_OPTIMAL

## Acceptance

`A_at_q5_canonical_graph_nesting_ok;B_at_q10_rebuild_vs_canonical_segmentation_rounding_artifact;no_full_network_optimality_claim`

No full-network optimality claim. No claim that expanding OSM alternatives makes the truck physically unable to drive the original roads.

## Reproduction

```bash
python scripts/run_northbound_route_expansion_integrity.py
```

Artifacts: `results/northbound_route_expansion_diagnostics.csv`, `results/northbound_route_expansion_summary.json`.
