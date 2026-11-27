# Executed-route geometry and DEM audit (P1)

Reconstruction uses solver macros (`macros_by_arc_id`) with the same DEM policy as physics:
child profile → parent-slice → dem_unavailable.

## Summary

           od_id vehicle_key                      infra_config_id  n_drive_arcs  route_length_m  geometry_coverage_frac  elevation_dem_coverage_frac  n_missing_geometry  n_dem_per_arc  n_dem_parent_slice  n_dem_unavailable  solver_flat_fallback_arcs
agadir_marrakech eactros_600                              I0_none             3   249061.947966                     1.0                          1.0                   0              3                   0                  0                          0
  marrakech_casa eactros_600                              I0_none             7   223002.210341                     1.0                          1.0                   0              4                   3                  0                          0
    tangier_casa eactros_600                              I0_none            19   361483.158879                     1.0                          1.0                   0             15                   4                  0                          0
      casa_rabat eactros_600                              I0_none             8   103123.640360                     1.0                          1.0                   0              6                   2                  0                          0
      rabat_casa eactros_600                              I0_none             7   116407.629188                     1.0                          1.0                   0              5                   2                  0                          0
       rabat_fes eactros_600                              I0_none             9   206372.704592                     1.0                          1.0                   0              9                   0                  0                          0
       fes_rabat eactros_600                              I0_none            11   204007.084196                     1.0                          1.0                   0             11                   0                  0                          0
   tangier_rabat eactros_600                              I0_none            18   246799.589550                     1.0                          1.0                   0             16                   2                  0                          0
   rabat_tangier eactros_600                              I0_none            12   247211.126724                     1.0                          1.0                   0             10                   2                  0                          0
  casa_marrakech eactros_600                      I1_benguerir_ca             7   257764.907361                     1.0                          1.0                   0              4                   3                  0                          0
     casa_agadir eactros_600                      I1_benguerir_ca            10   445616.138357                     1.0                          1.0                   0              5                   5                  0                          0
agadir_marrakech eactros_600                      I1_benguerir_ca             3   249061.947966                     1.0                          1.0                   0              3                   0                  0                          0
  marrakech_casa eactros_600                      I1_benguerir_ca             7   223002.210341                     1.0                          1.0                   0              4                   3                  0                          0
    tangier_casa eactros_600                      I1_benguerir_ca            19   361483.158879                     1.0                          1.0                   0             15                   4                  0                          0
      casa_rabat eactros_600                      I1_benguerir_ca             8   103123.640360                     1.0                          1.0                   0              6                   2                  0                          0
      rabat_casa eactros_600                      I1_benguerir_ca             7   116407.629188                     1.0                          1.0                   0              5                   2                  0                          0
       rabat_fes eactros_600                      I1_benguerir_ca             9   206372.704592                     1.0                          1.0                   0              9                   0                  0                          0
       fes_rabat eactros_600                      I1_benguerir_ca            11   204007.084196                     1.0                          1.0                   0             11                   0                  0                          0
   tangier_rabat eactros_600                      I1_benguerir_ca            18   246799.589550                     1.0                          1.0                   0             16                   2                  0                          0
   rabat_tangier eactros_600                      I1_benguerir_ca            12   247211.126724                     1.0                          1.0                   0             10                   2                  0                          0
  casa_marrakech eactros_600                 I2_benguerir_larache             7   257764.907361                     1.0                          1.0                   0              4                   3                  0                          0
     casa_agadir eactros_600                 I2_benguerir_larache            10   445616.138357                     1.0                          1.0                   0              5                   5                  0                          0
agadir_marrakech eactros_600                 I2_benguerir_larache             3   249061.947966                     1.0                          1.0                   0              3                   0                  0                          0
  marrakech_casa eactros_600                 I2_benguerir_larache             7   223002.210341                     1.0                          1.0                   0              4                   3                  0                          0
    tangier_casa eactros_600                 I2_benguerir_larache            19   361483.158879                     1.0                          1.0                   0             15                   4                  0                          0
    casa_tangier eactros_600                 I2_benguerir_larache            15   348124.947958                     1.0                          1.0                   0             11                   4                  0                          0
      casa_rabat eactros_600                 I2_benguerir_larache             8   103123.640360                     1.0                          1.0                   0              6                   2                  0                          0
      rabat_casa eactros_600                 I2_benguerir_larache             7   116407.629188                     1.0                          1.0                   0              5                   2                  0                          0
       rabat_fes eactros_600                 I2_benguerir_larache             9   206372.704592                     1.0                          1.0                   0              9                   0                  0                          0
       fes_rabat eactros_600                 I2_benguerir_larache            11   204007.084196                     1.0                          1.0                   0             11                   0                  0                          0
   tangier_rabat eactros_600                 I2_benguerir_larache            18   246799.589550                     1.0                          1.0                   0             16                   2                  0                          0
   rabat_tangier eactros_600                 I2_benguerir_larache            12   247211.126724                     1.0                          1.0                   0             10                   2                  0                          0
  casa_marrakech eactros_600 I3_benguerir_ca_larache_benguerir_ac             7   257764.907361                     1.0                          1.0                   0              4                   3                  0                          0
     casa_agadir eactros_600 I3_benguerir_ca_larache_benguerir_ac            10   445616.138357                     1.0                          1.0                   0              5                   5                  0                          0
     agadir_casa eactros_600 I3_benguerir_ca_larache_benguerir_ac             7   429153.163023                     1.0                          1.0                   0              4                   3                  0                          0
agadir_marrakech eactros_600 I3_benguerir_ca_larache_benguerir_ac             3   249061.947966                     1.0                          1.0                   0              3                   0                  0                          0
  marrakech_casa eactros_600 I3_benguerir_ca_larache_benguerir_ac             7   223002.210341                     1.0                          1.0                   0              4                   3                  0                          0
    tangier_casa eactros_600 I3_benguerir_ca_larache_benguerir_ac            19   361483.158879                     1.0                          1.0                   0             15                   4                  0                          0
    casa_tangier eactros_600 I3_benguerir_ca_larache_benguerir_ac            15   348124.947958                     1.0                          1.0                   0             11                   4                  0                          0
      casa_rabat eactros_600 I3_benguerir_ca_larache_benguerir_ac             8   103123.640360                     1.0                          1.0                   0              6                   2                  0                          0
      rabat_casa eactros_600 I3_benguerir_ca_larache_benguerir_ac             7   116407.629188                     1.0                          1.0                   0              5                   2                  0                          0
       rabat_fes eactros_600 I3_benguerir_ca_larache_benguerir_ac             9   206372.704592                     1.0                          1.0                   0              9                   0                  0                          0
       fes_rabat eactros_600 I3_benguerir_ca_larache_benguerir_ac            11   204007.084196                     1.0                          1.0                   0             11                   0                  0                          0
   tangier_rabat eactros_600 I3_benguerir_ca_larache_benguerir_ac            18   246799.589550                     1.0                          1.0                   0             16                   2                  0                          0
   rabat_tangier eactros_600 I3_benguerir_ca_larache_benguerir_ac            12   247211.126724                     1.0                          1.0                   0             10                   2                  0                          0

## Interpretation

- If `n_dem_parent_slice > 0` and `solver_flat_fallback_arcs == 0`, missing child JSON files
  are a **visualization** issue; physics already used parent DEM slices.
- If `solver_flat_fallback_arcs > 0`, terrain entered the solver as flat fallback —
  affected missions may need selective re-runs after DEM repair.

## Campaign result (45 missions)

- Plotted eActros stressed operational panel (R-Fig2 served): **45** audited here.
- `geometry_coverage_frac = 1.0` and `elevation_dem_coverage_frac = 1.0` for all audited missions.
- `n_dem_parent_slice` total = 95; `n_dem_unavailable` = 0; `solver_flat_fallback_arcs` = 0.
- Steep-grade arc `343a5225681579e5`: see `P1_steep_gradient_343a5225681579e5.md` and `P3_executed_route_geometry_notes.md`.
