# Task 06C — eActros vs Volvo FH Electric identical-mission comparison

Access date: 2026-11-10  
Artifacts: `results/task06c_vehicle_comparison.csv` (156 rows), `results/task06c_vehicle_placement.csv` (24 rows)  
Convention: solver integers = **cents**; `road_cost_per_km = 100` ¢/km (= 1 currency unit/km at `cents_to_currency=0.01`).  
Claim scope: **prospective** Volvo highway pack vs eActros comparator on path-union pilots — **not** verified Moroccan long-haul fleet operation.

## Headline question

**Does Volvo change selected sites and/or serviceable refrigerated mission count vs eActros?**

**Yes on both axes (under this research pack):**

1. **Placement sites change.** On the default multi-route portfolio (q=10, both objective modes), eActros optima install **Settat only** (`y_settat_ca`) for B1/B2/Ball at coverage weight 5.0. Volvo 475 and 460 need **Settat + Benguerir** for B2/Ball to reach coverage 5.0; under B1 (Settat only) Volvo coverage stalls at **3.0**.
2. **Longer no-charge missions lose serviceability.** Casa→Agadir at full initial SOC without en-route charge is **OPTIMAL** for eActros (`E_cap=600`) and **INFEASIBLE** for Volvo 475 (`E_cap=470`) and 460 (`E_cap=460`).
3. **Refrigerated Casa→Marrakech with chargers remains serviceable** for all three vehicles (Config A = declared assumption); Volvo discrete objectives are higher than eActros on the same install set.

Petit Forestier ~7.5 t is **not** in these runs (urban dossier only).

---

## Routing matrix (bounded)

Vehicles: eActros 600; Volvo usable_ma_475; Volvo usable_global_460.  
ODs: Casa→Marrakech, Casa→Agadir, Marrakech→Agadir.  
GCM: light (25 t) baseline; heavy (40 t) limited to q=10 en-route full/refrig cells.  
Installs: none / Settat / Settat+Benguerir / all direction-compatible (full install fan-out on q=10 en-route light).  
Objectives: `enroute_incremental_cost` and `energy_replenishment_cost`.  
q: 10 baseline + 5 sensitivity. Runner: `scripts/run_task06c_vehicle_comparison.py`.

| vehicle_key | OPTIMAL | INFEASIBLE |
| --- | ---: | ---: |
| eactros_600 | 25 | 27 |
| volvo_475 | 18 | 34 |
| volvo_460 | 18 | 34 |

All **61** OPTIMAL rows passed continuous physics replay (`continuous_replay_ok=True`).

### q=10 · en-route · light · none vs all_compatible

| vehicle | mission | none | all_compatible (obj ¢) |
| --- | --- | --- | ---: |
| eactros | casa_marrakech_full_nochg | OPTIMAL | — (23685 at none) |
| volvo_475 / 460 | casa_marrakech_full_nochg | OPTIMAL | — (23685 at none) |
| eactros | casa_marrakech_low_chg | INFEASIBLE | OPTIMAL 29777 |
| volvo_475 / 460 | casa_marrakech_low_chg | INFEASIBLE | OPTIMAL 31677 |
| eactros | casa_marrakech_refrig_chg | INFEASIBLE | OPTIMAL 27897 |
| volvo_475 / 460 | casa_marrakech_refrig_chg | INFEASIBLE | OPTIMAL 29577 |
| eactros | casa_agadir_full_nochg | OPTIMAL 48446 | — |
| volvo_475 / 460 | casa_agadir_full_nochg | **INFEASIBLE** | — |
| eactros | casa_agadir_low_chg | INFEASIBLE | OPTIMAL 54462 |
| volvo_475 / 460 | casa_agadir_low_chg | INFEASIBLE | **INFEASIBLE** |
| all | marrakech_agadir_low_chg | INFEASIBLE | INFEASIBLE |

Interpretation: smaller usable packs make Casa→Agadir energy-tight even at full SOC without charge, and low-init Casa→Agadir remains infeasible for Volvo even with all compatible ADM sites under the 200 kWh init used here. Marrakech→Agadir at 200 kWh init is infeasible for **all** vehicles in this matrix (direction/site coverage limitation, not Volvo-only).

Usable 475 vs 460: **identical** serviceability pattern and objectives on the shared OPTIMAL cells in this grid (quantum flooring already equalizes many discrete caps: 470 vs 460 kWh).

---

## Placement portfolio (enum ≡ B&B)

Demand: `multiroute_placement_pilot` default; q=10; `road_cost_per_km=100` ¢/km; unresolved demand weight = 0 on all reported rows → full-portfolio `CERTIFIED_OPTIMAL` is allowed (taxonomy downgrade not triggered).

| vehicle | B0 cov | B1 sites / cov | B2 / Ball sites / cov |
| --- | ---: | --- | --- |
| eactros_600 | 0.0 | `y_settat_ca` / 5.0 | `y_settat_ca` / 5.0 |
| volvo_475 | 1.0 | `y_settat_ca` / 3.0 | `y_benguerir_ca,y_settat_ca` / 5.0 |
| volvo_460 | 1.0 | `y_settat_ca` / 3.0 | `y_benguerir_ca,y_settat_ca` / 5.0 |

Enum and B&B agree on every budget × vehicle × objective mode (`enum_agreement=True`). Both objective modes select the same site sets for each vehicle.

---

## Integrity / honesty notes carried into 06C

- No false full-portfolio certification when probe missions are unresolved (`UNRESOLVED_SERVICEABILITY` / `CONDITIONAL_RESTRICTED_PORTFOLIO`).
- Energy bounds derived from vehicle usable kWh; eActros YAML pack retained as comparator.
- CCS acceptance capped at vehicle CCS max when declared (Volvo ≤350 kW).
- Config A refrigeration = declared research assumption for both highway packs.
- FE Electric and FH Aero Extended Range / MCS excluded from this pack.

## Not claimed

- Market tariffs or CAPEX; certified HGV access at ADM sites.
- Volvo FH Electric already deployed in Moroccan refrigerated long-haul fleets.
- Measured Volvo curb / CdA / η; continuous vs peak OEM split beyond mid-menu 400 kW assumption.
- Nationwide optimality or Config B Moroccan optimization.
