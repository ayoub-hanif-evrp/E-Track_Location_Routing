# Task 06A — Discretization and feasibility validation

Date: 2026-11-09  
Primary CSV: `results/multiroute_numerical_sensitivity.csv` (class-default HGV cruise)  
Contrast CSV: `results/multiroute_numerical_sensitivity_osm_maxspeed.csv`

## Road-cost representation

Removed per-macro `max(1, round(km))` inflation. Costs use nonnegative `round(km × rate)` with optional largest-remainder path allocation (`allocate_path_road_costs`) so child macros can sum to the unsplit total. Units remain **illustrative currency**, not Moroccan market prices.

## Energy / time grid (class-default speeds)

Fixed physical graphs; quantums 10 / 5 / 2 kWh (plus 1 kWh on Casa→Marrakech full flat). Time step 5 min baseline; one contrast at 1 min.

| Mission | q=10 | q=5 | q=2 | Notes |
| --- | --- | --- | --- | --- |
| casa_marrakech_full_flat_nochg | OPTIMAL | OPTIMAL | OPTIMAL | Also OPTIMAL at q=1 (~196–229 s prep) |
| casa_marrakech_low_flat_chg | OPTIMAL | OPTIMAL | OPTIMAL | Continuous replay OK |
| casa_agadir_full_flat_nochg | OPTIMAL | OPTIMAL | OPTIMAL | Continuous DRIVE-only OK |
| casa_agadir_low_flat_chg | OPTIMAL | OPTIMAL | OPTIMAL | |
| casa_marrakech_full_dem_nochg | OPTIMAL | OPTIMAL | OPTIMAL | DEM complete |
| casa_marrakech_heavy_refrig_flat | OPTIMAL | OPTIMAL | OPTIMAL | |

Under the corrected class-default speed policy, **no discrete-only infeasibility** appears on these missions at q=10.

### Casa→Agadir full-battery no-charge (key audit)

Under Task 05C / OSM-maxspeed-as-cruise, this mission was MRLS `INFEASIBLE`.  
With class-default speeds + continuous Task 02B on the same macros: **physically feasible and discrete OPTIMAL** at q=10/5/2 (non-shortest ~484 km in the regenerated pilot).

Classification: prior infeasibility was **modelled-speed / representation driven**, not proof of real-world impossibility. Continuous and discrete now agree that a no-charge full-battery journey exists under the declared research cruise policy.

### OSM-maxspeed contrast (archived)

With `use_osm_maxspeed=true`, Casa→Agadir full no-charge stayed `physically_infeasible` at all grids (continuous DRIVE-only also failed). Casa→Agadir low+charge was **discrete_only_infeasible at q=10** but OPTIMAL at q=5/2 — classic quantization gap when the physical model is tighter.

## Computational limits

1 kWh DRIVE tables for Casa→Marrakech: ~3–4 minutes prep (acceptable). Finer grids on Casa→Agadir low+charge: solve up to ~30 s at q=2. No wall-time abort required under class-default policy.
