# Interim scientific findings (campaign in progress)

**Not a completion certificate.** Evidence package still expanding (Volvo, Settat, diagnosis, P2–P5).

## Strongest supported findings (so far)

1. **Claimed dataset counts independently verified** on live artifacts (motorway 58 002/58 157; expanded 391 653/397 255; decision 198/293; 18 OD / 36 paths; 19 inventory sites; 14 headline missions).
2. **eActros stressed ladder reproduced** on baseline `8b0cbf7`: I0=9/14, I1=11/14, I2=12/14, **0 LIMIT**.
3. **Departure-SOC confound is real:** under matched 80% SOC, eActros coverage becomes I0=11/14, I1=12/14, I2=13/14. Infrastructure still helps, but two of the stressed I0 failures (`casa_marrakech`, `marrakech_agadir`) are SOC-driven rather than infrastructure-driven.
4. **Directional topology** for remaining hard cases: Amskroud CA is on `marrakech_agadir` union; Benguerir/Settat **AC** (not CA) are on `agadir_casa`. I2 installs Benguerir **CA** + Larache RT — directionally mismatched for Agadir→Casa.

## Vehicle comparison (Volvo stressed — complete; common-SOC partial)

| Config | eActros stressed | Volvo stressed |
|--------|-----------------:|---------------:|
| I0 | 9/14 | **7/14** |
| I1 Benguerir CA | 11/14 | **7/14** (no gain) |
| I2 +Larache | 12/14 | **8/14** |

**Do not claim eActros-selected infrastructure is optimal for Volvo.** Benguerir CA alone does not raise Volvo stressed coverage; Larache adds +1. Smaller usable battery (Volvo research pack) is the leading mechanistic hypothesis pending energy-decomposition tables.

## Conditional / pending

- Volvo common-SOC I1–I2 (resuming after process interrupt).
- Whether Settat CA ties Benguerir CA on coverage and how stationary times compare under final protocol.
- Whether existing AC candidates or SOC/operating changes restore `agadir_casa` / stressed `marrakech_agadir` without inventing sites.

## Infeasible-mission diagnosis (Task 7.2) — complete

| Mission | Mechanism | Effective remedy (existing options only) |
|---------|-----------|------------------------------------------|
| `marrakech_agadir` @ 50% | **Initial SOC / energy**, not missing topology | SOC≥0.9 restores feasibility even with **no** chargers; Amskroud CA on union does **not** restore at 50% |
| `agadir_casa` @ 80% | **Wrong carriageway direction** under I2 (CA vs AC) | `y_benguerir_ac` alone → OPTIMAL; SOC=1.0 also works without infra; Settat AC alone insufficient |

## Settat vs Benguerir (Task 7.1)

Coverage **ties at 11/14** after Settat escalate. Benguerir resolves Casa→Agadir at standard budget (65 min charge); Settat needs escalate and uses **120 min** stationary (75 charge + 45 wait). Objective slightly worse for Settat (51722 vs 51682).

## Negative / unexpected (informative)

- Even at 80% SOC + I2, **`agadir_casa` remains infeasible** for eActros — fixed by **AC-direction** Benguerir, not by more CA sites.
- Amskroud on Marrakech→Agadir union is **not sufficient** under 50% departure SOC.
- Expanded-network HGV tags are essentially all **unknown** — must not be sold as confirmed legal truck access.
- Volvo stressed: Benguerir CA alone gives **zero** coverage gain vs I0.

## DEM vs flat (Task 8.5) — complete for 4 corridors

DEM raises traction by ~65–102 kWh on Casa→Agadir / Casa→Marrakech / Rabat→Fès vs flat; regen credit appears only under DEM. Coastal Casa→Rabat difference is small and can reverse. Feasibility unchanged on these equipped cells. Table: `tables/results/R-T09_dem_vs_flat.csv`.

## Most informative artifacts so far

- `tables/dataset/D-T0*` + `dataset/dataset_quality_and_construction_report.md`
- `experiments/primary_comparison/primary_summary.csv` (full 168-cell grid)
- `tables/results/R-T04_*` (Settat/Benguerir), `R-T12_*` (infeasible remedies), `R-T09_*` (DEM/flat)
- `figures/dataset/D-Figure1_*`, `D-Figure3_*`, `D-Figure5_*`, `D-Figure6_*`
- `figures/results/R-Figure1_*`, `R-Figure3_*`
- `dataset/infeasible_topology_notes.md` + accessibility matrix
- `validation/consistency_report.json` (pass)