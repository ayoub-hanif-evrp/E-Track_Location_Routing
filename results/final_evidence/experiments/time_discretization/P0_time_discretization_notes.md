# P0 — Temporal discretization findings

Baseline: `518bc11a119c6f59ac2b11fa484d307d363336f6` / tag `evidence-freeze-518bc11`.

## Volvo Marrakech→Agadir @80% I2

            family vehicle_key            od_id  soc_frac      infra_config_id  time_step_min  deadline_steps  deadline_wall_h energy_status ops_status  operationally_served  energy_drive_min  drive_min_phys  sum_dt_phys_min  sum_dt_disc_min  n_drive_arcs  hos_max_continuous_steps  hos_max_continuous_min  phys_under_270_disc_over  family_b_ceil_exceeds_270  family_b_floor_exceeds_270  family_b_round_exceeds_270  family_b_ceil_sum_disc_min  family_b_floor_sum_disc_min  family_b_round_sum_disc_min  crep_ok  solve_sec hos_ok daily_driving_ok
A_global_time_grid   volvo_475 marrakech_agadir       0.8 I2_benguerir_larache              5             240             20.0       OPTIMAL INFEASIBLE                 False        265.615779             NaN       265.615779            285.0             5                        54                     270                      True                       True                       False                       False                         285                          265                          270     True   0.356650   None             None
A_global_time_grid   volvo_475 marrakech_agadir       0.8 I2_benguerir_larache              2             600             20.0       OPTIMAL    OPTIMAL                  True        265.615779      265.615779       265.615779            270.0             5                       135                     270                     False                      False                       False                       False                         270                          262                          266     True   0.360922   True             True
A_global_time_grid   volvo_475 marrakech_agadir       0.8 I2_benguerir_larache              1            1200             20.0       OPTIMAL    OPTIMAL                  True        265.615779      265.615779       265.615779            268.0             5                       270                     270                     False                      False                       False                       False                         268                          263                          266     True   0.360649   True             True

## Interpretation

If phys≤270 and disc>270 at ts=5, exclusion is **numerical ceil-inflation**
under HOS-in-search, not a physical continuous-driving exceedance.
Family A refinements (ts=2,1) may restore ops; label mixed-ts tables explicitly.

Casa–Tangier waiting: see `casa_tangier_wait_schedule_excerpt.csv`.
Do not claim waiting is legally mandatory unless the physical HOS audit requires it
independent of rounding.

See also `hos_policy_notes.md`.
