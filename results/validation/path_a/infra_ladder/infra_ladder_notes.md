# Observed infrastructure ladder (matched multi-route)

Protocol: 600 s / 2e6 expansions, q=2, eActros, hos_in_search ops + energy dual.

| Config | Sites | Ops | Energy | LIMIT |
|--------|-------|-----|--------|-------|
| I0_none | (none) | 9/14 | 9/14 | 0 |
| I1_benguerir_ca | y_benguerir_ca | 11/14 | 11/14 | 0 |
| I2_benguerir_larache | y_benguerir_ca,y_larache_rt | 12/14 | 12/14 | 0 |

## Interpretation

- **Observed I1** (Benguerir alone) is the matched counterpart of historical screened E.
  Observed ops=11/14; historical E ops=11/14.
- **Observed I2** (Benguerir+Larache multi) must be reported if better than I1;
  do **not** keep claiming 11/14 as best-known B2 coverage when I2 > I1.
  Observed I2 ops=12/14.
- Historical enum-selected E remains documented in `historical_enum_selection_reference.csv` (algorithm-selection table).
- Any LIMIT rows are unresolved — not INFEASIBLE / not HOS-physical failures.

Fingerprint: `path_a_infra_ladder_matched_multi` @ `c8d9769ba84469dc65ea434a636949a077aad053`
