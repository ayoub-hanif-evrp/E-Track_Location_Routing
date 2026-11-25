# Coverage reconciliation (Path A Gate 0)

## Authoritative manuscript ladder (eActros ops)

| Budget | C fixed | E multi | Sites C | Sites E |
|--------|---------|---------|---------|---------|
| B0 | 9/14 | 9/14 | — | — |
| B1 | 10/14 (Larache) | 11/14 (Benguerir CA) | y_larache_rt | y_benguerir_ca |
| B2 | 11/14 (Benguerir+Larache) | 11/14 (Benguerir CA) | both | y_benguerir_ca |

## Why 12/14 must not be the B2 headline

- Ablation **multi_on_C** = **12/14** because `casa_marrakech` is INFEASIBLE under fixed but OPTIMAL under multi on C sites (FLEX_GAIN).
- Headline **C** optimizes the **fixed-route** mask → still **11/14**.
- Headline **E** installs only Benguerir → `casa_tangier` fails (needs Larache direction) → **11/14**.
- Ball `D_energy=12/14` is an energy-only figure under a larger charger set — not B2 operational coverage.

## OD footnotes

- FLEX_GAIN on C sites: casa_marrakech
- served with Larache on C but not Benguerir-only E: casa_tangier

Source table: `results/validation/path_a/coverage_reconciliation.csv`
