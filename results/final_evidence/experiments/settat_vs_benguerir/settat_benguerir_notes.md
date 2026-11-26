# Settat CA vs Benguerir CA (Task 7.1)

Protocol: eActros, stressed mixed SOC, multi-route, q=2.

## Singleton panel coverage

| Config | Ops @ 600s/2e6 | LIMIT | After escalate |
|--------|---------------:|------:|----------------|
| none | 9/14 | 0 | — |
| Settat CA | 10/14 | 1 (`casa_agadir`) | casa_agadir OPTIMAL → **11/14** |
| Benguerir CA | **11/14** | 0 | unchanged |

**Coverage tie at 11/14** once Settat’s LIMIT is escalated. Benguerir is preferable under the **standard computational budget** (resolves without escalate).

## Casa→Agadir operational trade-off

| Site | Budget | Status | Charge | Wait | Stationary | min SOC | Objective |
|------|--------|--------|-------:|-----:|-----------:|--------:|----------:|
| Benguerir CA | 600s/2e6 | OPTIMAL | 65 | 0 | **65** | 0.118 | 51682 |
| Settat CA | 600s/2e6 | LIMIT_REACHED | — | — | unresolved | — | — |
| Settat CA | 1200s/5e6 | OPTIMAL | 75 | 45 | **120** | 0.118 | 51722 |

Previously recorded 120 vs 65 min stationary durations are **verified** under the final protocol (Settat escalate). Do not attribute the difference solely to HOS without a controlled HOS on/off experiment — both solutions pass schedule audit with `pad=False` here.

Files: `singleton_ledger.csv`, `casa_agadir_settat_vs_benguerir.csv`, `settat_casa_agadir_escalate.csv`, `tables/results/R-T04_*`.
