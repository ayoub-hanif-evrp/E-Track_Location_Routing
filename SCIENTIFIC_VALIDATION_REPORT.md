# Scientific Validation Report (Path A corrections)

**Checkpoint tag:** `path-a-pre-correction-c8d9769`  
**Research direction:** Path A feasibility / infrastructure assessment — **approved**  
**Evidence freeze:** **not approved** until executable corrections below are green  

## Corrected observed infrastructure ladder

Matched multi-route, eActros, q=2, 600 s / 2e6, `results/validation/path_a/infra_ladder/`:

| Config | Sites | Ops | Energy | LIMIT |
|--------|-------|-----|--------|-------|
| I0 | none | **9/14** | 9/14 | 0 |
| I1 | `y_benguerir_ca` | **11/14** | 11/14 | 0 |
| I2 | Benguerir + Larache | **12/14** | 12/14 | 0 |

Historical screened E (Benguerir alone) remains **11/14** — algorithm-selection history only.  
**Do not** describe 11/14 as best-known B2 coverage when I2 = 12/14 is evaluated.

## Energy vs ops

B1/B2 conventional energy>ops gap: `casa_agadir` + Settat → HOS-on `LIMIT_REACHED`, energy-only `OPTIMAL`  
→ `results/validation/path_a/energy_ops_limit_contamination.csv`  
**Not** certified HOS/physical infeasibility.  
`B_fixed_conventional` = fixed routing + Settat-first installs (not `baseline_none`).

## Cold-chain

Headline fridge: `configs/energy/pass2_tomato_firm_ripe.yaml` setpoint **9 °C** (UNECE 8–10).  
Legacy `refrigeration_approx.yaml` **+2 °C** is not the tomato claim.  
Variants: `results/validation/path_a/coldchain/`.

## Consistency checker

`scripts/run_validation_consistency_report.py` now warns on:
- better-evaluated portfolios than screened E
- LIMIT + energy-true + ops-false misinterpretation
- observed infra ladder > historical E

## HOS / CI

- Policy: `results/validation/path_a/hos_single_duty_policy.md`
- Graph CI asset: HTTP 200 `multiroute-graph-v1` (`ci_graph_check.json`)

## Settat escalate (done)

`casa_agadir` + `y_settat_ca` at 1200 s / 5e6: **OPTIMAL** ops=True (fixed and multi).  
Prior B1/B2 energy≠ops gap was LIMIT contamination — now conclusively served under escalate.  
CSV: `results/validation/path_a/limit_escalate/settat_casa_agadir_escalate.csv`.

## Recommendation

**CONDITIONAL → near paper-ready for Path A numerics** (infra ladder I2=12/14, cold-chain, P6 rebake, Settat escalate conclusive).  
Final READY still requires a clean commit review of claims⊆evidence and manuscript sync — not docs alone.
