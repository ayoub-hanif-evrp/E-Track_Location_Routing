# PASS 2A — Northbound Moroccan benchmark

## Problem definition (honest)

**Primary Case A:** prospective battery-electric refrigerated agricultural freight from Agadir/Souss-Massa toward Casablanca / northern export logistics.

- Computational OD: `agadir_casa` labeled **`corridor_research_proxy`.
- Tanger Med evidence supports Souss-Massa agricultural export importance; it does **not** prove this OD is an observed refrigerated shipment terminating at Casablanca.
- Historical southbound Task 07/08 retained as secondary Case B (not mixed here).
- No double-counted Agadir→Marrakech leg.

## Network / DEM / chargers

- DEM: Copernicus GLO-30 sampled **independently** for `agadir_casa` macros (not reversed southbound arrays). Merged into `dem_sampling_meta.json`.
- Candidates: `settat_ac`, `benguerir_ac` only — hypothetical future truck sites.
- `amskroud_ac`: **unavailable / unresolved** — not fabricated.
- Path-union default `max_alts=2`; bounded sensitivity vs 4 alternatives below (DEM complete for both after merge sampling).

## Headline physical finding (do not overclaim)

Continuous shortest-path simulation on independently sampled northbound DEM macros hits **`peak_motor_power_exceeded`** under the assumed power packs (Volvo 400/400 kW assumed; eActros also INFEASIBLE on the same union). Chargers at Settat/Benguerir AC cannot bypass a DRIVE peak-power violation.

**Publishable:** discrete + continuous infeasibility under this assumed vehicle model, DEM path-union, tomato refrigeration pack, and two hypothetical northbound sites.  
**Not publishable:** “these trucks cannot haul tomatoes Agadir→Casablanca in Morocco.”  
**Not:** that missing `amskroud_ac` alone explains the failure (continuous already fails).

Input hashes refreshed at report generation; see CSVs for run provenance.

## Path-set sensitivity (Volvo 475, A80, q=10, no chargers)

| max_alts | dem | n_arcs | MRLS | served | note |
| ---: | --- | ---: | --- | --- | --- |
| 2 | True | 33 | INFEASIBLE | False | infeasible_under_assumed_power_and_path_union |
| 4 | True | 51 | INFEASIBLE | False | infeasible_under_assumed_power_and_path_union |

## Routing summary (q=10)


## Placement summary (enum ↔ B&B)

| Cell | Vehicle | Budget | Coverage | Sites | Agree | Status |
| --- | --- | --- | ---: | --- | --- | --- |
| A80 | volvo_475 | B0 | 0 |  | True | CERTIFIED_OPTIMAL |
| A80 | volvo_475 | B1 | 0 |  | True | CERTIFIED_OPTIMAL |
| A80 | volvo_475 | B2 | 0 |  | True | CERTIFIED_OPTIMAL |
| A80 | volvo_475 | Ball | 0 |  | True | CERTIFIED_OPTIMAL |
| A80 | eactros_600 | B0 | 0 |  | True | CERTIFIED_OPTIMAL |
| A80 | eactros_600 | B1 | 0 |  | True | CERTIFIED_OPTIMAL |
| A80 | eactros_600 | B2 | 0 |  | True | CERTIFIED_OPTIMAL |
| A80 | eactros_600 | Ball | 0 |  | True | CERTIFIED_OPTIMAL |
| A80 | volvo_460 | B0 | 0 |  | True | CERTIFIED_OPTIMAL |
| A80 | volvo_460 | B1 | 0 |  | True | CERTIFIED_OPTIMAL |
| A80 | volvo_460 | B2 | 0 |  | True | CERTIFIED_OPTIMAL |
| A80 | volvo_460 | Ball | 0 |  | True | CERTIFIED_OPTIMAL |
| A50 | volvo_475 | B0 | 0 |  | True | CERTIFIED_OPTIMAL |
| A50 | volvo_475 | B1 | 0 |  | True | CERTIFIED_OPTIMAL |
| A50 | volvo_475 | B2 | 0 |  | True | CERTIFIED_OPTIMAL |
| A50 | volvo_475 | Ball | 0 |  | True | CERTIFIED_OPTIMAL |
| A50 | eactros_600 | B0 | 0 |  | True | CERTIFIED_OPTIMAL |
| A50 | eactros_600 | B1 | 0 |  | True | CERTIFIED_OPTIMAL |
| A50 | eactros_600 | B2 | 0 |  | True | CERTIFIED_OPTIMAL |
| A50 | eactros_600 | Ball | 0 |  | True | CERTIFIED_OPTIMAL |
| AH80 | volvo_475 | B0 | 0 |  | True | CERTIFIED_OPTIMAL |
| AH80 | volvo_475 | B1 | 0 |  | True | CERTIFIED_OPTIMAL |
| AH80 | volvo_475 | B2 | 0 |  | True | CERTIFIED_OPTIMAL |
| AH80 | volvo_475 | Ball | 0 |  | True | CERTIFIED_OPTIMAL |
| AH80 | eactros_600 | B0 | 0 |  | True | CERTIFIED_OPTIMAL |
| AH80 | eactros_600 | B1 | 0 |  | True | CERTIFIED_OPTIMAL |
| AH80 | eactros_600 | B2 | 0 |  | True | CERTIFIED_OPTIMAL |
| AH80 | eactros_600 | Ball | 0 |  | True | CERTIFIED_OPTIMAL |

## Reproduction

```bash
python scripts/fetch_multiroute_dem.py --od-ids agadir_casa --merge-meta --max-alts 2
python scripts/run_pass2a_northbound_benchmark.py
```

CSVs: `results/pass2_northbound_routing.csv`, `results/pass2_northbound_placement.csv`.
