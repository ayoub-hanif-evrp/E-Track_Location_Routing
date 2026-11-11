# Task 06D — Refrigerated freight sensitivity

Config A (tractor battery → TRU) remains a **declared research assumption** for eActros and Volvo highway packs. ePTO advertising ≠ proven trailer pairing. Petit Forestier 7.5 t is **not** in these runs.

## Routing (fair matrix excerpts)

Portfolio cells with `refrigeration_on=true` under corrected GCM:

- Casa→Marrakech refrig + chargers, equal SOC 100%, fixed GCM 25 t: **all three vehicles OPTIMAL** (road-dominated; 0 recorded en-route charge in the all_compatible cell).
- Casa→Agadir refrig, equal SOC 50%, fixed GCM 25 t: requires chargers for all three; all OPTIMAL with `all_compatible`.
- Hot vs cool Casa→Marrakech refrig (equal SOC 100%, fixed_gcm light): both weather labels remain serviceable for the three packs in the bounded matrix (see CSV `weather_id`).

Ablation (refrigeration off vs on) is embedded in the placement portfolio (`M_casa_agadir_ablation_off`).

Routing ablation at equal SOC 50%, fixed GCM 25 t, Casa→Agadir with `all_compatible`: refrigeration on vs off produced **identical** discrete objectives and charge kWh in this cool-weather flat cell for each vehicle (eActros 52362 ¢ / 370 kWh; Volvo 53842 ¢ / 440 kWh). That does **not** mean refrigeration is free in general — only that it did not bind the selected discrete plan under these research assumptions.

## Placement portfolio `refrigerated_06d`

Missions (all equal departure SOC 0.5 except absolute legacy default portfolio):

| ID | OD | Refrig | Weather | Weight |
| --- | --- | --- | --- | ---: |
| M_casa_marrakech_refrig_cool | Casa→Marrakech | on | cool | 2.0 |
| M_casa_marrakech_refrig_hot | Casa→Marrakech | on | hot | 2.0 |
| M_casa_agadir_refrig_cool | Casa→Agadir | on | cool | 2.0 |
| M_casa_agadir_ablation_off | Casa→Agadir | **off** | cool | 1.5 |
| M_marrakech_agadir_refrig_cool | Marrakech→Agadir | on | cool | 1.5 |

All-sites probe: Marrakech→Agadir remains `unserved_all_candidates` for the tested vehicles at SOC 0.5 (not unresolved/limit). Served weight denominator excludes that structural unserved OD from “serviceable” coverage but keeps full demand weight separate in context fields.

## Effect on infrastructure choice

See `task06d_corrected_placement.md`. Refrigeration-first demand **changes** which single site eActros prefers relative to the legacy mostly-dry portfolio, and Volvo still needs a second site to match max coverage.
