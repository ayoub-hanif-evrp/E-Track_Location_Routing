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

P4 closure (`experiments/volvo_settat_vs_benguerir/P4_paired_efficiency_notes.md`, `tables/results/R-T24_volvo_settat_benguerir_paired.csv`):

- **Coverage preference reverses by SOC** (Settat +1 stressed on `casa_marrakech`; Benguerir +1 common on `casa_agadir`) — distinct from operational efficiency.
- **Paired efficiency (@ `ts5`):** 8 stressed + 9 common missions both ops-served; **all objective/route metrics tie** (zero pairwise deltas).
- **Time-discretization:** `affected_case_inventory_224plus.csv` / `refined_time_matched_reevals.csv` may flip *other* cells at `ts2`/`ts1` (e.g. primary-panel Marrakech→Agadir); they do **not** rewrite the 56-cell Volvo Settat vs Benguerir **coverage winner** @ `ts5`. Label refined timestep separately; do not conflate with this panel.

Paired efficiency comparisons must use the intersection of missions feasible under **both** configs (existing matched panel artifacts).

## Heavier payload (new)

Infrastructure enablement of Casa–Marrakech / Casa–Agadir at stressed 50% SOC **fails at 10–15 t** under I1 in the finite matched set. Headline coverage claims must be scoped to the **5.3 t** scenario unless heavier-payload tables are cited.

## Effective initial SOC (Volvo 475 kWh)

Integer-kWh initialization can yield nominal 50% → effective ≈50.105%. Threshold experiments should record both nominal and effective initial energy; no global SOC-threshold rewrite was required by P2–P4 cells in this pass.
