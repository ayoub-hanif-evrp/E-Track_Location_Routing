# Scientific Validation Report

**Path A positioning:** Operational feasibility / charging-infrastructure assessment (TRIP-oriented); MRLS is an *instrument*, not an algorithm contribution.  
**Baseline commit:** `453d391ab3dd1d18d9c1710f20c74059f6af03aa`  
**Working tree:** Path A Gate 0–5 edits after baseline (see git status)  
**Baseline archive:** `results/validation/baseline_453d391/`  
**Path A artifacts:** `results/validation/path_a/`  
**Recommendation:** `CONDITIONAL` → near-READY (graph release live; Settat B1 LIMIT footnoted; claims ⊆ Path A crosswalk)

## Executive summary

Authoritative eActros ops ladder (Gate 0 reconciliation): **B0 9/14**, **B1 C=10/14 E=11/14**, **B2 C=E=11/14**. The **12/14** figure is ablation `multi_on_C` only (FLEX_GAIN on `casa_marrakech`) — **not** the B2 manuscript headline. Numbers remain best-known under cardinality cap 2, not globally optimal over \(2^9\). Fixed⊆multi flexibility loss on C was a **LIMIT artifact** at 500k; nesting restored at 2e6. Blind 10/14 vs E 11/14 was evaluator/LIMIT mismatch — fair eval matches E after escalate.

## Path A Gate 0–1 status

| Gate | Artifact | Status |
|------|----------|--------|
| 0.1 Coverage 11 vs 12 | `path_a/coverage_reconciliation.csv` + notes | **done** — one authoritative number per (vehicle,budget,method) |
| 0.2 HOS search↔replay + single duty | `classify_duty_scope` / `MULTI_DAY_OUT_OF_SCOPE`; tests in `test_hos_in_search.py` | **done** |
| 0.3 Energy≠ops dual | `path_a/energy_ops_dual_check.csv`; dual solve in `evaluate_mission_operational` | **done** |
| 1 Physics plausibility | `path_a/physics_plausibility.csv` (~1.34 kWh/km flat cruise; TRU Wh table) | **done** (reference-check, not field validation) |
| 1 Re-prep sensitivity | `scripts/run_remaining_p6_extras.py` re-bakes DRIVE tables | **wired** |
| 2 Design freeze | `path_a/experimental_design_freeze.md` | **frozen** |

---

## Validated claims

| ID | Claim | Evidence | Status |
|----|--------|----------|--------|
| V1 | eActros B1 joint multi (E) covers 11/14 vs fixed C 10/14 under HOS enum_cap≤2 | `q2_critical_portfolio.csv` | **best-known under cap** |
| V2 | B2 E=C=11/14 (no further multi-route gain at card≤2 winner) | same | best-known under cap |
| V3 | Volvo flat E=C=F=0.571 across B1–Ball | same | best-known under cap |
| V4 | short ⊆ all masks on violator ODs; nesting holds at 2e6 expansions | `results/validation/p1_nesting/escalate_2e6/` | **validated** |
| V5 | Continuous HOS break (≥45 min CHARGE+WAIT) resets drive clock; daily clock does **not** reset | `tests/unit/test_hos_in_search.py` | **validated** |
| V6 | Ops-true mini-panel rows are HOS audit-only (no post-pad) | `hos_mini_panel_gate.csv` | validated |

## Unsupported / withdrawn claims

| ID | Claim | Reason |
|----|--------|--------|
| W1 | `hos_in_search_full_enum` / global optimality | Card_cap=2 + 45s screen; relabeled `hos_in_search_enum_cap2_screen45_final600` |
| W2 | Certified flexibility **loss** on C (multi worse than fixed) at B2 | `casa_tangier`/`casa_agadir` were `LIMIT_ARTIFACT` / `LIMIT_CONTAMINATED` at 500k; at 2e6 → `BOTH_OPS` |
| W3 | Blind greedy underperforms E at identical Benguerir sites | Withdrawn: shared eval + 2e6 escalate matches E at 11/14 |
| W4 | Ball “more sites hurt” as physical non-monotonicity | B/D drops tied to `LIMIT_REACHED` after charger expansion |
| W5 | Full Moroccan multi-day HOS (Art.16 overnight daily rest) | Not implemented; daily_drive never resets |
| W6 | Legacy robustness / full frontier HOS certification | Files removed; not re-run under HOS |

---

## Priority 1 — Route nesting

### Problem
Ablation reported fixed_on_C=11/14 > multi_on_C=10/14 (`casa_agadir`, `casa_tangier`).

### Root cause
At default 500k expansions, multi (and sometimes fixed) hits `LIMIT_REACHED`. Ablation stored only bools, collapsing LIMIT into False. Masks satisfy short ⊆ all.

### Resolution (2e6 expansions, 600s)
| OD | fixed_C | multi_C | class_C | fixed_E | multi_E | note |
|----|---------|---------|---------|---------|---------|------|
| casa_agadir | OPTIMAL/True | OPTIMAL/True | BOTH_OPS | OPTIMAL/True | OPTIMAL/True | nesting OK |
| casa_tangier | OPTIMAL/True | OPTIMAL/True | BOTH_OPS | INFEAS/False | INFEAS/False | E site off-graph (placement confound) |

### Code / tests
- Status columns + nesting classifier in `ablation_live`
- `ABLATION_MAX_EXPANSIONS = 2_000_000`
- `scripts/run_priority1_nesting_diagnosis.py`
- `tests/unit/test_validation_scoring_and_nesting.py`

### Numerical impact on headline 9/10/11
**None** (headline E/C aggregates unchanged). Withdraw certified flex-loss narrative.

### Full 14-OD panel (done)
`results/validation/p1_nesting/full_b2_2e6/`: **0 LIMIT_ARTIFACT**; aggregates match headline
(`fixed_on_C=0.786`, `multi_on_E=0.786`). Nesting classes: 11 BOTH_OPS, 1 FLEX_GAIN, 2 BOTH_FAIL.
Promoted to `results/paper_campaign/placement_flexibility_ablation.csv`.

---

## Priority 2 — Greedy vs enum

### Problem
Same site `y_benguerir_ca`, blind 10/14 vs E 11/14.

### Root cause
`_eval_installed_on_panel` counted `ops ∧ status==OPTIMAL`; `evaluate_subset` counted `ops` only.

### Fix
Shared `coverage_from_mission_rows()`; blind final eval columns; `scripts/run_priority2_fair_site_eval.py`.

### Result
At 500k expansions, fair Benguerir eval = **10/14** with `casa_agadir=LIMIT_REACHED`.  
After escalating that OD to **2e6** expansions: **11/14 = E_ops** (`matches_E_ops=True`, n_limit=0).  
Evidence: `results/validation/p2_fair_eval/fair_frozen_site_eval.csv`.  
**Conclusion:** same installed set + matched protocol ⇒ same coverage; prior blind gap was LIMIT + metric mismatch, not algorithm superiority.

---

## Priority 3 — Placement certification

- Pipeline renamed away from `full_enum`.
- B1 singles matched eval (600s/2e6): Benguerir uniquely best among resolved candidates at **0.786**; Settat has unresolved `LIMIT_REACHED` on `casa_agadir` (ops≤0.714 after escalate attempt) → label `best_of_matched_B1_singles_settat_LIMIT_unresolved_benguerir_unique_among_resolved`.
- Evidence: `results/validation/p3_b1_certify/`

---

## Priority 4 — Reproduction

Canonical commands (README + stage_d):

```bash
python scripts/run_stage_c_hos_national.py --phase headline_enum
python scripts/run_stage_c_hos_national.py --phase post_portfolio
python scripts/run_validation_consistency_report.py
```

**Do not** run `all_fast` after `headline_enum` (overwrite risk).  
Consistency report: `results/validation/consistency_report.json`.

---

## Priority 5 — Controlled q-grid (done)

Cell: eActros, Agadir→Casa, 15 t, SOC 0.8, `y_benguerir_ac`, 600s/500k.

| q | multi status / ops | fixed status / ops | min SOC |
|---|--------------------|--------------------|---------|
| 5 | INFEASIBLE / False | INFEASIBLE / False | — |
| 2 | OPTIMAL / True | OPTIMAL / True | ≈0.1077 |
| 1 | OPTIMAL / True | OPTIMAL / True | ≈0.1077 |

**Interpretation:** Coarse q=5 yields a **false infeasibility** relative to q=2/1 under identical physics/HOS (not a LIMIT artifact). Near-reserve margin (~10.8% vs 10% reserve). Evidence: `results/validation/p5_qgrid/qgrid_controlled.csv`.

## Priority 6 — Southbound sensitivity (done)

Benguerir CA, multi, q=2, 600s/2e6; SOC∈{0.5…1.0} × payload∈{5.3,10,15}t; 30 cells; **0 LIMIT**.

| OD | OPTIMAL ops | Failures (INFEASIBLE) |
|----|-------------|------------------------|
| Casa→Agadir | 14/15 | SOC0.5 × 15t only |
| Casa→Marrakech | 13/15 | SOC0.5 × 10t and 15t |

SOC≥0.6 served for all tested payloads. Not a real-world probability.  
CSV: `results/validation/p6_sensitivity/southbound_sensitivity.csv`.

### P6 extras (aero/aux/weather labels)
`scripts/run_remaining_p6_extras.py` now **re-bakes DRIVE tables** via patched vehicle YAML / demand `weather_id` before evaluate.
Prior CSV rows without `pipeline=p6_extras_rebake` are protocol stubs; re-run extras when refreshing sensitivity appendix.
Treat SOC×payload P6 grid as authoritative for RQ1 thresholds.

## Priority 7 — HOS-on vs energy-only (done)

Benguerir CA panel: energy-only coverage = ops HOS-on coverage = **0.786**; `energy_true_ops_false=0` on that install.
Dual separation still holds elsewhere: Gate 0.3 shows authoritative baseline cells with energy ≠ ops when HOS binds (`path_a/energy_ops_dual_check.csv`).
CSV: `results/validation/p7_hos_on_off/`. Overnight daily-rest reset still not implemented (`MULTI_DAY_OUT_OF_SCOPE`).

---

## Solver-certification summary

| Setting | Value |
|---------|-------|
| Winner / panel final | 600 s, 500k expansions (ablation cert: 2e6) |
| Enum screen | 45 s, ops-only, card_cap=2 |
| LIMIT policy | Never equate to INFEASIBLE in narrative |

## Exact reproduction (authoritative tables)

1. Clean checkout at recorded SHA (or note dirty tree).  
2. `pip install -e ".[dev]"` + graph artifact if needed.  
3. Path A fast gates:  
   - `python scripts/path_a/build_coverage_reconciliation.py`  
   - `python scripts/path_a/verify_energy_ops_dual.py`  
   - `python scripts/path_a/build_physics_plausibility.py`  
4. Canonical Stage C commands in README.  
5. Validation extras:  
   - `python scripts/run_priority1_nesting_diagnosis.py`  
   - `python scripts/run_priority2_fair_site_eval.py`  
   - `python scripts/run_priority5_qgrid_controlled.py`

## Recommendation rationale (`CONDITIONAL`)

**Cleared:** P1 full ablation at 2e6; P2 fair eval; P3 B1 singles (Benguerir unique among resolved; Settat LIMIT unresolved); P4 dirs+repro docs; P5 q-grid; P6 SOC×payload; P7 HOS-on=energy coverage on Benguerir; manuscript rebuild.  
**Still open for READY:** (1) confirm CI graph download from `multiroute-graph-v1`; (2) resolve Settat `casa_agadir` LIMIT or keep best-among-resolved footnote; (3) optional full re-run of rebaked P6 extras for appendix tables.  
Manuscript retargeted to TRIP Path A feasibility claims (RQ1–RQ3); algorithm novelty withdrawn.
