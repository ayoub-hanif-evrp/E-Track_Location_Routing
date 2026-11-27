# Journal-level validation — finite experiment inventory

**Baseline commit:** `518bc11a119c6f59ac2b11fa484d307d363336f6`  
**Git tag:** `evidence-freeze-518bc11`  
**Target:** TRIP-style applied transportation paper (Path A)  
**Rule:** Preserve historical baseline; report corrections with mechanisms. Do not treat coverage as an acceptance target.

## Computational budget and escalation

| Tier | Scope | Budget |
|---|---|---|
| A | Diagnostics / audits (no full panel) | ≤ 20 targeted solves |
| B | Time-resolution / geometry / physics checks | ≤ 60 targeted solves |
| C | Limited matched re-runs of affected headline cells | ≤ 80 cells |
| Stop | No unrestricted infrastructure enumeration; no new cities; no algorithm redesign | — |

Unresolved LIMIT ≠ INFEASIBLE. Escalate time/expansions only with predefined caps.

## Execution order

1. **P0** Time discretization (Volvo Marrakech–Agadir; campaign screen; Casa–Tangier wait; HOS policy doc)
2. **P1** Executed-route geometry + DEM (solver vs visualization)
3. **P2–P4** Provenance, refrigeration, payload/weather (finite)
4. **P5** Reconcile infrastructure comparisons if corrections change results
5. **P6–P7** Dataset + results figures/tables
6. **P8–P10** Reproducibility, literature matrix, final audit

## P0 finite inventory

| ID | Experiment | Cells | Notes |
|---|---|---:|---|
| P0.1 | Per-arc physical vs discrete on Volvo MA energy itinerary @ I2 | 1 | Join solver `dt_steps` + replay `dt_s` |
| P0.2A | Global time-grid `ts∈{5,2,1}` energy+ops Volvo MA I2 | 3 | Scale `deadline_steps` to wall-clock |
| P0.2B | Offline ceil/floor/round HOS screen on frozen energy trace | 0 solves | Diagnostic only |
| P0.3 | Screen all primary OPTIMAL traces + energy-OK/ops-INF for ceil inflation | 0–N | Re-solve only proximity cases |
| P0.4 | Casa–Tangier eActros wait mechanism (schedule excerpt + refined ts if needed) | ≤3 | |
| P0.5 | HOS legal policy documentation (BO 5878 bis) | 0 | Literature/legal |

## Historical baseline to preserve (do not treat as targets)

| Vehicle / scenario | I0 | I1 | I2 | I3 |
|---|---:|---:|---:|---:|
| eActros stressed | 9 | 11 | 12 | 13 |
| eActros common 80% | 11 | 12 | 13 | 14 |
| Volvo stressed | 7 | 7 | 8 | 8 |
| Volvo common 80% | 8 | 9 | 10 | 10 |

Plus: 224 primary cells; 56 Volvo Settatt/Benguerir matched; 45 robustness; historical 15 t q-grid; DEM/flat; fine SOC brackets.

## Stopping criteria

Campaign is **COMPLETE** only if mandatory correctness gates pass.  
Campaign is **CONDITIONAL** if a mandatory issue remains unresolved — name the affected claim explicitly.  
Do not start manuscript writing.
