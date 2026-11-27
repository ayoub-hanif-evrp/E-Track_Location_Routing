# Final numerical validation report (journal evidence package)

**Baseline commit:** `518bc11a119c6f59ac2b11fa484d307d363336f6` (`evidence-freeze-518bc11`)  
**Path A:** Operational feasibility of battery-electric refrigerated freight on Moroccan motorway corridors  
**Target venue framing:** TRIP-style applied transportation evidence (no manuscript in this package)

## Executive verdict

Scientific correctness gates for **temporal HOS discretization (P0)** and **executed-route DEM geometry (P1)** are established. Headline **224-cell I0–I3 coverage** is preserved under the historical **5-minute** HOS-in-search policy. Corrections that would raise Volvo Marrakech→Agadir feasibility are reported as a **labeled time-resolution sensitivity**, not silently merged into coverage. Refrigeration remains energetically small on tested near-threshold cells; heavier payloads can remove I1 feasibility at stressed SOC.

## Deliverable map

| # | Deliverable | Location |
|---|---|---|
| 1 | This report | `validation/FINAL_NUMERICAL_VALIDATION_REPORT.md` |
| 2 | Temporal discretization | `experiments/time_discretization/` + `R-Figure10b` + `R-T14_*` |
| 3 | Executed-route / DEM audit | `experiments/executed_route_geometry/` |
| 4 | Physical provenance / benchmarks | `experiments/physical_model/` + `R-T15`/`R-T16` |
| 5 | Refrigeration + payload robustness | `experiments/journal_p2_p4/` + `R-T17`/`R-T18` + `R-Figure11` |
| 6 | Authoritative infrastructure results | `experiments/primary_i0_i3_panel/` (baseline preserved) |
| 7–8 | Dataset inventory / figures | `tables/dataset/` + `figures/dataset/` |
| 9–10 | Results figures / catalog | `figures/results/` (+ descriptions) |
| 11 | Literature matrix | `literature/P9_literature_comparison_matrix.md` |
| 12–13 | Manifest / validation | `executable_validation.py` + manifests |
| 14 | Limitations / findings class | `validation/P10_findings_classification.md` |

## P0 summary

Volvo MA @80% I2: phys drive **265.62 min** < 270; 5-min per-arc ceil **285** → ops INF; 2/1 min → served. Casa–Tangier wait is modeled break completion under discrete inflation.

## P1 summary

32+ successful itineraries: full geometry + DEM coverage via child or parent-slice; **0** solver flat fallbacks. Prior figure gaps were visualization-only. R-Fig2 served missing arcs = **0** after I3 agadir_casa fill.

## P2–P5 summary

See `journal_p2_p4/P2_P4_findings.md` and `P5_reconciliation_notes.md`.

## Closing pass (remaining gaps)

- **P2.3** engineering boundary checks: 26/26 pass (`R-T19_*`).
- **P5.3** effective initial SOC: Volvo 50% → ≈50.105% (`R-T20_*`).
- **P5.4** battery-capacity-only CF: Volvo params + 600 kWh usable restores Casa–Marrakech @50%/I1 (`R-T21_*`).
- **P8** LF `.gitattributes`; generate=`executable_validation.py`; verify=`verify_release_manifest.py` (VERIFIED).

## Stopping status

**COMPLETE.** Headline coverage remains the 5-minute 224-cell ladder. Do not begin manuscript writing.
