# Task 07C — Route nesting integrity

Reviewed HEAD (pre-fix): `fdc9ec9597dbf8fdf7029f2d94f3021480f1e61c`

## Invalidated Task 07B comparisons

The following rows in `results/task07b_routing_baselines.csv` are **not** a controlled route-superset experiment. Do **not** cite them as evidence that multi-route MRLS is worse than shortest-route MRLS.

| Case | 07B “restricted” | 07B “expanded” | Why invalid |
| --- | --- | --- | --- |
| eActros Casa→Marrakech, no chargers | A: OPTIMAL 23685 | D_none: INFEASIBLE | Different physical graphs |
| eActros Casa→Agadir, Settat+Benguerir | B/C: OPTIMAL 51522 | D_both: OPTIMAL 52362 | Different physical graphs |
| Baselines B vs C | Both shortest + MRLS + same chargers | — | Not independent methods |

`results/task07b_routing_baselines.csv` is **preserved** but nesting claims from it are withdrawn.

## Root cause

Task 07B passed `max_alternatives_for_union=1` for A/B/C and `None` for D. `None` falls back to pilot YAML `max_alternatives_for_union: 2`, which **rebuilds** a different path-union:

1. `max_alts=1` → often a single `O→D` macro; chargers cannot attach (no intermediate decision nodes); no station splits.
2. `max_alts→2` → junctions + `split_arcs_at_charger_nodes`; different discrete DRIVE flooring boundaries.
3. Same corridor length can still yield discrete infeasibility or higher charge cost under q=10.

This is a **representation defect**, not proof that “adding routes removes feasible solutions.”

## Required correction (implemented)

1. Build the **scientific pilot OD path-union once** (`max_alternatives_for_union=2`: shortest + top Jaccard alternative — the Task 05B/pilot claim scope). Do **not** rebuild a separate `max_alts=1` graph for “shortest” baselines.
2. Restrict routes with `allowed_arc_ids` on that same `RoutingInstance` (clone).
3. Toggle chargers only via `active_stations`.
4. Enforce the mask in `RoutingInstance.outgoing` so MRLS and discrete replay share it.

Note: using *all* CSV alternatives (`max_alts=0`) can introduce macros without COP-DEM coverage; those runs are gated `dem_incomplete` rather than silently flattened.

## Acceptance gates

See `tests/unit/test_task07c_route_nesting.py` and `results/task07c_matched_routing_baselines.csv`.

Pass conditions:

1. Restricted and expanded clones share identical node set, arc_id set, station keys, and DRIVE tables.
2. Feasibility nesting and cost monotonicity hold for the cited CM/CA cells.
3. Continuous replay validates selected `arc_id`s.

If any gate fails after the mask fix, stop and report the blocker — do not invent a new algorithm.

## Matched baseline nesting outcomes

C rows with nesting check: 10; failures: 0.
All reported B→C nesting checks passed on the same physical graph.
