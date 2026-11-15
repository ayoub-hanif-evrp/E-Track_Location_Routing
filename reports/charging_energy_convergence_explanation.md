# Charging-energy convergence explanation

Committed Ball site identity for served grids remains Benguerir, but discrete charging energy is **not** stable across q.

| q | Discrete charge kWh | Continuous charge kWh | Floor loss kWh | Objective | Same DRIVE arc sequence as q=5? |
| --- | ---: | ---: | ---: | ---: | --- |
| 5 | 175.0 | 175.0 | 94.45378870300519 | 46614 | True |
| 2 | 110.0 | 110.0 | 30.111524470292444 | 45234 | True |
| 1 | 94.0 | 94.0 | 14.111524470292935 | 44894 | True |

## Interpretation

**Primary classification: B + C on the same physical DRIVE arc sequence (A rejected).**

- Exact DRIVE `arc_id` sequences for q=5, 2 and 1 are **identical**.
- Discrete charge drops by **81.0 kWh** from q=5→1 (175→94).
- Action-exact cumulative floor loss drops by **80.3 kWh** (94.45→14.11).
- Therefore the charge-energy change is **largely explained by conservative flooring** that forces larger discrete top-ups on coarser grids, together with **different quantum-feasible charge amounts (C)** at Benguerir—not by selecting a different road.

Site identity can be stable while charging energy and secondary cost are still q-dependent. Do not market “results converged” for energy/cost when only the site set is stable.

CSV: `results/final_action_rounding_audit.csv`
