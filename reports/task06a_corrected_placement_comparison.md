# Task 06A — Corrected placement vs Task 05C

Date: 2026-11-09  
CSV: `results/task06a_placement_comparison.csv`  
Portfolio unchanged: three directional sites, four missions (`multiroute_placement_pilot.yaml`).

## Physics corrections affecting placement

- Per-edge class-default speeds in DRIVE tables.
- No fabricated `E_init`.
- Road costs without per-macro +1 inflation.
- Continuous replay certification unchanged in structure.

## Enum ↔ B&B (corrected model)

| Budget | Best sites | Coverage | Secondary | Status | Agree |
| --- | --- | --- | --- | --- | --- |
| B0 | NONE | 0.0 | 0.0 | CERTIFIED_OPTIMAL | yes |
| B1 | `y_settat_ca` | 5.0 | 307.043 | CERTIFIED_OPTIMAL | yes |
| B2 | `y_settat_ca` | 5.0 | 307.043 | CERTIFIED_OPTIMAL | yes |
| Ball | `y_settat_ca` | 5.0 | 307.043 | CERTIFIED_OPTIMAL | yes |

Serviceability unchanged qualitatively: Marrakech→Agadir low remains unserved; other three missions serviceable. Coverage weight 5.0.

## Delta vs Task 05C (`83c6f81`)

| Item | 05C | 06A |
| --- | --- | --- |
| Selected site (B1+) | `y_settat_ca` | **`y_settat_ca` (unchanged)** |
| Coverage | 5.0 | 5.0 |
| Secondary cost | ~331.99 | **~307.04** (road-cost + energy accounting under corrected speeds) |
| Enum↔B&B | agree | agree |
| Prunes | budget only (0 coverage/secondary) | same pattern on this tiny instance |

**Selected charging site does not change.** Operating costs shift under corrected physics. Small-portfolio B&B still shows no coverage/secondary pruning — correctness benchmark only, not speedup evidence.

## Regenerated pilot highlights

- `casa_marrakech_low_flat_chg`: non-shortest ~257.76 km, charge **190 kWh** at `settat_ca` (was 200 kWh).
- `casa_agadir_full_flat_nochg`: **OPTIMAL** no-charge (was INFEASIBLE under 05C fixed-graph / prior cruise misuse) — continuous replay OK.
- DEM + heavy/refrig Casa→Marrakech full: remain OPTIMAL.

## Remaining limitations

- Assumed class-default cruises ≠ measured HGV speeds.
- HGV access uncertified; Marrakech→Agadir low still unserved.
- Exactness only on the finite site set + path union + discrete grid.
- Placement B&B pruning power not demonstrated on this three-site instance.
