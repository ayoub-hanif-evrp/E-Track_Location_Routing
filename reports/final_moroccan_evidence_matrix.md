# Final Moroccan evidence matrix

**Purpose:** grade every input and outcome class for the Agadir$\rightarrow$Casablanca refrigerated eHDT corridor study without fabricating field data.  
**Numeric cells:** use **TBD_FROM_CSV** until regenerated from `results/*.csv` at submission time.

---

## Evidence grade legend

| Grade | Meaning |
| --- | --- |
| **A -- Sourced official** | Public authority or manufacturer document with stable citation |
| **B -- Open geodata / reproducible extract** | OSM, COP-DEM, repo-processed with commit hash |
| **C -- Engineering assumption** | Explicit YAML scenario; sensitivity planned |
| **D -- Hypothetical / prospective** | Future truck infrastructure not observed on site |
| **E -- Unavailable / pending** | Required for validation; outreach in progress |
| **X -- Superseded** | Do not cite in manuscript primary text |

---

## A. Geography and network

| Item | Grade | Source / artifact | Manuscript use |
| --- | --- | --- | --- |
| Motorway topology Agadir--Marrakech--Casablanca | B | OSM extract + repo graph build | Corridor map Fig.~01 |
| Directional path alternatives | B | `path_alternatives.csv`, decision graphs | Multi-route nesting |
| ADM service-area **names** Settat / Benguerir / Amskroud | A | ADM directory | Site identity only |
| Truck-suitable access geometry | E | `reports/site_access_audit.csv` | No access certification |
| Reverse carriageway charger candidates | C--D | Partial topology; gaps noted in PASS~1 audit | Northbound primary |

---

## B. Energy and terrain

| Item | Grade | Source / artifact | Manuscript use |
| --- | --- | --- | --- |
| COP-DEM GLO-30 slope macros | B | ESA Copernicus | DEM vs flat comparisons |
| Cruise / maxspeed policy | C | Research policy + OSM tags | Speed uncertainty |
| Discrete $q$ panel $\{10,5,2,1\}$ kWh | C | Method design | Convergence diagnostics |
| Continuous replay traces | C | `continuous_replay.py` | **SIMULATION_REPLAY_VALIDATED** |
| Complete trip distance (Agadir$\rightarrow$Casa, eActros NB) | B+C | `physical_trace_reconciliation.csv` | TBD_FROM_CSV km |

---

## C. Vehicle and cargo

| Item | Grade | Source / artifact | Manuscript use |
| --- | --- | --- | --- |
| Mercedes-Benz eActros 600 usable energy | A | Manufacturer YAML | Primary northbound tractor |
| Volvo FH Electric 475 kWh | A (usable) / C (peak split) | Manufacturer + assumed kW | Comparator only |
| GCW / axle Moroccan certification | E | Not encoded | Limitation paragraph |
| Firm-ripe tomato setpoint proxy | C | `pass2_tomato_firm_ripe.yaml` | Illustrative commodity |
| Payload 5.3 t / 15 t bands | C | Task 08 design | SOC--payload matrix |
| Departure SOC $\{0.5,0.8,1.0\}$ | C | Scenario grid | TBD_FROM_CSV coverage |

---

## D. Refrigeration and thermal

| Item | Grade | Source / artifact | Manuscript use |
| --- | --- | --- | --- |
| UA 50/80/120 W/K ladder | C | Task 07B YAMLs | Sensitivity only |
| Bank et al.\ (2025) physics bar | A (literature) | DOI 10.1016/j.ijrefrig.2025.04.026 | Citation; not calibration |
| Field TRU kWh in Moroccan ambient | E | No operator logs | Outreach priority |
| Refrigeration negligible vs traction claim | B+C | Prior repo ablations | TBD_FROM_CSV effect size |

---

## E. Infrastructure and economics

| Item | Grade | Source / artifact | Manuscript use |
| --- | --- | --- | --- |
| Hypothetical 150/350 kW truck chargers | D | Planning assumption | Not ADM AZUR car-only reality |
| Site install CAPEX / variable kWh cost | D | Normalized illustrative units | Secondary objective only |
| ONEE industrial tariffs | E | Not quoted | No investment optimality |
| Minimum site count / coverage | C+D | Optimization outputs | Primary decision metric TBD_FROM_CSV |

---

## F. Optimization outcomes (selected claims)

| Claim | Grade | Evidence file | Status |
| --- | --- | --- | --- |
| $q=10$ INFEASIBLE, $q\in\{5,2,1\}$ OPTIMAL (NB canonical-4) | B+C | `moroccan_energy_grid_convergence.csv` | TBD_FROM_CSV |
| Ball sites stable `{y_benguerir_ac}` for served fine $q$ | B+C | Same CSV | Conditional; **not** universal |
| Benguerir universally optimal | **X** | N/A | **Do not claim** |
| Charge energy converged across $q$ | **E** | Pending audit | 175$\rightarrow$94~kWh **not converged** |
| Volvo 15~t unserved at $q=10$ but served at $q=5$ (selected OD) | B+C | H80 diagnosis CSV | Discrete-grid symptom |
| B\&B faster than enum in general | **X** | `task08_algorithm_benchmarks.csv` | Instance-dependent only |

---

## G. External Moroccan logistics motivation (non-numeric)

| Source | Grade | Supports | Does not support |
| --- | --- | --- | --- |
| Tanger Med -- Souss-Massa exporters (2023 page) | A | Northbound produce export **motivation** | Trip counts |
| SOTRAFRIQUE public fleet page | A | Operator existence, cold-chain footprint | GPS / energy logs |
| Moroccan cold-chain regulations | A/B | Setpoint plausibility bands | SKU-level compliance proof |

---

## H. Manuscript hard stops

1. No **PHYSICALLY_VERIFIED** label --- use **SIMULATION_REPLAY_VALIDATED** where replay passes.
2. No fabricated Moroccan trip frequencies or charger utilisation.
3. No investment recommendation for Benguerir or Settat.
4. All table numerals trace to `paper/claims_to_results_crosswalk.csv` rows with `pending` cleared only after CSV regeneration.