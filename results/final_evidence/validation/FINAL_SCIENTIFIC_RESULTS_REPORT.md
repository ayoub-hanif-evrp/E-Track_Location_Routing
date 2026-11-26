# Final numerical validation and scientific results report

Baseline commit: `8b0cbf716cc342550299895d4da58889b8239d37`

Authoritative package: `results/final_evidence/`

## Strongest supported findings

1. Dataset headline counts independently verified.
2. eActros stressed infrastructure ladder reproduced: I0=9/14, I1=11/14, I2=12/14 (0 LIMIT).
3. Common 80% SOC raises eActros coverage (11/12/13); infrastructure gains partly SOC-dependent.
4. Volvo on eActros-selected sites: stressed 7/7/8 — Benguerir CA alone gives no Volvo gain.
5. Settat vs Benguerir: coverage tie at 11/14 after escalate; Benguerir 65 min vs Settat 120 min stationary.
6. `agadir_casa` failure under I2 is directional (Benguerir AC restores); `marrakech_agadir`@50% is SOC/energy.
7. DEM increases traction ~50–100 kWh on long corridors; refrigeration ~0.1% of traction+aux at 9°C tomato.
8. Fine SOC brackets: Casa→Marrakech 10 t flips INF→OPT between 0.50 and 0.52 SOC (I1); Casa→Agadir 15 t between 0.52 and 0.55.
9. Headline robustness (5.3 t): Casa→Marrakech and Casa→Agadir remain OPTIMAL across fridge/sensitivity/adverse packs under I1; Casa→Tangier requires I2 (Larache) — all 15 I2 variants OPTIMAL.
10. Fixed vs flexible routing: multi-route restores Casa→Marrakech under I1/I2 where fixed/short can fail; Tangier needs I2 regardless of route mode.

## Primary coverage table

| vehicle_key | soc_scenario | infra_config_id | ops_served | n_missions |
|-------------|--------------|-----------------|------------|------------|
| eactros_600 | stressed_mixed | I0_none | 9 | 14 |
| eactros_600 | stressed_mixed | I1_benguerir_ca | 11 | 14 |
| eactros_600 | stressed_mixed | I2_benguerir_larache | 12 | 14 |
| eactros_600 | common_soc_80 | I0_none | 11 | 14 |
| eactros_600 | common_soc_80 | I1_benguerir_ca | 12 | 14 |
| eactros_600 | common_soc_80 | I2_benguerir_larache | 13 | 14 |
| volvo_475 | stressed_mixed | I0_none | 7 | 14 |
| volvo_475 | stressed_mixed | I1_benguerir_ca | 7 | 14 |
| volvo_475 | stressed_mixed | I2_benguerir_larache | 8 | 14 |
| volvo_475 | common_soc_80 | I0_none | 8 | 14 |
| volvo_475 | common_soc_80 | I1_benguerir_ca | 9 | 14 |
| volvo_475 | common_soc_80 | I2_benguerir_larache | 10 | 14 |

## Conditional findings

- q=1 can hit LIMIT (computational), not model infeasibility.
- Historical q=5 INF / q=2 OPT pattern not reproduced under current matched Agadir→Casa setups.
- Payload–SOC brackets are tested points only (no interpolated thresholds).
- Tangier corridor is infrastructure-gated by Larache (I2), not by refrigeration/sensitivity within the tested packs.

## Negative / unexpected

- Amskroud on Marrakech→Agadir union does not restore feasibility at 50% SOC.
- HGV tags unknown throughout expanded network.
- Fixed/short route masks can lose missions that multi-route recovers (Casa→Marrakech I1/I2).

## Limitations

- Constructed OD missions, not observed freight trips.
- Hypothetical chargers at ADM service areas.
- Single-duty HOS screen only (no multi-day Art.16).
- Robustness headline uses I1 for Casa→Marrakech/Agadir and I2 for Casa→Tangier (site set matched to corridor need).

## Artifact index

- Dataset figures D-1…D-6; results figures R-1…R-11; supplementary direction-blind access figure.
- Tables D-T01…D-T07 and R-T01…R-T13 under `tables/`.
- Experiments under `experiments/` (primary 168, Settat, diagnosis, DEM/flat, q-grid, robustness 45, fine SOC 15, fixed-vs-flex 24).
- Release manifest: `manifests/release_manifest.json`.
- Consistency gate: `validation/consistency_report.json` (ladder_ok=true).

## Most informative figures/tables

- R-Figure 1, 3, 4, 7, 8; D-Figure 1, 3, 4; R-T02, R-T04, R-T05, R-T10, R-T12, R-T09
