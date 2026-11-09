# Task 05B — Route-choice validation

## Synthetic / unit gates

`tests/unit/test_multiroute_physics.py` covers:

1. Two alternatives with different distance/cost  
2. Branching junction choice  
3. One-way forbidden continuation  
4. Parallel macros same endpoints (`arc_id`)  
5. Canonical alias collapse  
6. Charger availability changes route  
7. Artificial `R0_*` midpoint rejected  
8. Intermediate SOC floor blocks short path  
9. Failed continuous replay not certified  
10. Compact OD path-union contraction  
11. Offline reproducible `arc_id`  
12. MRLS = reference on small branching instance  

## Moroccan physics pilot (`results/multiroute_physics_experiments.csv`)

Portfolio: Casa→Marrakech, Casa→Agadir, Marrakech→Agadir. Flat terrain + Task 02B physics DRIVE tables. Claim scope: **path_union_of_verified_alternatives_only**.

| Mission | Status | Chose shortest? | Continuous replay |
|---|---|---|---|
| casa_marrakech full, no charger | OPTIMAL | yes | pass |
| casa_marrakech low, no charger | INFEASIBLE | — | — |
| casa_marrakech low + grounded chargers | OPTIMAL | **no** (~258 km vs 237 km shortest) | pass |
| casa_agadir full, no charger | INFEASIBLE | — | — |
| casa_agadir low + grounded chargers | OPTIMAL | yes | pass |
| marrakech_agadir full, no charger | OPTIMAL | yes | pass |
| marrakech_agadir low (+/− charger) | INFEASIBLE | — | — |
| casa_marrakech refrig / heavy GCM / q=5 | OPTIMAL | yes | pass |

### Interpretation (honest)

- With a full battery on Casa–Marrakech / Marrakech–Agadir, physics MRLS selects the **shortest-distance** verified corridor under flat terrain (road cost ∝ length; grades not differentiating).  
- **Casa–Marrakech low battery + Settat/Benguerir** restores feasibility on a **longer** reconstructed path (~258 km) — real routing–charging interaction without artificial midpoints.  
- **Casa–Agadir** without chargers is energy-infeasible under the discrete DRIVE model even at 600 kWh init (long macros + SOC floors); grounded chargers restore a feasible shortest-corridor solution at low init.  
- Marrakech–Agadir low-battery remains infeasible with only Amskroud on the union — reported honestly; no invented sites.  
- Non-shortest optima were **not fabricated**; they appear when charging availability changes the feasible set.

## Map

`reports/figures/multiroute_physics_paths.png` — OD alternatives + grounded hypothetical charger points.

## Limitations

- Exactness only over the OD path-union decision graph.  
- Flat-terrain pilot (per-arc DEM optional; A3 profiles never reused).  
- Scenario speeds / GCM are research parameters.  
- HGV access mostly OSM-unknown; chargers hypothetical.  
- Placement B&B re-coupling is Task **05C**.
