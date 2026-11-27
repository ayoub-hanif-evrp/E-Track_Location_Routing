# P5 — Reconciliation after journal corrections

## Coverage table policy

The historical **224-cell I0–I3** coverage (baseline `518bc11`) remains the **authoritative headline** under the **5-minute** HOS-in-search policy:

| Vehicle / scenario | I0 | I1 | I2 | I3 |
|---|---:|---:|---:|---:|
| eActros stressed | 9/14 | 11/14 | 12/14 | 13/14 |
| eActros common 80% | 11/14 | 12/14 | 13/14 | 14/14 |
| Volvo stressed | 7/14 | 7/14 | 8/14 | 8/14 |
| Volvo common 80% | 8/14 | 9/14 | 10/14 | 10/14 |

No global rewrite under mixed time resolutions. P0 shows Volvo Marrakech→Agadir @80% I2 would become ops-feasible at **2 min / 1 min** timesteps — report as a **labeled time-discretization sensitivity**, not as silently updated coverage.

## Volvo Settat vs Benguerir preference reversal

Matched panel under 5-minute policy stands (no physics change from P1 visualization fix):

| SOC | Benguerir+Larache | Settat+Larache |
|---|---:|---:|
| Stressed | 8/14 | 9/14 |
| Common 80% | 10/14 | 9/14 |

Paired efficiency comparisons must use the intersection of missions feasible under **both** configs (existing matched panel artifacts).

## Heavier payload (new)

Infrastructure enablement of Casa–Marrakech / Casa–Agadir at stressed 50% SOC **fails at 10–15 t** under I1 in the finite matched set. Headline coverage claims must be scoped to the **5.3 t** scenario unless heavier-payload tables are cited.

## Effective initial SOC (Volvo 475 kWh)

Integer-kWh initialization can yield nominal 50% → effective ≈50.105%. Threshold experiments should record both nominal and effective initial energy; no global SOC-threshold rewrite was required by P2–P4 cells in this pass.
