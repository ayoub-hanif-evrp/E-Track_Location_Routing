# Task 06B — Placement grid robustness

CSV: `results/task06b_placement_grid_comparison.csv`, `results/task06b_objective_comparison.csv`  
Portfolio unchanged: three CA directional sites, four missions.

## Scope executed

| Grid | Objectives | Placement budgets |
| --- | --- | --- |
| 10 kWh | both | B0, B1, B2, Ball (full 8-subset enum+B&B) |
| 5 kWh | both | full |
| 2 kWh | both | **B1 only** (documented limit; full 8-subset×4-mission at q=2 + replenishment search too heavy) |

## Selected sites (B1+)

| q | Mode | Best sites | Coverage | Secondary |
| --- | --- | --- | --- | --- |
| 10 | enroute | `y_settat_ca` | 5.0 | ~307 |
| 10 | replenish | `y_settat_ca` | 5.0 | ~875 |
| 5 | enroute | `y_settat_ca` | 5.0 | ~266 |
| 5 | replenish | `y_settat_ca` | 5.0 | ~835 |
| 2 | enroute (B1) | `y_settat_ca` | 5.0 | ~254 |
| 2 | replenish (B1) | `y_settat_ca` | **3.0** | ~820 |

**Settat remains the preferred single site** wherever the portfolio solves. Benguerir appears in some **mission** charge plans at q=2 (Casa→Agadir low, enroute) but is not selected under budget B1 (one site).

## Important grid / mode effects

1. **Charge amounts and routes change with q** (same as Task 06A sensitivity): Casa→Marrakech low ~190→170→160 kWh at Settat (enroute, all sites).
2. **B0 coverage** rises from 0 at q=10 to 1.0 at q=5/2 because `M_casa_marrakech_refrig` becomes no-charge feasible on the finer grid (objective 237). Coverage is therefore **not grid-invariant**.
3. **Replenishment secondary ≫ enroute** — terminal shortfall to full pack dominates the monetary secondary term; do not compare absolute secondary across modes without stating the mode.
4. **q=2 + replenishment:** `M_casa_agadir_low` hit `LIMIT_REACHED` on the all-sites serviceability probe; coverage weight for B1 drops to 3.0 (Agadir low excluded from serviceable set). Enum↔B&B still agree on that reduced discrete problem. **Do not claim full-portfolio grid-robust optimality at q=2 replenishment.**

## Continuous replay

Served OPTIMAL missions in the objective comparison CSV report `continuous_replay_ok=True` under the corrected arc-id replay. Infeasible / limit cells are recorded, not masked.

## Claim

Station preference for Settat is **stable on this tiny portfolio** at q=10 and q=5 under both objectives, and at q=2 enroute (B1). It is **not** demonstrated as grid-robust for the full replenishment portfolio at q=2.
