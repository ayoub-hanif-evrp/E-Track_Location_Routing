# Final numerical validation and scientific results report

Baseline package: commit `5d15aebe6056ad8deef580649e4c234d50ed44a6` + audit corrections  
Executable validation: **ALL_PASSED** (`validation/executable_validation_report.json`)  
Campaign packaging status: **COMPLETE**

## Validated findings

1. Dataset counts verified; primary 168-cell ladder preserved: eActros stressed **I0=9 / I1=11 / I2=12**.
2. **Elevation corrected (P0):** ordered path-specific DEM profiles. Casa→Agadir ≈445.6 km (not ~868 km bag-stitch). D-T05 / D-Figure 5 regenerated.
3. **Terrain separated (P1):** fixed-route terrain-only deltas vs confounded reoptimized routing. Casa–Marrakech 257 vs 236 km is route selection under energy stress.
4. **Casa–Rabat DEM traction −7.3 kWh** on identical geometry with regen and lower net battery demand → downhill/regen physics, not accounting error.
5. **Historical 15 t q-grid reproduced (P2):** Agadir→Casa / 80% / Benguerir AC: q=5 INF → q=2/1 OPT (multi & fixed). 5.3 t remains a separate family.
6. Fine-SOC transitions preserved (P3): Casa–Marrakech 10 t 0.50→0.52; Casa–Agadir 15 t 0.52→0.55; Casa–Agadir 5.3 t 0.45→0.50.
7. Volvo primary file usable **475 kWh** (`volvo_475`); usable460 is sensitivity-only.
8. **I3** (Benguerir CA+AC + Larache): eActros stressed **13/14** (+1 vs I2), common **14/14** (+1). Volvo stressed/common unchanged at 8/10.
9. Volvo Marrakech→Agadir @80%: energy OPTIMAL / ops INFEASIBLE by **`daily_driving_ok=False`** (HOS-in-search). Infra I0–I3 does not restore.
10. Volvo targeted infra: Benguerir CA alone still 0/7 failed ODs; **Settat+Larache** serves 2/7 (`casa_marrakech`, `rabat_tangier`).

## Conditional findings

- Fixed-route Casa–Marrakech DEM at SOC 0.5 is infeasible on the shortest path; terrain-only comparison uses SOC 0.8 on identical geometry (+33.7 kWh).
- Soft ~5 m DEM junction elevation jumps remain flagged; not used as physical grade breaks.
- Settat standard-budget LIMIT retained separately from escalate OPTIMAL (coverage tie 11/14 after escalate).

## Corrected figures/tables

- D-Figure 5 / D-T05 / DEM coverage & invalid audits
- R-T09 fixed vs reoptimized; R-T11 / R-Figure 10 (15 t family labeled)
- R-T05 (+ preserved transitions); R-T04 Settat escalate index; R-T02 vehicle files + I3 addendum
- R-Figure 2 executed routes; R-Figure 4 fine SOC; R-Figure 5 multipanel OD profiles
- R-T12 Volvo ops mechanism; Volvo targeted infra matrix
- SHA-256 release manifest: `manifests/release_manifest_sha256.json`

## Unresolved / deferred

- Manuscript writing deferred by design.

## Limitations

- Constructed OD missions; hypothetical ADM chargers.
- Single-duty HOS screen ≠ full Art.16 multi-day / 12 h daily-rest certification (24 h journey gate is a coarse out-of-scope screen only).
- I3 is an evaluated configuration, not proven global three-site optimality.
