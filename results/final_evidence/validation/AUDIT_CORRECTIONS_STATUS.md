# Independent audit corrections — status

Baseline package commit: `5d15aebe6056ad8deef580649e4c234d50ed44a6`  
Campaign status: **COMPLETE**

## Validated findings (corrected)

1. **Elevation (P0):** D-Figure 5 / D-T05 now use path-ordered decision-arc DEM reconstruction. Casa→Agadir shortest profile length ≈445.6 km (was ~868 km from unsorted arc bags). Mean |length error| <1 km; shortest-path DEM coverage = 100% for all 18 ODs.
2. **Invalid DEM:** `fe603377792cc7cb` (`casa_oujda` edge-penalty alt only) — sampling skipped; not used on shortest-path D-T05 rows.
3. **Terrain (P1):** Fixed-route vs reoptimized families separated in R-T09. Casa–Marrakech 257 vs 236 km is route selection under energy stress, not DEM geometry. Fixed-route terrain-only deltas: Casa→Agadir +64.7 kWh; Casa→Marrakech @80% SOC +33.7 kWh; Rabat→Fès +51.3 kWh.
4. **Casa–Rabat DEM traction lower (−7.3 kWh):** same route; regen credit ≈1.36 kWh; **net battery demand also lower** → physical downhill/regen effect, not an accounting error.
5. **q-grid (P2):** Historical Agadir→Casa **15 t / 80% / Benguerir AC** reproduced: q=5 INFEASIBLE → q=2/1 OPTIMAL (multi and fixed). 5.3 t series retained as a separate family in R-T11 / R-Figure 10.
6. **Fine SOC (P3):** Preserved transitions documented in `R-T05_preserved_soc_transitions.csv`.
7. **Volvo naming (P3):** Primary vehicle is `volvo_fh_electric_4x2_540kwh.yaml` / usable **475 kWh** (`volvo_475`). usable460 is sensitivity-only.
8. **Volvo Marrakech→Agadir @80% (P4.2):** energy OPTIMAL but operational INFEASIBLE due to **`daily_driving_ok=False`** under HOS-in-search; infrastructure (I0–I3) does not restore ops serviceability. eActros contrast on I2 is operationally served.

## Conditional / in-flight

- I3 = Benguerir CA + Larache RT + Benguerir AC panel (running): early cells show Agadir→Casa becoming OPTIMAL under eActros stressed — northbound AC contribution under evaluation.
- Volvo targeted infrastructure alternatives (running).
- Executable validation gate (`executable_validation.py`) not yet all-green until I3/Volvo infra artifacts land and R-T09 fixed-family check passes.

## Corrected figures/tables

- D-Figure 5, D-Figure 5b, D-T05, `elevation_by_od_method.csv`, DEM coverage/invalid audits
- R-T09 (+ fixed / reoptimized splits), DEM interpretation notes
- R-T11, R-Figure 10 (historical 15 t labeled)
- R-T05 (+ preserved transitions), R-T04 Settat escalate index, R-T02 vehicle parameter files
- R-Figure 2 (executed routes), R-Figure 4 (fine SOC), R-Figure 5 multipanel per OD
- R-T12 Volvo ops mechanism table

## Unresolved / limitations

- Soft elevation junction jumps (~5 m) remain at some DEM arc seams (sampling densification), flagged in continuity notes.
- Single-duty HOS screen ≠ full multi-day Art.16 compliance; daily-driving failures must be read under the modeled policy.
- Dataset GIS maps D-Fig1/2/4 upgraded with projected continuous geometry, scale bars, and Benguerir entrance/exit inset.

## Do not claim COMPLETE

Mark COMPLETE only after `python scripts/final_evidence/executable_validation.py` reports `ALL_PASSED`.
