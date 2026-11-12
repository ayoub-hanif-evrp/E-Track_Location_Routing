# Task 08 — Claims, evidence, and limitations

## Main claims (scoped)

1. **Under the tested DEM refrigerated portfolio**, vehicle usable energy and route flexibility affect the minimum hypothetical ADM site count needed for modeled coverage (weight 5.5 with MA often unserved).
2. **Same-graph multi-route MRLS** can restore feasibility when fixed-shortest is infeasible (Task 07C/08 matched masks).
3. **Synthetic shared-road B&B** matches enumeration on the 8-site Task 08 benchmark (correctness/pruning demo — not national scale).
4. **Headline challenge (Task 08):** the Task 07A/07C eActros one-site vs Volvo two-site contrast at SOC 0.5 / 5300 kg **does not universally survive** SOC 0.8/1.0 or equal 15 t cargo — disappearance reported without retuning.

## Evidence grades

| Input | Grade |
| --- | --- |
| Volvo/eActros usable kWh, empty combo, tech GCW | Manufacturer verified (YAML) |
| ADM site identity / OSM topology | Official + OSM |
| 350 kW truck charging at Settat/Benguerir/Amskroud | **Unavailable / hypothetical** |
| Departure SOC 0.5/0.8/1.0 | Engineering assumption (dispatch policy) |
| Payload 5300 / 15000 kg | Engineering assumption |
| Demand weights total 5.5 | Illustrative |
| Site CAPEX = 100 research units | Illustrative |
| Uniform electricity ¢/kWh | Illustrative (not an ONEE site quote) |
| DEM macros | Official open data (COP-DEM) |

## Economics provenance (Gate 4)

| Cost component | Treatment |
| --- | --- |
| Charger equipment | Illustrative (bundled into site CAPEX=100) |
| Civil / installation | Illustrative (bundled) |
| Grid connection / upgrades | **Unavailable** for these sites — not modeled |
| O&M | Not modeled |
| Energy purchased | Uniform research tariff; ONEE public tariffs are transferability-qualified only if cited as sensitivity — this freeze keeps uniform ¢/kWh |
| Road operating cost | Research 100 ¢/km |
| Annualization | CRF from 8% / 15 yr |
| Freight-demand weights | Illustrative |

CAPEX ratio sensitivity (0.5× / 1× / 2×) on equal illustrative site costs:

| Ratio | Vehicle | Budget | Sites | Coverage | Secondary |
| --- | --- | --- | --- | ---: | ---: |
| 0.5 | eactros_600 | B1 | y_benguerir_ca | 4.0 | 1640.2214772468012 |
| 0.5 | eactros_600 | B2 | y_benguerir_ca | 4.0 | 1640.2214772468012 |
| 0.5 | eactros_600 | Ball | y_benguerir_ca | 4.0 | 1640.2214772468012 |
| 0.5 | volvo_475 | B1 | y_benguerir_ca,y_settat_ca | 4.0 | 1718.282954493602 |
| 0.5 | volvo_475 | B2 | y_benguerir_ca,y_settat_ca | 4.0 | 1718.282954493602 |
| 0.5 | volvo_475 | Ball | y_benguerir_ca,y_settat_ca | 4.0 | 1718.282954493602 |
| 1.0 | eactros_600 | B1 | y_benguerir_ca | 4.0 | 1646.062954493602 |
| 1.0 | eactros_600 | B2 | y_benguerir_ca | 4.0 | 1646.062954493602 |
| 1.0 | eactros_600 | Ball | y_benguerir_ca | 4.0 | 1646.062954493602 |
| 1.0 | volvo_475 | B1 | y_settat_ca | 2.0 | 607.222954493602 |
| 1.0 | volvo_475 | B2 | y_benguerir_ca,y_settat_ca | 4.0 | 1729.965908987204 |
| 1.0 | volvo_475 | Ball | y_benguerir_ca,y_settat_ca | 4.0 | 1729.965908987204 |
| 2.0 | eactros_600 | B1 | nan | 0.0 | 0.0 |
| 2.0 | eactros_600 | B2 | y_benguerir_ca | 4.0 | 1657.745908987204 |
| 2.0 | eactros_600 | Ball | y_benguerir_ca | 4.0 | 1657.745908987204 |
| 2.0 | volvo_475 | B1 | nan | 0.0 | 0.0 |
| 2.0 | volvo_475 | B2 | y_settat_ca | 2.0 | 618.9059089872039 |
| 2.0 | volvo_475 | Ball | y_benguerir_ca,y_settat_ca | 4.0 | 1753.3318179744078 |

If site sets are unchanged across ratios, only secondary cost scales — feasibility-driven siting, not investment optimization.

## Distinctions (required)

1. **Minimum sites for modeled feasibility** — coverage under discrete MRLS + continuous replay gates.
2. **Budget-optimal under illustrative CAPEX** — B1/B2/Ball with CAPEX=100 units.
3. **Real-world investment recommendation** — **not established** without site costs, grid capacity, and observed demand.

## Data request (parallel, outside this freeze)

- SOTRAFRIQUE / operators: 10–30 anonymized refrigerated journeys (route, payload, times, trailer temperature, stops).
- ADM / utilities: HGV access certification and available power at candidate service areas.
- Measured TRU electrical load logs for Moroccan ambient conditions.

## Limitations

- Path-union of verified alternatives only — not full Moroccan network optimality.
- Discrete quantum / time grid ≠ continuous physics ≠ empirical validation.
- Petit Forestier/Centrale Danone remains a separate distribution-scale dossier case.
