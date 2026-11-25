# Path A experimental design (corrected)

## Observed infrastructure configs (authoritative for RQ2)

Protocol: multi-route, eActros, q=2, 600 s / 2e6 expansions.

| ID | Sites | Expected role |
|----|-------|---------------|
| I0 | ∅ | no new chargers |
| I1 | `y_benguerir_ca` | matched counterpart of historical E |
| I2 | `y_benguerir_ca` + `y_larache_rt` | two-site observed coverage |

**Observed results:** I0=9/14, I1=11/14, I2=12/14 (0 LIMIT) — see `infra_ladder/`.

## Historical algorithm-selection (separate table)

Screened enum_cap≤2 E at Benguerir = 11/14. Preserve; do not call best-known B2 coverage.

## Energy / ops

Never attribute energy≠ops to HOS physics while status is LIMIT_REACHED.

## Cold-chain

Headline: tomato 9 °C (`pass2_tomato_firm_ripe.yaml`). Compare on/off + UA demand; re-bake DRIVE tables.

## Robustness

CdA / aux / weather / **real** `charger_power_kw` via prepare; assert station power matches.
