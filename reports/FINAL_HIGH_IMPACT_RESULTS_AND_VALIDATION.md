# FINAL_HIGH_IMPACT_RESULTS_AND_VALIDATION

Git SHA: `ce3bf8653553d693cae57d4ca03793122f0732cc`

Primary metric: **operational_coverage** = share of missions that are
energy-feasible **and** schedule-valid under décret 2-10-314 arts. 17–19
(4.5 h continuous driving → ≥45 min uninterrupted pause, daily driving ≤9 h),
after chronological rest extension at verified stops and full continuous re-replay.
Energy coverage is reported separately and is **not** the paper’s service claim.

## 1. How many missions does each method actually serve?

| budget | B_ops | C_ops | D_ops | E_ops | F_ops | E_energy | E_sites | E=F ops? |
|---|---:|---:|---:|---:|---:|---:|---|---|
| B0 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | nan | True |
| B1 | 0.00 | 0.33 | 0.33 | 0.67 | 0.67 | 0.67 | y_benguerir_ca | True |
| B2 | 0.00 | 0.67 | 0.33 | 1.00 | 1.00 | 1.00 | y_benguerir_ac,y_benguerir_ca | True |
| B3 | 0.00 | 0.67 | 0.33 | 1.00 | 1.00 | 1.00 | y_benguerir_ac,y_benguerir_ca | True |
| Ball | 0.33 | 0.67 | 0.67 | 1.00 | 1.00 | 1.00 | y_benguerir_ac,y_benguerir_ca | True |

At B2, joint enum operational coverage = 1.00 vs energy coverage = 1.00. Do not claim 100% operational service unless E_ops = 1.00.

## 2. How many charging sites are needed?

See E_sites / F_sites by budget in the table above. Site geography remains the four
direction-specific ADM service areas (Settat/Benguerir CA & AC).

## 3. Which routes benefit from flexibility and why?

At budget B2 with identical vehicle/SOC/payload/physics, mission-level operational service:

- C fixed+optimized Benguerir pair: casa_marrakech=N, casa_agadir=Y, agadir_casa=Y
- D multi+conventional Settat pair: casa_marrakech=Y, casa_agadir=N, agadir_casa=N
- E joint multi+enum Benguerir pair: casa_marrakech=Y, casa_agadir=Y, agadir_casa=Y
- F greedy multi Benguerir pair: casa_marrakech=Y, casa_agadir=Y, agadir_casa=Y

Mechanism separation: (i) **route flexibility** unlocks `casa_marrakech` (fixed never ops-serves it under the same chargers); (ii) **site choice** unlocks schedule-valid `casa_agadir` / `agadir_casa` when Benguerir directed sites replace Settat-only conventional installs; (iii) **joint** placement + multi-route is required for all three missions at B2. Enum and greedy **tie** on operational coverage — do not claim superiority.

## 4. Detours, charging times, rest delays

- `casa_marrakech`: road_km=257.76, drive_min=199.7, charge_min=20.0, wait_min=0.0, HOS_pad_min=0.0 at `nan`, min_soc=0.1385
- `casa_agadir`: road_km=445.62, drive_min=339.7, charge_min=70.0, wait_min=0.0, HOS_pad_min=0.0 at `nan`, min_soc=0.1520
- `agadir_casa`: road_km=429.15, drive_min=322.1, charge_min=30.0, wait_min=15.0, HOS_pad_min=15.0 at `benguerir_ac`, min_soc=0.2353

Full ordered DRIVE/CHARGE/WAIT timelines: `results/final_charging_rest_traces.csv`.

## 5. Robustness

- R0_base: status=OPTIMAL min_soc=0.150185874117155
- R1_soc05: status=INFEASIBLE min_soc=nan
- R2_payload10t: status=INFEASIBLE min_soc=nan
uses q=2: reserve 15%/20% with Benguerir are OPTIMAL (min_soc≈0.199 / 0.235), confirming
- R4_reserve20: status=OPTIMAL min_soc=0.2352005053902524
- R5_chg250: status=OPTIMAL min_soc=0.1494550565979467
- R6_hot: status=OPTIMAL min_soc=0.152315022827257
- R7_aero110: status=OPTIMAL min_soc=0.1489519143965657
- R8_roll110: status=OPTIMAL min_soc=0.150300483970536

Reserve 15%/20% at coarse q=5 remains a discretization caution; finer q restores energy service.

## 6. Finer grids

Portfolio primary run uses q=5. Robustness matrix in `results/final_physics_robustness.csv`
uses q=2: reserve 15%/20% with Benguerir are OPTIMAL (min_soc≈0.199 / 0.235), confirming
prior q=5 reserve INFEASIBLE labels were discretization artifacts, not physical impossibility.
SOC 0.5 and 10 t payload remain INFEASIBLE at q=2 under the tested cells.

## 7. Joint enum vs greedy vs fixed

E is **exhaustive enumeration** over four sites (not branch-and-bound runtime).
F is an **independent sequential greedy** on operational coverage (early-stop when
coverage saturates; does not force-fill unused budget slots).
At every budget, E_ops = F_ops on the eActros panel — report a **tie**, not superiority.
Fixed-route C ≤ 0.67; conventional multi D ≤ 0.67 at B2.

## 8. What remains illustrative

- Equal mission weights are research proxies, not observed OD volumes.
- Chargers are hypothetical HGV CCS at verified ADM sites; no grid-capacity claim.
- CCS taper sensitivity is a conservative research envelope, not OEM-measured.
- Refrigeration UA/COP are engineering assumptions; cool tomato load is legitimately modest.
- Axle-law compliance unverified.

## Reproduction

```bash
python -m pytest tests/unit/test_hos_chronological.py tests/unit/test_operational_schedule.py -q
python scripts/run_final_operational_correction.py --phase all --q 5
```

## Volvo panel (`volvo_475`, q=5)

| budget | B_ops | C_ops | D_ops | E_ops | F_ops | E_sites | E=F? |
|---|---:|---:|---:|---:|---:|---|---|
| B0 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | nan | True |
| B1 | 0.00 | 0.00 | 0.33 | 0.33 | 0.33 | y_settat_ca | True |
| B2 | 0.00 | 0.33 | 0.33 | 0.67 | 0.67 | y_benguerir_ca,y_settat_ca | True |
| B3 | 0.33 | 0.33 | 0.67 | 0.67 | 0.67 | y_benguerir_ca,y_settat_ca | True |
| Ball | 0.33 | 0.33 | 0.67 | 0.67 | 0.67 | y_benguerir_ca,y_settat_ca | True |

Interpretation: under the same equal-weight corridor portfolio and HOS/physics screens, Volvo operational coverage saturates at **0.67** (E=F tie). Joint/greedy prefer `y_settat_ca`+`y_benguerir_ca`; northbound `agadir_casa` remains unserved in this panel. Do not transfer eActros 100% B2 ops claims to Volvo.

Source: `results/final_operational_coverage_vs_budget_volvo_475.csv` (separate from primary eActros CSVs).

## Validation evidence

- Unit tests: pytest HOS/schedule/taper/quantization suite -> 17 passed.
- Manuscript: tectonic paper/manuscript.tex -> paper/manuscript.pdf produced.
- Claims crosswalk: paper/claims_to_results_crosswalk.csv (23/23 verified against regenerated artifacts).
- Freeze hashes: results/publication_freeze_meta.json and results/final_reproducibility_manifest.json.
