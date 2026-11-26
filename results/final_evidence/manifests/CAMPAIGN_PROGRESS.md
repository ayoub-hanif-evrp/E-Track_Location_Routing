# Final evidence campaign — progress log

Baseline: `8b0cbf716cc342550299895d4da58889b8239d37`

## Status: COMPLETE

All required dataset characterization, primary/robustness experiments, figures D-1…D-6 & R-1…R-11, tables D-T01…D-T07 & R-T01…R-T13, final report, release manifest, and consistency gate are under `results/final_evidence/`.

## Completed blocks

### P0 — Dataset audit & design freeze
- Independent recount: all claimed counts match.
- Tables D-T01…D-T07; quality/construction report.
- Experiment design freeze + 168-cell primary inventory.
- HOS duty-scope regression: journey horizon = 24 h.
- Topology notes: Amskroud CA on `marrakech_agadir`; Benguerir/Settat AC on `agadir_casa`.

### P1 — Primary comparison (168/168)
| Vehicle | SOC | I0 | I1 | I2 |
|---------|-----|---:|---:|---:|
| eActros | stressed | 9 | 11 | 12 |
| eActros | common 80% | 11 | 12 | 13 |
| Volvo | stressed | 7 | 7 | 8 |
| Volvo | common 80% | 8 | 9 | 10 |

LIMIT=0 on primary grid. Settat escalate: Benguerir 65 min vs Settat 120 min stationary; coverage tie 11/14 after escalate.

### P2 — Robustness / physics
- Fridge on/off + UA×1.25; CdA/Crr/aux/charger/weather; adverse packs (45 headline cells).
- Fine SOC brackets (15 cells) near known transitions.
- DEM vs flat (R-T09); Path A coldchain archived.

### P3 — Routing / resolution / packaging
- Fixed vs flexible routing (24 cells) → R-T10.
- Direction-blind supplementary figure.
- q-grid (R-T11) with transparent non-reproduction note.
- Infeasible diagnosis (R-T12).
- Final scientific report + release manifest + cleanup addendum.

## Consistency

`validation/consistency_report.json`: ladder_ok=true (I0=9, I1=11, I2=12), n_primary_missions=168.
