# Authoritative publication evidence ledger

**Gate commit target:** research integrity P0.1–P0.5 (physical traces, energy-grid audit, B&B certification).  
**Base reviewed HEAD:** `98a042acc8176ffd923cb13e071649398a2de5a3`.  
**Purpose:** single index of retained vs superseded scientific claims for the Moroccan electric refrigerated heavy-truck charging-infrastructure study.

Monetary secondary objectives below are **NORMALIZED ILLUSTRATIVE COSTS**, not Moroccan investment costs. Coverage and minimum-site requirements remain the primary decision outcomes. Do not claim annualized Moroccan investment optimality without annual trips, applicable tariffs, CAPEX and O&M evidence.

---

## How to read status labels

| Label | Meaning |
| --- | --- |
| PHYSICALLY_VERIFIED | Discrete solution + continuous DRIVE/CHARGE/WAIT replay OK on committed geometry/DEM |
| MODEL_ONLY | Finite discrete model result; continuous uniqueness not claimed |
| ILLUSTRATIVE | Scenario / cost / weight assumptions, not observed Moroccan operations |
| SUPERSEDED | Do not cite as primary; kept for reproducibility |
| HISTORICAL | Archived experiment; not the publication baseline |
| UNRESOLVED | Incomplete, timeout, nesting artifact, or missing evidence |

---

## A. Retained primary results

### A1. Authoritative Agadir→Casablanca journey metrics (eActros 600)

| Field | Value |
| --- | --- |
| Commit baseline | `98a042a` + this integrity gate |
| Config | `configs/optimization/multiroute_placement_pass2a.yaml` |
| OD / commodity | Agadir→Casablanca; firm-ripe tomato proxy (`A_nb_tomato_p5300_soc08`) |
| Vehicle / cargo | eActros 600; 5.3 t; departure SOC 0.8 |
| DEM | Independently sampled COPDEM GLO-30 along directed OSM |
| Speed policy | Peak-power adaptive (`adapt_speed_to_peak_power=True`) |
| Chargers | Directional hypothetical `benguerir_ac`, `settat_ac` (not operating ADM HGV chargers) |
| Authoritative distance | **429.15 km** (COMPLETE trace) |
| Evidence | `results/physical_trace_reconciliation.csv`, `reports/physical_replay_trace_integrity.md` |
| Status | PHYSICALLY_VERIFIED |

Incomplete traces are labelled `INCOMPLETE` and excluded from complete-trip statistics.

### A2. Battery quantization policy (conservative flooring retained)

| Field | Value |
| --- | --- |
| Implementation | Floor after DRIVE table build; `_snap_energies_after_stationary` after CHARGE/WAIT |
| CHARGE zero discrete gain | Proven at unit level (300 + 10 − 0.25 → discrete 300 at q=10) |
| Audit | `src/morocco_etruck/optimization/quantization_audit.py` |
| Tests | `tests/unit/test_quantization_error_and_charge.py` |
| Adopted representation change | **None** (finite-model guarantees preserved) |
| Status | MODEL_ONLY + quantified error; not marketed as novel exact continuous algorithm |

Historical rounding on northbound path (DRIVE floors): ~58.5 kWh (rebuild max_alts=2, q=10) and ~85.6 kWh (same nodes on canonical max_alts=4, q=10) — see `results/northbound_route_expansion_summary.json`. Publication claims that depend on discrete feasibility require fine-grid stability (panel A3).

### A3. Energy-grid convergence panel (canonical max_alts=4)

| Field | Value |
| --- | --- |
| Graph | Canonical four-alternative Agadir→Casablanca union (fixed physical graph across q; 51 arcs) |
| q panel | 10 (INFEASIBLE), 5 / 2 / 1 (OPTIMAL, served, cont OK) |
| Ball sites (served) | Stable `{y_benguerir_ac}` for q ∈ {5, 2, 1} |
| Southbound H80 | q=10 INFEASIBLE; q=5 OPTIMAL with empty site set (q-feasibility sensitivity confirmed) |
| Evidence | `results/moroccan_energy_grid_convergence.csv`, `reports/battery_quantization_and_convergence.md` |
| Status | PHYSICALLY_VERIFIED for served fine-grid paths; **q=1 is not a continuous optimum** |

Do **not** claim q-refinement changes the optimal installation within q ∈ {5, 2, 1}. Coarse q=10 changes feasibility only. Replay of a successful path does **not** prove absence of other continuous-feasible paths.

### A4. B&B budget-relaxed bound certification

| Field | Value |
| --- | --- |
| Defect | `certified = budget_ok ∧ routing_ok` blocked safe coverage UB on over-budget supersets |
| Fix | `certified` := routing-resolved; incumbents require `budget_ok`; leaves enforce CAPEX |
| Benchmark | Existing eight-site synthetic shared-road (Task 08); not Moroccan traffic |
| Evidence | `results/bb_relaxed_bound_before_after.csv`, `reports/bb_relaxed_bound_certification.md` |
| Status | MODEL_ONLY (algorithmic correctness on synthetic); **do not claim B&B is generally faster** |

Observed cold-cache after fix: Ball B&B faster than enum; B2/B3 enum faster — report both honestly.

---

## B. Explicitly superseded / historical claims

| Obsolete claim | Replacement | Index |
| --- | --- | --- |
| Fixed-speed northbound all-zero as primary representation | Peak-adapt physics + energy feasibility narrative | SUPERSEDED — `reports/northbound_power_grade_root_cause.md` |
| Cross-graph rebuild max_alts=2 vs max_alts=4 nesting comparisons | Same-graph `allowed_arc_ids` nesting only; publication placement uses q=5 on canonical-4 | SUPERSEDED nesting misuse |
| Unreconciled 353.6 km driving diagnostic | Authoritative 429.15 km COMPLETE replay | SUPERSEDED — `reports/physical_replay_trace_integrity.md` |
| q-refinement already changes optimal charger installation | Served fine-grid sites stable at `{y_benguerir_ac}` for q∈{5,2,1}; q=10 is infeasible only | SUPERSEDED / false for fine-grid installation change |
| B&B is generally faster than enumeration | Synthetic 8-site: depends on budget; no general claim | SUPERSEDED marketing |
| Prospective chargers already operate at ADM sites | Hypothetical future truck sites; ADM identity ≠ HGV 350 kW operation | SUPERSEDED if asserted |
| Simulated Volvo legally certified for Moroccan operation | Model vehicle; `gross_mass_within_limit_axle_unverified`; not type-approval | SUPERSEDED if asserted |

Keep older reports on disk for reproducibility; cite this ledger when selecting publication numbers.

---

## C. Refrigeration interpretation

Existing OFF / nominal / high thermal comparisons remain the evidence base. If refrigeration contribution to energy and siting is negligible under those runs, report that fact. Do **not** amplify refrigeration parameters to manufacture larger effects. Do **not** add cargo-temperature dynamics without evidence or demonstrated need.

Primary northbound Case A uses firm-ripe tomato fridge YAML (`configs/energy/pass2_tomato_firm_ripe.yaml`) as an ILLUSTRATIVE cold-chain proxy.

---

## D. Economic interpretation

| Decision layer | Role |
| --- | --- |
| Coverage / serviceable weight | Primary |
| Minimum installed sites / equivalent optimal sets | Primary |
| En-route incremental / annualized infra+variable cost | NORMALIZED ILLUSTRATIVE secondary objective |
| Moroccan CAPEX, tariffs, O&M, annual trips | Not invented; require sourced scenario before investment claims |

---

## E. Reproduction commands (integrity gate)

```bash
pytest -q tests/unit/test_physical_replay_trace.py \
       tests/unit/test_quantization_error_and_charge.py \
       tests/unit/test_branch_and_bound.py
pytest -q -m "not integration"
python scripts/run_physical_trace_reconciliation.py
python scripts/run_bb_relaxed_bound_benchmark.py
python scripts/run_moroccan_energy_grid_convergence.py
```

A green offline unit CI run alone is **not** sufficient: regenerate the CSV/MD tables from committed Moroccan graph, DEM and configuration inputs before manuscript use.

Offline verification for this gate: `273 passed, 2 deselected` (`pytest -q -m "not integration"`).

---

## F. Hard stops (unchanged)

No nationwide OSM expansion; no new vehicle family; no generic capacity/queue model; no fabricated Moroccan data; no unproved continuous-optimality claims; no new algorithm solely for paper marketing.


## Sprint update

Use `SIMULATION_REPLAY_VALIDATED` instead of unqualified `PHYSICALLY_VERIFIED` for simulated routes. Prior path-node rounding losses are SUPERSEDED by `audit_solved_actions_exact`.
