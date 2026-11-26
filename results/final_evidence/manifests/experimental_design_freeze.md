# Final evidence campaign — experimental design freeze

**Baseline commit:** `8b0cbf716cc342550299895d4da58889b8239d37`  
**Campaign:** Dataset characterization + numerical results + maps/figures/tables (no manuscript work).  
**Frozen before expensive runs.** Reuse Path A results only when implementation fingerprints match.

## Historical reference (preserve; report if corrected)

| Config | Sites | eActros coverage (ops) |
|--------|-------|------------------------|
| I0 | ∅ | 9/14 |
| I1 | `y_benguerir_ca` | 11/14 |
| I2 | `y_benguerir_ca` + `y_larache_rt` | 12/14 |

Zero unresolved `LIMIT_REACHED` on the matched multi-route ladder at 600 s / 2e6. Settat Casa→Agadir escalate closed as OPTIMAL under higher budget (see `results/validation/path_a/limit_escalate/`).

## Headline mission panel (14)

`casa_marrakech`, `casa_agadir`, `marrakech_agadir`, `agadir_marrakech`, `marrakech_casa`, `agadir_casa`, `casa_tangier`, `tangier_casa`, `tangier_rabat`, `rabat_tangier`, `rabat_fes`, `fes_rabat`, `casa_rabat`, `rabat_casa`.

**Excluded (constructed but not headline):** `fes_oujda`, `oujda_fes`, `casa_oujda`, `oujda_casa`.

## Primary comparison grid (Task 5–6)

| Axis | Levels |
|------|--------|
| Vehicles | `eactros_600`, Volvo FH Electric (`volvo_fh_electric_4x2_540kwh (usable 475 kWh; registry key volvo_475)` / registry `volvo_475`) |
| Departure SOC | **Stressed** (existing mixed: 50% selected southbound, 80% elsewhere); **Common-SOC** (80% all 14) |
| Infrastructure | I0, I1 (`y_benguerir_ca`), I2 (`y_benguerir_ca`+`y_larache_rt`) |
| Missions | 14 headline ODs |
| Payload | 5.3 t (headline) |
| Route mode | multi |
| Energy grid | q=2 kWh confirm |
| Solver budget | 600 s / 2e6 expansions (escalate only if LIMIT) |
| Cold chain | tomato firm-ripe 9 °C, precooled cargo assumption |
| Reserve | 0.10 SOC |

**Cells:** 2 × 2 × 3 × 14 = **168** primary operational solves (reuse fingerprint-matched Path A eActros stressed I0–I2 where valid).

## Targeted follow-ups (finite budget)

1. **Settat vs Benguerir** (Task 7.1): singleton `y_settat_ca` vs `y_benguerir_ca` on Casa→Agadir and full 14 where needed; one-site ledger.
2. **Infeasible diagnosis** (Task 7.2): `marrakech_agadir`, `agadir_casa` — topology accessibility + targeted existing candidates / operating changes (no arbitrary new sites).
3. **Directional access matrix** (Task 7.3): OD × candidate from route topology; labeled direction-blind counterfactual.
4. **Payload–SOC frontiers** (Task 8.1): payloads {5.3, 10, 15} t × existing SOC grid; finer SOC near transitions; representative long/near-boundary missions.
5. **Headline-condition sensitivity** (Task 8.2): Casa–Marrakech, Casa–Agadir (+ Tangier / remaining infeasible as relevant).
6. **Combined adverse** (Task 8.3): ≤5 predefined stress packs; assert overrides hit physics.
7. **Refrigeration on/off** (Task 8.4): 9 °C tomato; quantify kWh fraction.
8. **DEM vs flat** (Task 8.5): controlled counterfactual on same routes.
9. **q-grid** (Task 9): Agadir–Casa q∈{5,2,1} + small near-boundary set; fixed vs flexible routing.

## Status vocabulary (mandatory)

`OPTIMAL` / feasible · `INFEASIBLE` / model-infeasible · `LIMIT_REACHED` / unresolved · `audit-failed` · `MULTI_DAY_OUT_OF_SCOPE` / out-of-scope.

**Never equate `LIMIT_REACHED` with infeasibility.**

## Output root

`results/final_evidence/{dataset,experiments,validation,tables,figures,manifests}/`

Path A historical evidence remains under `results/validation/path_a/`.

## Computational budget (cap)

| Block | Cap |
|-------|-----|
| Primary grid | 168 cells; reuse Path A eActros stressed when fingerprint matches |
| Settat / diagnosis / direction | ≤40 targeted solves + topology audits |
| Robustness / fridge / DEM | ≤80 targeted solves |
| q-grid / flex | ≤30 solves |
| Escalations | only on LIMIT; document budget |

Stop expanding scope once caps are met; retain unresolved rather than widening geography or inventing sites.
