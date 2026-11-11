# Task 07A — Refrigeration ON/OFF ablation (matched demand)

Config A (tractor battery → TRU) remains a **declared research assumption**. No empirical Volvo–TRU pairing claim.

## Design

- Placement: `cold_chain_baseline_07a` vs `cold_chain_no_refrigeration_ablation_07a` — **same** mission IDs, ODs, weights (total **5.5**), SOC 0.5, payload 5300 kg; only `refrigeration_on` flips.
- Routing: paired rows in `results/task07a_refrigerated_routing.csv` with continuous energy breakdown:
  - `E_traction_kwh`, `E_aux_drive_kwh`, `E_refrig_drive_kwh`, `E_regen_credit_kwh`
  - `E_aux_stationary_kwh`, `E_refrig_stationary_kwh`, `E_refrig_total_kwh`
  - charge energy/duration, `min_soc`, continuous replay status

## Measured example (q=10, Casa→Marrakech, cool, SOC 100%, no chargers)

| Vehicle | Refrig | E_refrig_total_kWh | E_traction_kWh | Discrete obj (¢) |
| --- | --- | ---: | ---: | ---: |
| eActros / Volvo | ON | ≈1.22 | ≈212–213 | 23685 |
| eActros / Volvo | OFF | 0 | ≈212–213 | 23685 |

TRU energy is observable while the discrete objective remains road-dominated (unchanged) in this cell. Hot Casa→Marrakech at SOC 0.5 shows larger TRU draw (e.g. ≈5.5 kWh on q=5 Volvo rows) and slightly higher objectives with chargers.

Hot weather is a **separate** portfolio (`cold_chain_hot_07a`), not extra demand inside the baseline.

## Limitations

UA/COP parameters assumed; door/infiltration = 0 in pilot; Config B out of scope.
