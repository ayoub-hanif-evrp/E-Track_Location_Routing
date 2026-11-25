# Path A Gate 2 — Experimental design freeze

Frozen before any Gate 3 re-runs. Do not expand geography, enum beyond card≤2, or multi-day Art.16 overnight rest for the paper core.

## Panel and sites

| Item | Freeze |
|------|--------|
| OD panel | 14 equal-weight missions (headline corridor panel) |
| Candidate sites | 9 directional ADM sites |
| Primary vehicle | eActros 600 |
| Primary q | 2 kWh |
| Certification protocol | 600 s / 2×10⁶ expansions; status ∈ {OPTIMAL, INFEASIBLE, LIMIT_REACHED} |
| Enum | card_cap ≤ 2; screen 45 s; winners 600 s |
| Pipeline id | `hos_in_search_enum_cap2_screen45_final600` |

## Blocks

| Block | Content | Acceptance |
|-------|---------|------------|
| Infra ladder | B0 / B1 (Benguerir E; Larache C) / B2 (Benguerir+Larache C; Benguerir E) | Ops totals match `coverage_reconciliation.csv`; 0 unexplained LIMIT in reported cells |
| Flexibility | Matched fixed vs multi on identical C and E installs | Nesting classes; report zero-gain honestly; **do not** cite ablation multi_on_C=12/14 as B2 headline |
| Thresholds | SOC×payload southbound + critical ODs | Feasible/infeasible frontier; statuses complete |
| Discretization | q ∈ {5,2,1} Agadir→Casa 15 t SOC 0.8 | Retain false-infeasibility at q=5 |
| Directionality | AC vs CA Benguerir on disputed ODs | Show which direction unlocks service |

## Authoritative coverage ladder (manuscript only)

From `results/validation/path_a/coverage_reconciliation.csv` (`authoritative_for_manuscript=True`):

- B0: 9/14
- B1: C=10/14 (Larache), E=11/14 (Benguerir CA)
- B2: C=11/14 (Benguerir+Larache), E=11/14 (Benguerir CA)

**12/14** is ablation multi-on-C only (FLEX_GAIN on `casa_marrakech`) — not the B2 headline.

## Non-goals

- New optimization algorithm / SOTA benchmarks
- Full multi-day Art.16 overnight 12 h rest
- Hundreds of sites / national CAPEX without cost data
- Designing experiments to force a predetermined coverage gain

## Settat footnote

B1 Settat `casa_agadir` LIMIT: either escalate that single cell to OPTIMAL/INFEASIBLE or footnote as unresolved and keep “best among resolved.”
