# Coverage reconciliation (Path A corrected)

## Do not confuse these tables

1. **historical_enum_selection** — screened E/C under card_cap≤2 (E at Benguerir = **11/14**). Preserve as algorithm-selection history.
2. **observed_infra_ladder / ablation_multi_on_C** — matched multi-route evaluation of infrastructure configs. Benguerir+Larache multi can be **12/14**; that is better observed coverage than screened E and must be reported.

## B_fixed_conventional (not baseline_none)

- B0: no sites, fixed route
- B1: `y_settat_ca`, fixed route
- B2: `y_settat_ca,y_settat_ac`, fixed route

## Energy ≠ ops on B1/B2 conventional

Mission cells where energy OPTIMAL but ops false under LIMIT: **2** (see `energy_ops_limit_contamination.csv`).
Typical OD: `casa_agadir` with Settat. Do not attribute to HOS physics without a conclusive OPTIMAL/INFEASIBLE re-solve.

Source: `results/validation/path_a/coverage_reconciliation.csv`
