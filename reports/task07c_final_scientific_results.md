# Task 07C — Final scientific results

Finite-model research freeze after route-nesting repair. Not a Moroccan install recommendation.

## Finding 1 — Infrastructure: when battery assumptions change site count

| Cell | Vehicle | B1 cov | B1 sites | B2 sites | optima | agree |
| --- | --- | ---: | --- | --- | --- | --- |
| F0_dem_nominal_q10 | eactros_600 | 4.0 | y_benguerir_ca | y_benguerir_ca | y_benguerir_ca|y_settat_ca | True |
| F0_dem_nominal_q10 | volvo_475 | 2.0 | y_settat_ca | y_benguerir_ca,y_settat_ca | y_settat_ca | True |
| F1_dem_nominal_q5 | eactros_600 | 4.0 | y_benguerir_ca | y_benguerir_ca | y_benguerir_ca|y_settat_ca | True |
| F1_dem_nominal_q5 | volvo_475 | 2.0 | y_settat_ca | y_benguerir_ca,y_settat_ca | y_settat_ca | True |
| F2_dem_high_thermal | eactros_600 | 4.0 | y_benguerir_ca | y_benguerir_ca | y_benguerir_ca|y_settat_ca | True |
| F2_dem_high_thermal | volvo_475 | 2.0 | y_settat_ca | y_benguerir_ca,y_settat_ca | y_settat_ca | True |
| F3_dem_12h_150kw | eactros_600 | 4.0 | y_benguerir_ca | y_benguerir_ca | y_benguerir_ca|y_settat_ca | True |
| F3_dem_12h_150kw | volvo_475 | 2.0 | y_settat_ca | y_benguerir_ca,y_settat_ca | y_settat_ca | True |

## Finding 2 — Method: what joint route choice adds on the same graph

| Vehicle | OD | install | B obj (shortest MRLS) | C obj (multi) | gain | nesting_ok |
| --- | --- | --- | ---: | ---: | ---: | --- |
| eactros_600 | casa_marrakech | none | nan | nan | nan | True |
| eactros_600 | casa_marrakech | settat_benguerir | nan | 28517.0 | nan | True |
| eactros_600 | casa_agadir | none | nan | nan | nan | True |
| eactros_600 | casa_agadir | settat_benguerir | 53202.0 | 53202.0 | 0.0 | True |
| eactros_600 | marrakech_agadir | none | nan | nan | nan | True |
| volvo_475 | casa_marrakech | none | nan | nan | nan | True |
| volvo_475 | casa_marrakech | settat_benguerir | nan | 29777.0 | nan | True |
| volvo_475 | casa_agadir | none | nan | nan | nan | True |
| volvo_475 | casa_agadir | settat_benguerir | nan | 55553.0 | nan | True |
| volvo_475 | marrakech_agadir | none | nan | nan | nan | True |

Deterministic fixed-route policy (A) rows: 10; OPTIMAL=1.

## Finding 3 — Cold-chain significance

| Vehicle | thermal | status | obj | E_refrig_drive | E_traction |
| --- | --- | --- | ---: | ---: | ---: |
| eactros_600 | thermal_nominal | OPTIMAL | 53202 | 2.1045066106562835 | 590.9013626959703 |
| eactros_600 | thermal_nominal | OPTIMAL | 53202 | 2.1045066106562835 | 590.9013626959703 |
| eactros_600 | thermal_high | OPTIMAL | 53202 | 3.156759915984422 | 590.9013626959703 |
| volvo_475 | thermal_nominal | OPTIMAL | 55553 | 2.518508882599879 | 570.9222486834583 |
| volvo_475 | thermal_nominal | OPTIMAL | 55553 | 2.518508882599879 | 570.9222486834583 |
| volvo_475 | thermal_high | OPTIMAL | 55553 | 3.7777633238998174 | 570.9222486834583 |

Interpretation must not inflate TRU to force siting. If objectives/coverage are unchanged vs nominal, report cold-chain as secondary energy share under documented UA ranges.

## Failed or invalidated robustness items

1. **Task 07B routing baselines A/B vs D nesting claims** — invalidated (different physical graphs via `max_alts` rebuild). See `task07c_route_nesting_integrity.md`.
2. **Task 07B baselines B and C** — not independent methods (identical setup).
3. Any row with `dem_incomplete`, `BUILD_ERROR`, or `nesting_ok_vs_B=False` in Task 07C CSVs is a failed gate for that cell.

## Framing

Prospective evidence-graded optimization study. Requires external fleet/charger-access data before any field-validated performance claim.
