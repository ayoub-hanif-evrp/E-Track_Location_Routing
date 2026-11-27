# Independent audit corrections — status

Baseline package commit: `af60083`  
Campaign status: **COMPLETE** (executable validation `ALL_PASSED`)

## Freeze corrections delivered

1. **P0 Volvo HOS:** Unevaluated `hos_ok` / `daily_driving_ok` are null/`NOT_EVALUATED` without an OPTIMAL ops trace. Marrakech→Agadir @80% binding mechanism (ablations): continuous-driving / qualifying-break eligibility — not Art.17 daily driving. Energy-only drive ≈266 min / ≈283 km.
2. **P1 I0–I3 panel:** 224 unique scenario keys; directional installation counts 0/1/2/3; ladder 9/11/12/13, 11/12/13/14, 7/7/8/8, 8/9/10/10. No global optimality claim.
3. **P2 Volvo Settat vs Benguerir:** Full 56-cell panel. Stressed 9 vs 8; common 9 vs 10. Mission-level matrix exported.
4. **P3 Terrain accounting:** Infeasible DEM@0.5 Casa–Marrakech uses missing energy (not zeros). Triptych `R-Figure9b`; R-Figure 9 comparable traces only.
5. **P4 Elevation:** Junction jumps excluded from gain/loss/grade; continuity investigation documented.
6. **P5 Figures:** R-Fig1/2/3 include I3; R-Fig5 executed-route distance axis (NaN DEM gaps where profiles missing).
7. **P6 Validation:** Manifest written last, excludes self; hashes verified; `ALL_PASSED`.

## Limitations

- Soft elevation junction jumps (~5 m) remain flagged.
- Single-duty HOS screen ≠ full multi-day Art.16 compliance.
- I3 / Settat+Larache are evaluated configurations, not proven minima.
