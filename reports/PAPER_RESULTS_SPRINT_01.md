# PAPER_RESULTS_SPRINT_01

Git SHA (base): `ce956e601eb11ab6fa2175266acf1f3846d40a90` (sprint edits uncommitted)  
Date: 2026-11-15  
Scope: integrity corrections + matched H1 pilots + ADM candidate evidence + operational schedule screen. **Not** a publication-ready freeze.

## Authoritative vs superseded

- Authoritative prior freeze: `reports/FINAL_RESEARCH_FREEZE.md`, `final_numerical_integrity.md`, `final_moroccan_robustness_results.md`, `task07c_*`, `results/final_action_rounding_audit.csv`.
- This sprint **adds** `paper_results_*` artifacts; it does not overwrite freeze CSVs or `paper/manuscript.tex`.
- Historical Task07C H1 at q=10 remains archival; new H1 pilots re-test at q=5 and q=2 on the same physical graph with `allowed_arc_ids`.
- `drive_path_floor_loss` remains SUPERSEDED by `audit_solved_actions_exact`.

## Integrity corrections

1. Explicit demand `A_nb_tomato_p5300_soc10` (SOC=1.0) in `multiroute_placement_pass2a.yaml`; robustness no longer uses `force_soc` on an 80% demand (q=2 refine uses the same SOC100 demand).
2. `audit_solved_actions_exact`: continuous DRIVE sim failure or `table_vs_floor_gap` beyond tolerance → `audit_ok=False` (adversarial unit tests added).
3. eActros CCS acceptance cap set to **400 kW** (Mercedes public page); effective power = min(charger_kw, 400). No OEM SOC-dependent curve — constant envelope stated explicitly.

## Site candidates (H5)

ADM directory lists Marrakech and Oum Rbii (Agadir→Casablanca). OSM match status: `prospective_official_name_only_no_osm_geometry` for both. **Not enabled** — no fabricated connectors or proximity snaps. Benguerir/Settat northbound remain the only topology-accepted pass2a candidates. See `results/paper_results_site_candidates.csv`.

## H1 matched pilots (fixed vs multi-route)

Same canonical DEM graph, same battery grid, chargers toggled via active stations, fixed route restricted by `allowed_arc_ids` (no graph rebuild). SOC₀=0.5, payload 5300 kg, 350 kW chargers, refrigerated.

Convincing feasibility gains (fixed INFEASIBLE → multi OPTIMAL; audit + continuous replay OK) in **6** cells:

| OD | Truck | q | Road (km) | Charge (kWh) | min SOC | Multi obj |
|---|---|---:|---:|---:|---:|---:|
| casa_marrakech | eactros_600 | 5 | 257.8 | 105 | 0.145 | 27997 |
| casa_marrakech | volvo_475 | 5 | 257.8 | 160 | 0.156 | 29157 |
| casa_agadir | volvo_475 | 5 | 460.7 | 405 | 0.155 | 54613 |
| casa_marrakech | eactros_600 | 2 | 257.8 | 86 | 0.113 | 27597 |
| casa_marrakech | volvo_475 | 2 | 257.8 | 140 | 0.121 | 28737 |
| casa_agadir | volvo_475 | 2 | 460.7 | 368 | 0.124 | 53833 |

Without chargers (`install=none`), both methods remain INFEASIBLE. Do **not** report %-cost savings vs an infeasible fixed baseline — the result is a **feasibility / coverage** gain from route flexibility under identical infrastructure.

| OD | Truck | Install | q | Fixed | Multi | Gain |
|---|---|---|---:|---|---|---|
| casa_marrakech | eactros_600 | none | 5 | INFEASIBLE | INFEASIBLE | False |
| casa_marrakech | eactros_600 | settat_benguerir | 5 | INFEASIBLE | OPTIMAL | True |
| casa_marrakech | volvo_475 | none | 5 | INFEASIBLE | INFEASIBLE | False |
| casa_marrakech | volvo_475 | settat_benguerir | 5 | INFEASIBLE | OPTIMAL | True |
| casa_agadir | volvo_475 | none | 5 | INFEASIBLE | INFEASIBLE | False |
| casa_agadir | volvo_475 | settat_benguerir | 5 | INFEASIBLE | OPTIMAL | True |
| casa_marrakech | eactros_600 | none | 2 | INFEASIBLE | INFEASIBLE | False |
| casa_marrakech | eactros_600 | settat_benguerir | 2 | INFEASIBLE | OPTIMAL | True |
| casa_marrakech | volvo_475 | none | 2 | INFEASIBLE | INFEASIBLE | False |
| casa_marrakech | volvo_475 | settat_benguerir | 2 | INFEASIBLE | OPTIMAL | True |
| casa_agadir | volvo_475 | none | 2 | INFEASIBLE | INFEASIBLE | False |
| casa_agadir | volvo_475 | settat_benguerir | 2 | INFEASIBLE | OPTIMAL | True |

Figure: `results/figures/paper_results_sprint_01_h1_feasibility.png`

## Northbound SOC100 placement (all optimal sets)

Explicit demand `A_nb_tomato_p5300_soc10`, E_truck_init=600, peak-speed adaptation ON (same policy as authoritative robustness baseline).

| q | Budget | Equivalent optimal site sets | Notes |
|---|---|---|---|
| 5 | B0 | NONE | coverage 0 — mission unserved without a charger |
| 5 | B1 / Ball | `y_benguerir_ac` **or** `y_settat_ac` | two equivalent single-site optima |
| 2 | B0 / B1 / Ball | NONE | finer grid: full-battery mission served with **zero** en-route sites |

At SOC=1.0, en-route charging need is **q-dependent**. Do not treat a q=5 single-site pick as the unique physical optimum.

Northbound matched (q=5, peak-adapt): SOC 0.8 needs Benguerir (Settat-only fails); SOC 1.0 accepts either site; SOC 0.5 unserved even with both. Fixed vs multi agree on these cells (no extra H1 gain on northbound at screened installs).

## Operational schedule (H3)

Independent 45 min break after 4.5 h continuous driving (Moroccan professional-driver decree family) — validator only, no HOS re-optimizer.

- Casa→Marrakech multi-route (~258 km): schedule OK without a mandatory break.
- Casa→Agadir Volvo (~461 km): long continuous driving; q=5 charge ≈75 min can supply a 45 min overlap, but `schedule_ok=False` when the stop is too late relative to the continuous-driving clock. Charging can overlap rest when long enough; it does not automatically cure continuous-driving violations.

See `results/paper_results_operational_schedule.csv`.

## Hypotheses H1–H5

- **H1**: CONFIRMED — three OD/truck cases at q=5 and q=2 with chargers: fixed-shortest INFEASIBLE, multi-route OPTIMAL, audit + continuous replay OK. Report as feasibility/coverage gain.
- **H2**: WEAK / limited — 2-site northbound universe; enum and greedy B1 often agree because the candidate set is tiny. Not a nationwide siting superiority claim.
- **H3**: PARTIAL — rest/charge overlap occurs on some long missions; alignment is not guaranteed.
- **H4**: PARTIAL — SOC100 q=5→q=2 removes infrastructure need; H1 multi min_SOC ≈0.11–0.16. Dedicated reserve-SOC 10/15/20% policy sweep not yet run.
- **H5**: NOT ENABLED — ADM names exist for Marrakech/Oum Rbii, but OSM geometry unmatched; no fabricated access.

## Reproduction

```bash
python -m pytest tests/unit/test_action_rounding_and_min_soc.py \
  tests/unit/test_operational_schedule.py \
  tests/unit/test_soc100_demand_scenario.py -q
python scripts/run_paper_results_sprint_01.py --phase all
```

## Tests

```
.............                                                            [100%]
13 passed in 0.25s
```

## Artifacts

- `results/paper_results_matched_baselines.csv` (72 rows after 01b: H1 B/C/D + northbound A/C/D/E/Greedy)
- `results/paper_results_site_candidates.csv` (10 rows)
- `results/paper_results_operational_schedule.csv` (16 rows)
- `results/paper_results_soc100_placement.csv` (24 rows)
- `results/figures/paper_results_sprint_01_h1_feasibility.png`
- 01b: `results/paper_results_reserve_soc.csv`, `..._h1_failure_diagnosis.csv`, `..._metric_hygiene.csv`

## Smallest next experiment

1. Optional H1 q=1 check only if a paper claim needs ultra-fine confirmation (q=5 and q=2 already agree).
2. Manual OSM POI resolution for Marrakech / Oum Rbii before any H5 enablement.
3. Optional charging-time sensitivity under the constant CCS envelope (no OEM curve).

## Sprint 01b completion

Prioritized gaps closed in `reports/PAPER_RESULTS_SPRINT_01b.md`: reserve-SOC 10/15/20% (hard cliff at 15%), baseline C, H1 failure diagnosis (charger-access vs road-choice), enum↔B&B hygiene.
