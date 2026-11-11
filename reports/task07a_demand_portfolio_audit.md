# Task 07A — Demand portfolio audit

Access date: 2026-11-11  
Base commit reviewed: `09ac930`

## Defect in Task 06D `refrigerated_06d`

The portfolio in `configs/optimization/multiroute_placement_pilot.yaml` mixed:

- Casa→Agadir refrigeration **ON** (weight 2.0) and refrigeration **OFF** ablation (weight 1.5) as **independent demand**
- Casa→Marrakech **cool** and **hot** (weight 2.0 each) as simultaneous freight

Total illustrative weight **9.0**; served headline **7.5**. Ablation and weather twins inflated the planning denominator.

**Status:** retained as **HISTORICAL ONLY** (non-primary). Primary claims use `configs/optimization/multiroute_placement_07a.yaml`.

## Corrected primary portfolio `cold_chain_baseline_07a`

| Mission id | OD | Weight | Refrig | Weather | Init | Payload |
| --- | --- | ---: | --- | --- | --- | ---: |
| M_casa_marrakech | casa_marrakech | 2.0 | ON | cool | SOC 0.5 | 5300 kg |
| M_casa_agadir | casa_agadir | 2.0 | ON | cool | SOC 0.5 | 5300 kg |
| M_marrakech_agadir | marrakech_agadir | 1.5 | ON | cool | SOC 0.5 | 5300 kg |

**Fixed total demand weight = 5.5** for baseline, ablation, hot, and cool matched variants.

Matched scenarios (same IDs/weights; one factor changes):

- `cold_chain_no_refrigeration_ablation_07a` — refrigeration OFF
- `cold_chain_hot_07a` — weather hot
- `cold_chain_cool_07a` — weather cool (baseline alias)

## Provenance (honest)

| Field | Value | Class |
| --- | --- | --- |
| OD geometry | Path-union pilot Casa–Marrakech–Agadir | illustrative (not observed trip GPS) |
| Demand weights | 2.0 / 2.0 / 1.5 | illustrative research scenario — **not** observed annual Moroccan volumes |
| Cargo payload | 5300 kg | research assumption (fixed-payload primary) |
| Departure SOC | 0.5 | research dispatch policy |
| Setpoint | +2 °C | from `refrigeration_approx.yaml` |
| Config A TRU | tractor battery | declared research assumption |
| GCM | curb + trailer + payload | under manufacturer GCW; not legal HGV access certification |

## Reporting rules

Always report separately: total demand, served total, infeasible under candidate set, unresolved, serviceable coverage. Unserved missions are not “absent real-world demand.”
