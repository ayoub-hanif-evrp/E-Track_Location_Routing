# PASS 2 — Final claims and provenance ledger

Base PASS 1: `20d5557`  
PASS 2A: `e1832c0` (+ this package)  
Date: 2026-11-14

---

## Claims allowed

| # | Claim | Evidence | Grade |
| --- | --- | --- | --- |
| 1 | Task 07/08 primary portfolios are southbound-only | PASS 1 freight audit | Confirmed |
| 2 | Northbound Souss-Massa refrigerated agricultural logistics has credible **category-level** Moroccan motivation (Tanger Med / operator footprint) | PASS 1 + PASS 2A | Sourced motivation |
| 3 | `agadir_casa` is a **corridor research proxy**, not an observed shipment OD terminating at Casablanca | PASS 2A labels | Required honesty |
| 4 | Independent Copernicus DEM for `agadir_casa` macros was generated (not reversed southbound arrays) | `fetch_multiroute_dem.py --od-ids agadir_casa --merge-meta` | Validated |
| 5 | Only `settat_ac` / `benguerir_ac` used; `amskroud_ac` not fabricated | PASS 2A config | Confirmed |
| 6 | Firm-ripe tomato setpoint 9 °C (UNECE 8–10 °C band) replaces universal +2 °C for Case A | `pass2_tomato_firm_ripe.yaml` | Category reference |
| 7 | Legal mass status = `gross_mass_within_limit_axle_unverified` (40 t Art. 3 screen; axles unchecked) | Decree 2-10-421 + PASS 2A legal report | Confirmed |
| 8 | Under assumed power + northbound DEM path-union, Case A is peak-motor / model-infeasible; chargers do not restore service | PASS 2A routing/placement | Model-scoped |
| 9 | Enum ↔ B&B agree on Case A placement (coverage 0) | PASS 2A placement CSV | Confirmed |
| 10 | q=10 can falsely mark southbound H80 portfolio Ball unserved while q=5 serves weight 2.0 with no sites | PASS 2B CSV | Confirmed counterexample |
| 11 | Certification-aware q refinement is at most a **diagnostic hygiene** contribution | PASS 2B novelty report | CONDITIONAL_DIAGNOSTIC_ONLY |

---

## Claims forbidden

| Forbidden statement | Why |
| --- | --- |
| Agadir→Casablanca is an observed refrigerated shipment dataset | Only a proxy |
| Volvo/eActros cannot haul tomatoes northbound in Morocco | Peak-motor under **assumed** power / DEM artifacts / reduced network |
| Sites are operating verified 350 kW HGV chargers | Hypothetical |
| Combination is `legally_certified` | Axles unverified |
| Adaptive q refinement is a continuous-optimal / top-tier new algorithm | No proof; prior art already covers SoC discretization & LRP |
| B&B is generally faster / scales nationally | Not shown |
| Mixing northbound exports + southbound distribution as one verified annual demand | Explicitly disallowed |

---

## Historical results

| Artifact | Status |
| --- | --- |
| Task 07/08 southbound portfolios | Retained as Case B / historical |
| `results/final_heavy_vehicle_feasibility_diagnosis_historical.csv` | Pre-claim-fix archive |
| `results/final_heavy_vehicle_feasibility_diagnosis.csv` | Claim fields corrected for integrity |
| Task 08 algorithm historical CSV | Retained earlier |

---

## Reproduction

```bash
python scripts/fetch_multiroute_dem.py --od-ids agadir_casa --merge-meta --max-alts 4
python scripts/run_pass2a_northbound_benchmark.py
python scripts/run_pass2b_discretization_refinement.py
pytest -q -m "not integration"
```

Primary outputs:

- `reports/pass2_northbound_moroccan_benchmark.md`
- `reports/pass2_refrigerated_cargo_and_legal_screen.md`
- `reports/pass2_discretization_novelty_result.md`
- `reports/pass2_final_claims_and_provenance.md`
- `results/pass2_northbound_routing.csv`
- `results/pass2_northbound_placement.csv`
- `results/pass2_refinement_comparison.csv`
