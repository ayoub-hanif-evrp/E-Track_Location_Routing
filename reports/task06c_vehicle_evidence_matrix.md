# Task 06C — Vehicle evidence matrix

Access date: 2026-11-10  
Reviewed HEAD base: `4dc6cd8`

## Scientific roles (locked)

| Role | Vehicle | Claim allowed |
| --- | --- | --- |
| Primary **prospective** highway scenario | Volvo FH Electric 4×2 tractor | Product on Volvo Trucks Morocco site; **not** verified in Moroccan refrigerated long-haul fleets |
| Comparator | Mercedes-Benz eActros 600 | Existing manufacturer pack; Moroccan long-haul deployment **not** verified |
| Real Moroccan cold-chain EV | Petit Forestier / Centrale Danone ~7.5 t | Confirmed Moroccan urban/peri-urban operation — **not** a 40 t tractor |

**Excluded / not to be mixed**

- Volvo FE Electric (Arma Rabat waste collection, 2023) ≠ FH Electric.
- Volvo FH Aero Electric Extended Range / MCS / ~725 kWh usable ≠ FH Electric research pack.

---

## Sources

| ID | URL | Role |
| --- | --- | --- |
| MA | https://www.volvotrucks.ma/fr-ma/trucks/electric/volvo-fh-electric.html | Moroccan market FH Electric page |
| GL | https://www.volvotrucks.com/en-en/trucks/electric/volvo-fh-electric.html | Global FH Electric page |
| PR2026 | https://www.volvotrucks.com/en-en/news-stories/press-releases/2026/apr/volvo-launches-new-electric-trucks---with-ranges-up-to-700-km.html | 2026 new generation — **different product line**; consulted only to exclude |
| PF | https://www.petitforestier.com/fr-ma/posts/270_petit-forestier-met-en-circulation-le-premier-poids-lourd-frigorifique-100-electrique-au-maroc | Petit Forestier Morocco launch |
| H24 | https://h24info.ma/paroles-dexpertss/paroles-dexperts-de-faical-tadlaoui-petit-forestier-electrise-le-transport-frigorifique-au-maroc/ | Interview technical figures |

---

## Volvo FH Electric — parameter matrix (4×2 tractor research identity)

Primary modeled identity: `volvo_fh_electric_4x2_540kwh` (6-battery / up to 540 kWh installed menu point).

| Parameter | Value used in 06C | Evidence class | Source | Notes |
| --- | --- | --- | --- | --- |
| Manufacturer / model | Volvo Trucks / FH Electric | confirmed | MA, GL | |
| Axles | 4×2 tractor | confirmed (menu) | MA, GL | Also lists 6×2/6×4; we lock 4×2 |
| Battery packs | 4–6; research = 6 | confirmed (range) | MA, GL | Installed 360–540 kWh |
| Installed energy | 540 kWh | confirmed (ceiling) | MA, GL | |
| Usable energy (MA) | **475 kWh** | confirmed_conflict | MA | Scenario `usable_ma_475` |
| Usable energy (global) | **460 kWh** | confirmed_conflict | GL | Scenario `usable_global_460` — **not merged** with 475 |
| CCS charge power | ≤350 kW, &lt;750 V | confirmed (advertised) | MA, GL | Not a full SOC curve |
| Charge time claim | ~65 min 20%→80% at 350 kW | confirmed (advertised) | MA, GL | |
| GCW | up to 65 t | confirmed (advertised) | MA, GL | Research GCM 25/40 t under this limit |
| Driveline performance menu | 300 / 350 / 400 / 470 / 540 kW | confirmed_menu | MA, GL | Continuous vs peak **not** distinguished |
| Selected driveline | **400 kW** as both continuous and peak | **assumed_variant_pick** | — | Mid-menu; not copied from eActros |
| Peak regen | = 400 kW | assumed | — | Bound + sensitivity |
| Range claim | up to 470 km | confirmed (advertised) | MA, GL | Not used as model input |
| Unladen tractor mass | **12 000 kg** research bound | assumed | — | **Not** manufacturer-certified; sensitivity [11 000, 13 500]; **never** labeled as Volvo OEM mass |
| Trailer curb | 8 000 kg | assumed | — | Same honesty class as eActros pack |
| CdA | 6.5 m² | assumed | — | Research long-haul tractor–trailer |
| Crr | 0.007 | literature/assumed | — | |
| η_prop / η_regen | 0.90 / 0.70 | assumed | — | |
| P_aux | 2 500 W | assumed | — | |
| soc_min | 0.10 | assumed | — | Operating floor |
| ePTO | advertised 30/60/90 kW levels | confirmed (menu) | MA, GL | |
| Electric TRU / Config A | tractor battery supplies TRU | **unresolved_compatibility** | — | Declared research assumption; ePTO ≠ proven trailer pairing |
| MCS / Aero Extended Range | excluded | n/a | PR2026 | Different product |

### Unresolved-parameter policy

1. **Usable capacity conflict:** always run **two labeled scenarios** (475 and 460); never average or pick silently.
2. **Continuous vs peak power:** until Volvo publishes a split, selected menu kW is applied to both continuous and peak with class `assumed_variant_pick`; sensitivity at neighboring menu levels if peak-motor binds.
3. **Tractor curb mass:** engineering assumption with stated range; never copy eActros 11.7 t as “Volvo manufacturer data”.
4. **Charging taper:** constant acceptance `min(charger_kW, vehicle_ccs_max_kW)` × η until a curve exists; optional reduced-acceptance sensitivity.
5. If a comparison requires a parameter with no defensible bound → **blocker** (stop that cell as `unresolved_inputs`), do not invent OEM numbers.

---

## Mercedes-Benz eActros 600 (comparator — unchanged pack)

See `configs/vehicles/eactros_600.yaml`. Retained as historical comparator. Moroccan long-haul refrigerated fleet operation: **not verified**.

---

## What 06C will and will not claim

**Will support:** prospective B&B–MRLS infrastructure/routing differences under manufacturer-published FH Electric capacity/charge menus vs eActros, with assumed aero/mass/efficiency clearly labeled.

**Will not support:** “Volvo FH Electric already operates Moroccan cold-chain highway fleets”; FE Electric ≡ FH; mixing Aero Extended Range; empirical validation without measured trip data; Config B Moroccan optimization in this milestone.
