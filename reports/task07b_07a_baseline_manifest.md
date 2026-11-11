# Task 07B Stage 1 — Task 07A baseline manifest

Machine-readable: `results/task07b_07a_manifest.json`  
Reviewed commit: `f18711c19552e1c2850be897b7a085008d853844`  
Access date: 2026-11-11

## Locked comparison equality

eActros 600 and Volvo FH Electric (475 / 460 usable) share the same Task 07A freight definition:

- Fixed cargo payload **5300 kg** (vehicle-specific GCM)
- Departure SOC **0.5**
- Refrigeration **ON**, Config **A**, setpoint +2 °C
- Cool weather, **flat** terrain (07A primary)
- Demand `cold_chain_baseline_07a`, total weight **5.5**
- Hypothetical 350 kW southbound sites; road cost 100 ¢/km
- q=10 primary / q=5 sensitivity; Δt=5 min; deadline 240 steps (20 h)

## Headline retained for stress-testing (not a Moroccan install recommendation)

| Vehicle | One site | Two sites |
| --- | --- | --- |
| eActros | Settat **or** Benguerir (tie), cov 4.0 | still 4.0 |
| Volvo 475/460 | Settat, cov 2.0 | Settat+Benguerir, cov 4.0 |

Marrakech→Agadir weight 1.5 unserved under all candidates → max cov 4.0 / 5.5.

## Hashes (sha256 prefix)

See JSON manifest for vehicle YAMLs, refrigeration YAML, placement/pilot configs, path alternatives, decision graph.

## Policy

Task 07A CSVs are **preserved** (not silently rewritten). Task 07B writes new `task07b_*` artifacts only.
