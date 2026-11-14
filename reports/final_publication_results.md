# Final publication results package

Repository freeze after publication-readiness audits on Task 08 base `0ca24a1`.

**Defensible headline:** Charging-infrastructure requirements for prospective refrigerated electric freight in Morocco are strongly dependent on vehicle configuration, departure SOC, cargo payload, and route flexibility.

This is **not** a claim that one truck or one charging location is universally best, and **not** a Moroccan investment recommendation.

---

## 1. Corridor and vehicle scenario realism

| Element | Status |
| --- | --- |
| OSM corridor topology + ADM place names | Evidence-graded open/official inputs |
| DEM macros (COP-DEM) | Used for Task 07B/08 DEM cells |
| Path union `max_alts=2` | Scientific pilot (shortest + top Jaccard alt) |
| Hypothetical chargers (Settat / Benguerir / Amskroud) | Not operating verified HGV sites |
| eActros usable energy / peak power | Manufacturer-labeled YAML |
| Volvo usable 475 kWh | Manufacturer MA-page label |
| Volvo continuous/peak 400 kW | **Assumed** mid-menu pick (OEM lists 300–540 without cont/peak split) |
| Empty tractor/trailer masses | Volvo tractor + both trailers **assumed** |
| Manufacturer GCW | Not Moroccan legal axle certification |

See `reports/final_economic_units_and_provenance_audit.md` and `reports/final_heavy_vehicle_feasibility_diagnosis.md`.

---

## 2. Vehicle / SOC / payload sensitivity of charger need

Task 08 DEM refrigerated portfolio (illustrative weights totaling 5.5; one-site budget B1):

| Case | eActros 600 served | Volvo 475 served |
| --- | ---: | ---: |
| 5.3 t, SOC 50% | 4.0 / 5.5 | 2.0 / 5.5 |
| 5.3 t, SOC 80% | 5.5 / 5.5 | 4.0 / 5.5 |
| 5.3 t, SOC 100% | 5.5 / 5.5 | 5.5 / 5.5 |
| 15 t, SOC 50% | 2.0 / 5.5 | **0.0 / 5.5** |
| 15 t, SOC 80% | 4.0 / 5.5 | **0.0 / 5.5** |

Source: `results/task08_soc_payload_comparison.csv`.

**Conditional reading:** the earlier “eActros one site vs Volvo two sites” contrast at SOC 50% / 5.3 t **does not universally survive** higher departure SOC or 15 t cargo. At full SOC and light cargo, both vehicles reach full modeled coverage with one site.

### Heavy Volvo (15 t) — diagnosed, not overclaimed

Even with all candidate sites, Volvo H50/H80 remain 0 / 5.5 under the committed q=10 stack. Diagnosis (`reports/final_heavy_vehicle_feasibility_diagnosis.md`):

| OD | Dominant labels (assumed 400 kW) |
| --- | --- |
| Casa→Agadir | **peak_motor** (clears to SOC-floor at in-memory 540 kW menu bound) |
| Casa→Marrakech @ 50% | **soc_floor** |
| Casa→Marrakech @ 80% | **discrete_grid_reject** at q=10; **served** at q=5 |
| Marrakech→Agadir | **soc_floor** |

Publishable: infeasible under this **assumed** vehicle model and reduced network. **Not** “Volvo cannot transport 15 t in Morocco.”

---

## 3. Added feasibility from alternative-route optimization

Task 07C same-graph nesting still stands: `allowed_arc_ids` masks on one path-union; fixed-shortest can be INFEASIBLE while multi-route is OPTIMAL (feasibility gain). Task 08 adds a synthetic adversarial positive cost-monotonicity test (`tests/unit/test_task08_nesting_and_realism.py`).

Unserved / vacuous cells must be labeled separately from positive nesting.

---

## 4. Refrigeration and terrain effects

Task 07B established DEM vs flat and thermal-ladder stress under the finite model. Those effects remain scoped research findings — not calibrated Moroccan TRU field validation. Task 08 keeps DEM + refrigeration ON + cool weather for the SOC/payload matrix.

---

## 5. Exact finite-model certification and algorithm performance

| Check | Result |
| --- | --- |
| Moroccan placement enum ↔ B&B objectives (Task 08 cells) | Agreement on committed runs |
| Synthetic 8-site enum ↔ B&B (corrected) | Agreement; `CERTIFIED_OPTIMAL` under honest certification |
| Cold-cache speed (corrected) | Enum faster on B2/B3; B&B faster on Ball |
| MRLS `LIMIT_REACHED` → subset uncertified | Enforced in synthetic evaluator + unit test |

Details: `reports/final_algorithm_benchmark_audit.md`, `results/task08_algorithm_benchmarks.csv`.  
Historical pre-fix CSV: `results/task08_algorithm_benchmarks_historical_8site.csv`.

**Do not claim** a general B&B computational superiority from this instance.

---

## 6. Limitations and missing field data

| Gap | Status |
| --- | --- |
| Observed refrigerated trip frequency / GPS | Unavailable (external request) |
| Certified HGV charger power at candidate sites | Unavailable / hypothetical |
| Moroccan legal axle / GCW operating certificate | Not encoded; axle detail unavailable |
| ONEE site tariffs / civil CAPEX quotes | Not invented; illustrative costs only |
| OEM Volvo continuous vs peak power split | Unpublished; 400 kW assumed |
| Empirical TRU electrical load in Moroccan ambient | Not established |

Economic secondary costs remain **class B illustrative** (see provenance audit): annual CAPEX and weight×trip costs lack a shared trips/year unit.

### Marking convention for manuscript tables

| Label | Meaning |
| --- | --- |
| Served | Discrete MRLS OPTIMAL + replay gates under stated assumptions |
| Unserved | Resolved INFEASIBLE under all candidates (or Ball) |
| Unresolved | LIMIT_REACHED / incomplete DEM / search limit |
| Physically unvalidated | Outside model — needs field evidence |

---

## Reproducibility commands

```bash
pytest -q -m "not integration"
python scripts/run_final_heavy_vehicle_diagnosis.py
python scripts/run_task08_final_validation.py --stages benchmark
python scripts/write_task08_reports.py
```

Primary artifacts:

- `reports/final_publication_results.md` (this file)
- `reports/final_heavy_vehicle_feasibility_diagnosis.md`
- `reports/final_algorithm_benchmark_audit.md`
- `reports/final_economic_units_and_provenance_audit.md`
- `results/final_heavy_vehicle_feasibility_diagnosis.csv`
- `results/task08_soc_payload_comparison.csv`
- `results/task08_algorithm_benchmarks.csv`

**STOP:** next activity is manuscript preparation and external Moroccan operational evidence — not Task 09 feature development.
