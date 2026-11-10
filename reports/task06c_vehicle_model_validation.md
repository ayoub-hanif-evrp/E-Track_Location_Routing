# Task 06C — Vehicle model validation

Access date: 2026-11-10  
Base: `4dc6cd8` + 06C multi-vehicle pack

## What was validated

| Check | Result |
| --- | --- |
| Load eActros 600 YAML unchanged | pass (`usable_kwh=600`) |
| Load Volvo MA usable 475 | pass (`vehicle_id` …`usable475`) |
| Load Volvo global usable 460 | pass (separate YAML; not merged) |
| Discrete energy bounds from vehicle | `E_cap=floor_q(usable)`, `E_min=ceil_q(soc_min·usable)`, `E_init≤E_cap` |
| Reject `E_init > usable` | pass |
| CCS acceptance | `min(charger_kW, vehicle.ccs_max_charge_kw)` when set |
| DRIVE cache version | `06c.1` / preprocess `06c.1_multi_vehicle`; fingerprint includes vehicle id + usable scenario |
| Placement memo | vehicle / objective / tariff / terrain fields in key |
| GCM gate | missions above vehicle GCW limit skipped |
| Monetary convention | solver integers = cents; research comparison uses `road_cost_per_km=100` ¢/km |
| Certification taxonomy | probe `LIMIT_REACHED` / unresolved demand → never full-portfolio `CERTIFIED_OPTIMAL` |
| Config A refrigeration | labeled declared research assumption on both highway packs |
| Petit Forestier | dossier only — **no** physics YAML |

Unit entry point: `tests/unit/test_multi_vehicle_06c.py` (plus existing placement/certification suite).

## Energy derivation (locked production rule)

From loaded `VehicleParams`:

- `E_cap = floor_q(usable_kwh)`
- `E_min = ceil_q(soc_min × usable_kwh)`
- `E_init = floor_q(soc_init_frac × usable)` or explicit mission kWh ≤ usable

Non-divisible usable capacity vs quantum is floored/ceiled conservatively (documented in `battery_bounds.py` notes). Hard-coded `600/60` defaults removed from multi-route prep paths; pilot YAML uses `derive_energy_from_vehicle`.

## Charging honesty

- Pilot chargers remain illustrative 350 kW class.
- Volvo FH Electric advertises CCS ≤350 kW; effective power = `min(charger, vehicle_ccs_max)`.
- No SOC taper curve → constant acceptance × η until a curve exists.
- eActros without `ccs_max_charge_kw` keeps charger-limited power (legacy behaviour).

## Refrigeration honesty

Config A (tractor battery → TRU) remains a **declared research assumption** for eActros and Volvo highway packs. ePTO advertising is **not** treated as proof of a specific refrigerated trailer pairing. Config B Moroccan optimization is out of scope for 06C.

## What is not claimed

- Volvo FH Electric already operating in Moroccan refrigerated long-haul fleets
- Manufacturer-certified curb mass / CdA / η for Volvo research pack
- Continuous vs peak motor split beyond the mid-menu 400 kW assumed_variant_pick
- Petit Forestier 7.5 t as a substitute for 25/40 t highway GCM runs
- Market CAPEX/tariffs or certified HGV chargers at ADM sites
