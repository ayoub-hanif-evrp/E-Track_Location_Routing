# DEM vs flat interpretation notes

## Comparison families

1. `fixed_short`: identical shortest-path mask; terrain-only effect when both traces exist.
2. `reoptimized_multi`: multi-route union; routing/charging may change with terrain.

Infeasible solutions without an OPTIMAL action trace use missing energy values
(not zeros). Feasibility differences are reported separately from energy deltas.

## Casa–Marrakech @ 50% SOC (authoritative three-outcome contrast)

comparison_family          od_id  soc_frac      installed status_dem status_flat  ops_dem  ops_flat feasibility_comparison  energy_comparable  road_km_dem  road_km_flat route_id_dem route_id_flat same_route_geometry  min_soc_dem  min_soc_flat  traction_dem  traction_flat  regen_dem  regen_flat  aux_dem  aux_flat  refrig_dem  refrig_flat  net_battery_dem  net_battery_flat  charge_kwh_dem  charge_kwh_flat  charge_min_dem  charge_min_flat  delta_traction_kwh  delta_min_soc                   interpretation
      fixed_short casa_marrakech       0.5 y_benguerir_ca INFEASIBLE     OPTIMAL    False      True    feasibility_differs              False          NaN    236.847742               ab4ae4e7d047                None          NaN      0.130572           NaN     211.813982        NaN         0.0      NaN  9.541192         NaN     0.301565              NaN        221.656739             NaN              0.0             NaN              0.0                 NaN            NaN feasibility_only_no_energy_delta
reoptimized_multi casa_marrakech       0.5 y_benguerir_ca    OPTIMAL     OPTIMAL     True      True          both_feasible               True   257.764907    236.847742 691ba1372de6  ab4ae4e7d047               False     0.114353      0.130572    313.556032     211.813982   5.626367         0.0 9.152561  9.541192     0.30575     0.301565       317.387977        221.656739            86.0              0.0            20.0              0.0           101.74205      -0.016219     confounded_route_and_terrain

Scientific reading (fixed route):
- Flat-road fixed route: feasible without charging (when ops_flat True / trace present).
- DEM-aware fixed route: infeasible (no OPTIMAL trace ⇒ no zero-energy claim).
- DEM-aware flexible/reoptimized route: may restore feasibility via Benguerir charging
  and/or route selection — see reoptimized family rows.
