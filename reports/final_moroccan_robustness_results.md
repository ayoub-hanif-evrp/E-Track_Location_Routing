# Final Moroccan robustness results

Baseline Ball sites: `y_benguerir_ac`
Distinct served site signatures in matrix: `{'y_benguerir_ac', 'y_settat_ac', 'y_benguerir_ac,y_settat_ac'}`

DEM: COPDEM GLO-30 DSM along OSM centerline — **not** surveyed pavement grade.
Chargers: hypothetical future HGV installations (Benguerir/Settat).
Replay label: `SIMULATION_REPLAY_VALIDATED` ≠ field validation.

| Scenario | Served | Sites | Reliability |
| --- | --- | --- | --- |
| B0_baseline_soc08_p5300_peak_q5 | True | y_benguerir_ac | PHYSICAL_SCENARIO_STABLE_WITHIN_TESTED_RANGE |
| F1_soc05_q5 | False |  | CONDITION_DEPENDENT |
| F1_soc05_q5_q2refine | False |  | CONDITION_DEPENDENT |
| F1_soc10_q5 | True | y_settat_ac | CONDITION_DEPENDENT |
| F1_soc10_q5_q2refine | True | y_benguerir_ac | PHYSICAL_SCENARIO_STABLE_WITHIN_TESTED_RANGE |
| F2_payload15t_q5 | False |  | CONDITION_DEPENDENT |
| F2_payload15t_q5_q2refine | False |  | CONDITION_DEPENDENT |
| F3_cont_power_q5 | True | y_benguerir_ac | PHYSICAL_SCENARIO_STABLE_WITHIN_TESTED_RANGE |
| F3_fixed_speed_q5 | False |  | CONDITION_DEPENDENT |
| F3_fixed_speed_q5_q2refine | False |  | CONDITION_DEPENDENT |
| F5_refrig_low_q5 | True | y_benguerir_ac | PHYSICAL_SCENARIO_STABLE_WITHIN_TESTED_RANGE |
| F5_refrig_summer_q5 | True | y_benguerir_ac | PHYSICAL_SCENARIO_STABLE_WITHIN_TESTED_RANGE |
| F6_charger_150kw_q5 | True | y_benguerir_ac | PHYSICAL_SCENARIO_STABLE_WITHIN_TESTED_RANGE |
| F6_none | False |  | CONDITION_DEPENDENT |
| F6_benguerir_only | True | y_benguerir_ac | PHYSICAL_SCENARIO_STABLE_WITHIN_TESTED_RANGE |
| F6_settat_only | False | y_settat_ac | CONDITION_DEPENDENT |
| F6_both | True | y_benguerir_ac,y_settat_ac | PHYSICAL_SCENARIO_STABLE_WITHIN_TESTED_RANGE |

## Interpretation

A site may be grid-stable on the baseline (q∈{5,2,1}, SOC 0.8, 5.3 t, peak-adapt) without being robust to dispatch SOC, payload, or speed policy.

Key negative / conditional results retained:
- Departure SOC 0.5 → unserved at q=5 and q=2.
- Departure SOC 1.0 → Ball prefers Settat at q=5 (Benguerir also optimal); q=2 refine returns Benguerir — **site identity is q- and SOC-dependent**.
- ~15 t payload → unserved under tested candidates.
- Fixed (non-adaptive) speed → unserved (peak/grade rejects).
- Settat-only availability → unserved; Benguerir-only → served.
- Refrigeration low/summer and 150 kW charger → Benguerir retained on baseline SOC/payload.

Benguerir is **not** a universally optimal Moroccan recommendation.

## Reproduction

```bash
python scripts/run_final_moroccan_robustness.py
```
