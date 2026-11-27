# P4 — Volvo Settat CA+Larache RT vs Benguerir CA+Larache RT (paired closure)

**Scope:** Final comparative analysis for the 56-cell Volvo matched-infra panel (`volvo_settat_vs_benguerir_*`). Does **not** extend research scope beyond existing CSVs and the 5-minute HOS-in-search baseline. The study evaluates **constructed corridor missions** at **5.3 t** payload (`P4_payload_justification.md`); it is **not** a representation of observed national freight demand.

**Epistemic labels used below**

| Label | Meaning |
|---|---|
| **Verified numerical** | Reproduced from committed mission CSVs under the frozen protocol (600 s / 2×10⁶ expansions, `hos_in_search`, 5 min timestep). |
| **Engineering plausibility** | Mechanistic interpretation consistent with model physics; not independently measured. |
| **Conditional scenario** | Holds only for the stated vehicle, SOC, OD, and install set. |
| **External empirical** | Not claimed here. |

---

## Protocol

| Item | Value |
|---|---|
| Vehicle | Volvo FH Electric class, **475 kWh** usable (`volvo_475`) |
| Configurations | `V_benguerir_larache` = {`y_benguerir_ca`, `y_larache_rt`}; `V_settat_larache` = {`y_settat_ca`, `y_larache_rt`} |
| ODs | 14 national corridor missions (same set as primary I0–I3 panel) |
| SOC scenarios | `stressed_mixed` (per-mission nominal SOC) and `common_soc_80` (all @ 80%) |
| Mass | **5300 kg** fixed cargo (research counterfactual, not typical line-haul loading) |
| Time policy | **Baseline `ts5`** (5-minute HOS discretization in search); refined `ts2` / `ts1` sensitivity is **labeled separately** and does not replace headline coverage |

Sources: `volvo_settat_vs_benguerir_missions.csv`, `volvo_settat_vs_benguerir_ops_matrix.csv`, `volvo_settat_vs_benguerir_summary.csv`, `tables/results/R-T24_volvo_settat_benguerir_paired.csv`.

Related (different vehicle / installs): eActros singleton Settat vs Benguerir CA only — `experiments/settat_vs_benguerir/settat_benguerir_notes.md`, `R-T04_*`.

---

## 1. Coverage (operational feasibility) — report separately

**Verified numerical** ops-served counts @ `ts5`:

| SOC scenario | Benguerir + Larache | Settat + Larache | Panel total |
|---|---:|---:|---:|
| `stressed_mixed` | **8/14** | **9/14** | 14 |
| `common_soc_80` | **10/14** | **9/14** | 14 |

Neither configuration uniformly dominates coverage. Preference **reverses by SOC scenario**:

- **Stressed mixed:** Settat **+1** (`casa_marrakech`: Benguerir energy-INFEASIBLE; Settat OPTIMAL with en-route support).
- **Common 80%:** Benguerir **+1** (`casa_agadir`: Benguerir OPTIMAL with 55 min charge; Settat INFEASIBLE).

**Verified numerical** missions served by neither config: **5/14** on `stressed_mixed` (`agadir_casa`, `casa_agadir`, `casa_tangier`, `marrakech_agadir`, `tangier_casa`); **4/14** on `common_soc_80` (same list except `casa_agadir`, which is Benguerir-only — see asymmetry table).

Neither site choice changes Volvo coverage on the northern / Rabat–Fes–Tangier sub-panel when both configs are ops-feasible (see paired section).

**Conditional scenario:** Lower headline means in `volvo_settat_vs_benguerir_summary.csv` (e.g. Settat lower `mean_objective` on common 80%) reflect **different mission sets** (unpaired denominators), **not** superior efficiency on shared missions. Paired analysis is required for efficiency claims.

---

## 2. Paired operational efficiency (intersection only)

**Rule:** Compare road km, drive time, objective, charge/wait, and SOC **only** where **both** configurations are operationally served under the same SOC scenario.

**Verified numerical** paired counts:

| SOC scenario | Missions both ops-served | Share of 14-OD panel |
|---|---:|---:|
| `stressed_mixed` | **8** | 8/14 |
| `common_soc_80` | **9** | 9/14 |

On every paired mission, Benguerir and Settat yield **identical** `road_km`, `drive_min_phys`, `objective`, `charge_min_phys`, `wait_min_phys`, `min_soc`, and `arrival_soc` (all pairwise deltas = 0). **Verified numerical:** 8/8 stressed ties; 9/9 common ties.

**Engineering plausibility:** When both solutions are ops-feasible, the optimizer selects the same Larache-anchored driving structure; the alternate CA site is unused on these cells (terminal `END`, zero charge/wait on the paired northern/middle corridors). Efficiency therefore cannot discriminate the two CA placements within the paired set.

**Not paired (coverage-only deltas):**

| SOC | OD | Benguerir | Settat | Mechanism (conditional) |
|---|---|---|---|---|
| `stressed_mixed` | `casa_marrakech` | INFEASIBLE | OPTIMAL | Energy reserve / charging topology: Settat route uses **30 min** charge en route (`charge_min_phys`); Benguerir lacks a feasible stressed solution. |
| `common_soc_80` | `casa_agadir` | OPTIMAL (obj 49842, 55 min charge) | INFEASIBLE | Long southern corridor @ 80%: Benguerir placement enables charge; Settat install set does not. |

Refrigeration (**verified numerical** from `P2_P4_findings.md`): on tested eActros near-threshold cells, refrigeration is a small traction share and does not change I1 enablement; Volvo `casa_marrakech` @ 50% remains infeasible with or without refrigeration. **Do not inflate** refrigeration as a driver of Settat vs Benguerir outcomes here; outcomes are dominated by **energy reserve and directional charging placement**, not fridge load.

Battery-capacity counterfactual (**conditional scenario**, `P5_4_battery_capacity_counterfactual.md`): raising usable capacity to 600 kWh while holding Volvo mass/aero fixed restores stressed `casa_marrakech` energy feasibility — indicates **reserve margin**, not a commercial retrofit claim. Full vehicle comparison remains on modeled configurations.

---

## 3. Time-discretization corrections vs “preference reversal”

**Baseline preserved:** Authoritative Volvo Settat vs Benguerir coverage remains the **`ts5`** panel above. P0 / time-discretization work flags cases where **refined timestep** (`ts2`, `ts1`) restores ops feasibility (e.g. Volvo Marrakech→Agadir @ 80% on primary I2) — those rows live under `experiments/time_discretization/` and `R-T14c_refined_time_matched_reevals.csv` and must **not** be merged silently into the `ts5` table.

**Verified numerical:** Re-screen of `volvo_settat_benguerir_56` rows in `affected_case_inventory_224plus.csv` does **not** change ops counts relative to the baseline missions file (still **8 vs 9** stressed, **10 vs 9** common @ `ts5`). Temporal refinement is a **labeled sensitivity** on HOS ceil inflation; it does **not** remove the SOC-dependent **coverage** preference reversal between Settat and Benguerir.

**Reconciliation wording:**

| Question | Answer @ `ts5` |
|---|---|
| Who wins stressed coverage? | **Settat** (9 vs 8) |
| Who wins common 80% coverage? | **Benguerir** (10 vs 9) |
| Who wins on paired efficiency? | **Neither** (complete ties) |
| Does refined `ts` flip the coverage winner? | **No** for this 56-cell panel; refined `ts` may flip **other** cells (document separately) |

---

## 4. Cross-links

| Artifact | Role |
|---|---|
| `R-T24_volvo_settat_benguerir_paired.csv` | Mission-level coverage + paired metrics + summary rows |
| `P5_reconciliation_notes.md` | Global P5 policy; Volvo subsection updated for P4 closure |
| `P5_4_battery_capacity_counterfactual.md` | Capacity-only counterfactual (fixed mass) |
| `settat_benguerir_notes.md` | eActros singleton CA sites (different experiment) |

---

## 5. Reporting checklist (P4)

1. State coverage counts **before** any efficiency comparison.
2. Restrict efficiency statements to **paired** missions (8 stressed, 9 common @ `ts5`).
3. Attribute asymmetric missions to **coverage / energy topology**, not to spurious mean objectives across unpaired sets.
4. Keep `ts5` headline; cite refined timestep results only with explicit `ts2` / `ts1` labels.
5. Do not extrapolate to national freight demand or minimum infrastructure.