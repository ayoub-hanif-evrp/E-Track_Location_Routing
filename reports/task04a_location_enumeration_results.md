# Task 04A — Location enumeration results

Artifacts: `results/location_enumeration.csv` (1792 rows = 8 scenario combos × 32 subsets × 7 missions), `results/location_optimal_solutions.csv` (32 rows). All subsets certified (no `LIMIT_REACHED`).

Structural mission (excluded from serviceable denominator): **`M_struct_dem_AC`** (Agadir→Casablanca light DEM; peak-motor on first macro-arc under 80 km/h).

## Q1 — Best subset by budget (default / equal / uniform)

| Budget | Best sites | Serviceable coverage | Illustrative CAPEX |
|---|---|---|---|
| B0 (0) | NONE | 1.0 | 0 |
| B1 (100) | `y_benguerir_ca` | 7.0 | 100 |
| B2 (200) | `y_benguerir_ca`, `y_settat_ac` | 9.0 (full serviceable) | 200 |
| Ball | same as B2 | 9.0 | 200 |

One Casa→Agadir mid-corridor site (Benguerir) restores heavy + DEM + refrigerated CA missions; one Agadir→Casa site (Settat) restores the AC heavy mission.

## Q2 — Refrigeration

Heavy flat CA with refrigeration (A and B) is served once `y_benguerir_ca` is installed (included in the B1 coverage jump 1→7). Config A vs B changes variable charge cost slightly but does **not** change the selected sites under the tested budgets.

## Q3 — Differentiated prices

Site **identity** for B0–B2 is unchanged vs uniform. With **unlimited** budget, differentiated tariffs select an extra `y_settat_ca` (cheaper tariff) to cut demand-weighted operating cost at equal full coverage (secondary cost 186.7 vs 209.6 for the two-site set). CAPEX scenario (equal vs amskroud premium) does not change selections because Amskroud is never required for full serviceable coverage.

## Q4 — Marginal coverage vs budget

Default weights (serviceable total = 9): B0→1, B1→7 (+6), B2→9 (+2), Ball→9 (+0). Heavy-emphasis weights (serviceable total = 11): B0→0.5, B1→8, B2→11.

## Q5 — Sensitivity to charging-grid correction

Stage 1 replaced per-step ceil (1 kWh/5 min ≈ 12 kW) with action-level 2.5 kW integration + quantum floor. Heuristics that previously failed with `drive_table_missing` after full charge are consistent with the corrected invariant. Enumeration optima above use the corrected interface; synthetic A–J benchmarks remain exact.

## Q6 — Non-charger infeasibility

`M_struct_dem_AC` remains infeasible with all five sites installed due to peak motor power on the DEM macro-arc — not a missing-charger problem under the fixed 80 km/h policy.

## Q7 — Fixed-route limits

Only charging-stop selection on directed A3 baselines is optimized. No alternate corridors, facility-internal paths, or nationwide graph. Results are exact for this discrete model, not continuous real-world infrastructure optimality.

## Baselines / greedy

Greedy-by-marginal-coverage matches exhaustive site sets for B1/B2 under uniform prices (coverage gap 0). Under differentiated Ball, greedy stops at two sites (no coverage gain from a third) while lex-secondary adds `y_settat_ca` — objective gap is cost-only at equal coverage.
