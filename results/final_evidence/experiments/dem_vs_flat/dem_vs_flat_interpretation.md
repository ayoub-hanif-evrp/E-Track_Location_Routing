# DEM vs flat interpretation notes

## Comparison families

1. `fixed_short`: identical shortest-path mask; terrain-only effect.
2. `reoptimized_multi`: multi-route union; routing/charging may change with terrain.

Casa–Marrakech reoptimized distance differences (≈257 vs ≈236 km) are **route-selection**
effects under energy stress, not DEM geometry changes. Use the fixed-route table for
terrain-only traction deltas.

## Casa–Rabat coastal traction under DEM

comparison_family      od_id  soc_frac installed  ops_dem  ops_flat  road_km_dem  road_km_flat route_id_dem route_id_flat  same_route_geometry  min_soc_dem  min_soc_flat  traction_dem  traction_flat  regen_dem  regen_flat  net_battery_dem  net_battery_flat  charge_kwh_dem  charge_kwh_flat  charge_min_dem  charge_min_flat  delta_traction_kwh  delta_min_soc interpretation
      fixed_short casa_rabat       0.8               True      True    103.12364     103.12364 960e9d84c341  960e9d84c341                 True     0.586868      0.572441    125.820237     133.112356   1.363714         0.0       127.879495        136.535329             0.0              0.0             0.0              0.0           -7.292119       0.014426   terrain_only
reoptimized_multi casa_rabat       0.8               True      True    103.12364     103.12364 960e9d84c341  960e9d84c341                 True     0.586868      0.572441    125.820237     133.112356   1.363714         0.0       127.879495        136.535329             0.0              0.0             0.0              0.0           -7.292119       0.014426   terrain_only

If DEM traction is lower than flat on this short coastal OD, the likely physical
mechanism is **net downhill / regen-eligible grade segments** captured by DEM but
absent under flat (zero grade). Verify via regen credits and net battery columns;
if regen and net demand do not reconcile, treat as an accounting issue.

## Casa–Marrakech fixed-route note

At SOC 0.5, DEM makes the shortest path operationally infeasible (energy), so no terrain-only delta exists at that SOC.
At SOC 0.8 on the identical shortest route (b4ae4e7d047, 236.85 km): DEM traction − flat = +33.7 kWh (terrain-only).
Reoptimized multi at SOC 0.5 remains confounded (257.8 vs 236.9 km).
