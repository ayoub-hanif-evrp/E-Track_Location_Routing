# Final numerical validation and scientific results report

Baseline package: commit `af60083` + freeze corrections  
Executable validation: **ALL_PASSED** (`validation/executable_validation_report.json`)  
Campaign packaging status: **COMPLETE**

## Validated findings

1. Authoritative **224-cell** I0–I3 panel (2×2×4×14). Directional installations: I0=0, I1=1 (`y_benguerir_ca`), I2=2 (+`y_larache_rt`), I3=3 (+`y_benguerir_ac`). Not a global optimum claim.
2. Coverage ladder: eActros stressed **9/11/12/13**; eActros common **11/12/13/14**; Volvo stressed **7/7/8/8**; Volvo common **8/9/10/10**.
3. **Elevation:** ordered path-specific DEM profiles. Casa→Agadir ≈445.6 km. Gain/loss/max grade exclude artificial junction jumps; missing DEM segments are not bridged.
4. **Terrain:** Casa–Marrakech @50% SOC: flat fixed feasible without charging; DEM fixed infeasible (missing energy values, not zeros); DEM flexible restores via Benguerir charging / route selection (`R-Figure9b`). Fixed-route DEM@80% identical geometry: +33.7 kWh traction.
5. Casa–Rabat DEM traction −7.3 kWh on identical geometry with regen → downhill/regen physics.
6. Historical 15 t q-grid reproduced: Agadir→Casa / 80% / Benguerir AC: q=5 INF → q=2/1 OPT.
7. Fine-SOC transitions preserved; Volvo primary usable **475 kWh**.
8. **Volvo Marrakech→Agadir @80%:** energy OPTIMAL (~266 min / ~283 km drive on energy trace; within 9 h daily screen) / ops INFEASIBLE with **no ops trace** ⇒ HOS fields not evaluated. Ablations: relaxing **continuous driving** restores ops; expanding rest nodes restores ops; relaxing **daily driving alone does not**. Prior daily-driving claim withdrawn.
9. **Volvo Settat CA+Larache vs Benguerir CA+Larache (full 14 ODs):** stressed **9 vs 8** (Settat enables `casa_marrakech`); common **9 vs 10** (Settat loses `casa_agadir`). Not uniformly dominant — report mission-level matrix.

## Conditional findings

- Soft ~5 m DEM junction elevation jumps remain flagged; excluded from grade stats.
- Some executed physics arcs lack densified DEM profiles; R-Fig5 advances distance with NaN elevation gaps and uses u/v waypoints on the map.
- Settat standard-budget LIMIT retained separately from escalate OPTIMAL.

## Limitations

- Constructed OD missions; hypothetical ADM chargers.
- Single-duty HOS screen ≠ full Art.16 multi-day / 12 h daily-rest certification.
- Evaluated infrastructure configurations are not proven minimum sets.
