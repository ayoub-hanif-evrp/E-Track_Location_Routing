# Task 07B — Discretization diagnostics

Isolate eActros Casa→Marrakech SOC 0.5, refrigeration ON, **no chargers**, q=10 vs q=5 vs q=2 against continuous shortest-path physics.

| Terrain | q | MRLS | continuous_ok | class | obj | terminal_soc_short |
| --- | ---: | --- | --- | --- | ---: | ---: |
| dem | 2 | INFEASIBLE | False | physical_infeasible | nan | 0.09988016730215 |
| dem | 5 | INFEASIBLE | False | physical_infeasible | nan | 0.09988016730215 |
| dem | 10 | INFEASIBLE | False | physical_infeasible | nan | 0.09988016730215 |
| flat | 2 | OPTIMAL | True | discrete_feasible | 23685.0 | 0.1273621761347434 |
| flat | 5 | OPTIMAL | True | discrete_feasible | 23685.0 | 0.1273621761347434 |
| flat | 10 | INFEASIBLE | True | discrete_grid_reject | nan | 0.1273621761347434 |

## Classification key

- `physical_infeasible` — continuous SOC/peak fails on shortest path
- `discrete_grid_reject` — continuous OK, discrete MRLS INFEASIBLE
- `quantization_capacity_loss` — discrete solution exists but replay/capacity loss
- `peak_motor` / `time` / `unresolved` — as labeled

## Headline

Flat q=10: `discrete_grid_reject` (MRLS `INFEASIBLE`); flat q=5: `discrete_feasible` (MRLS `OPTIMAL`). This matches the Task 07A B0 coverage swing (0.0 → 2.0) attribution to Casa→Marrakech grid conservatism.
