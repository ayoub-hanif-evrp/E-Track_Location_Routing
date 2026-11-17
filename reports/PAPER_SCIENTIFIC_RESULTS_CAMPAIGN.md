# PAPER_SCIENTIFIC_RESULTS_CAMPAIGN

**Status:** revalidated after independent-rest HOS correction (executable frontier; not `restored_from_logs`).

**Critical assessment:** the campaign supports **conditional** serviceability claims. Joint multi-route helps on a low-SOC headline pilot and on selected Volvo 6-OD depot cells; eActros 6-OD depot shows **E=C=F**. Northbound **15 t @ 80% SOC** remains unserved even with both AC chargers; **100% SOC** restores service. A prior q=2 false negative (5.3 t @ 100% SOC, no charge stop) was an **HOS validator artifact**, not a physical energy failure.

Primary metric: **operational coverage** = energy-feasible ∧ continuous replay ∧ schedule/HOS valid (incl. independent rest at verified on-path ADM nodes when no charge is required).  
Chargers = hypothetical HGV CCS. Scenario counts ≠ traffic samples.  
Artifacts: `results/paper_campaign/` · publication extracts: `results/paper_campaign/publication_tables/`.

---

## Validation correction (rest / HOS)

**Issue.** At fine energy quantum q=2, energy-optimal northbound itineraries at high SOC can skip charging. The prior validator only extended existing CHARGE/WAIT stops, so physically energy-feasible missions failed HOS with `no_verified_stop_before_continuous_limit` even when min SOC ≈ 16.8%.

**Fix.** `propose_chronological_hos_plan` now inserts an **independent qualifying WAIT** at a topology-verified rest node the route already traverses (ADM/service-area graph node such as `benguerir_ac`), with auxiliary + refrigeration energy during the break, then re-replays.

**Revalidation.** eActros Agadir→Casa 5.3 t @ 100% SOC: ops **True** at q=2 and q=1 with or without AC chargers (independent rest). 15 t @ 80% remains **False** at q=2 and q=1 — a real payload–SOC limit, not an artifact.

---

## Experiment 0 — DEM recovery

| OD | dem_complete | On-union stations | Amskroud CA on union? |
|---|---|---|---|
| agadir_casa | True | settat_ac, benguerir_ac | No |
| marrakech_casa | True (recovered) | settat_ac, benguerir_ac | No |
| agadir_marrakech | True (recovered) | *(none — amskroud_ac missing)* | No |
| casa_agadir | True | settat_ca, benguerir_ca, **amskroud_ca** | **Yes** |
| casa_marrakech | True | settat_ca, benguerir_ca | No |
| marrakech_agadir | True | **amskroud_ca** | **Yes** |

---

## Result A — Infrastructure value (coverage vs budget)

### Table 1 — Headline 3-mission pilot (q=2; low-SOC mix)

Denominator: 3 equal-weight missions (casa_marrakech SOC0.5, casa_agadir SOC0.5, agadir_casa SOC0.8; 5.3 t).

| Vehicle | Budget | C ops | E ops | F ops | E−C | E=F? | E sites |
|---|---|---:|---:|---:|---:|---|---|
| eActros | B1 | 0.33 | 0.67 | 0.67 | +0.33 | Yes | benguerir_ca |
| eActros | **B2** | **0.67 (2/3)** | **1.00 (3/3)** | **1.00** | **+0.33** | Yes | both Benguerirs |
| Volvo | B1 | 0.00 | 0.33 | 0.33 | +0.33 | Yes | settat_ca |
| Volvo | **B2** | **0.33 (1/3)** | **0.67 (2/3)** | **0.67** | **+0.33** | Yes | settat_ca+benguerir_ca |

Source: `q2_critical_portfolio.csv` (re-run after HOS fix; unchanged). **Do not claim E beats F.**

### Table 2 — Six-OD depot portfolio (SOC 80%, 5.3 t)

| Vehicle | q | Budget | C ops | E ops | F ops | E−C | Mechanism |
|---|---:|---|---:|---:|---:|---:|---|
| eActros | 2 | B0 | 0.67 (4/6) | 0.67 | 0.67 | **0** | no new chargers serve 4/6 |
| eActros | 2 | B1 | 0.83 | 0.83 | 0.83 | **0** | +benguerir_ac |
| eActros | 2 | B2+ | **1.00 (6/6)** | **1.00** | **1.00** | **0** | benguerir_ac+ca |
| Volvo | 2 | B0 | 0.50 | **0.67** | 0.67 | **+0.17 (+1/6)** | route flexibility (zero sites) |
| Volvo | 2 | B1–Ball | 0.67 | **0.83** | 0.83 | **+0.17** | +benguerir_ca |

Source: `method_comparison_AF.csv`. Separate N agricultural vs S hypothetical ODs in mission CSVs.

**Mechanism split:** charger budgets raise eActros depot coverage 4/6→6/6 with **no** E−C gap; Volvo’s +1/6 is **route access**, not extra chargers at B0.

---

## Result B — Payload–SOC operating frontier

Executable q=5 frontier: **288** cells (not restored). Decisive q=2 subset: **91** cells.

### Agadir→Casablanca (best over AC ladder)

| Vehicle | Payload | SOC 50% (stress) | SOC 80% | SOC 100% |
|---|---|---|---|---|
| eActros | 5.3 / 10 t | unserved | served (≥1 AC) | served (even **0 AC** after rest fix) |
| eActros | **15 t** | unserved | **unserved (both AC)** | **served (≥1 AC)** |
| Volvo | 5.3 / 10 t | unserved | unserved | served (≥1 AC) |
| Volvo | 15 t | unserved | unserved | unserved |

**Not recoverable by more sites:** eActros 15 t @ 80% — confirmed at q=2 and q=1.  
**Recoverable by SOC, not sites:** same load @ 100% + one AC.

Sources: `payload_soc_frontier.csv`, `critical_q1_confirms.csv`.

---

## Result C — Route flexibility

| OD / case | Who benefits | Mechanism |
|---|---|---|
| Casa→Marrakech @ SOC **50%** | both vehicles, all 3 payloads | multi Y / fixed N (flex); **gone at SOC≥80%** |
| Marrakech→Agadir | eActros 15 t @ 80%; Volvo 15 t @ 100%; Volvo 5.3 t @ 80% (q=2) | **zero new chargers**; alternative route |
| Headline casa_marrakech SOC0.5 | both | drives E−C on 3-mission pilot |

Flex cells at SOC≥80%: **2** (marrakech_agadir heavy). At SOC 50%: **6** (all casa_marrakech).

Matched-time Δtrip median = **0** when both C and E are feasible — report **serviceability**, not travel-time savings. E=F on all tabulated budgets.

Source: `operational_efficiency.csv`, frontier summary table.

---

## Result D — Robustness

Pre-registered eActros matrix (Agadir→Casa multi; Casa→Marrakech multi/fixed): reserve 10–20%, charger 150–350 kW, hot weather, Cd/Crr ×1.10, payload 10–15 t.

| Finding | Survives? |
|---|---|
| Light/medium NB @ SOC80% + Benguerir AC | Yes under kW/hot/aero/roll/reserve |
| Casa→Marrakech @ depot SOC with Settat CA | Yes (multi and fixed) |
| **15 t NB @ SOC80%** | **No** (energy) |
| 15 t NB @ SOC100% | Yes |

Source: `robustness_matrix.csv`.

---

## Corrected q=2 confirmation inventory

Decisive subset (**91** cells; not all 288 screening cells):

| Metric | Count |
|---|---:|
| Agree on multi-route status | **90 / 91** |
| Agree on multi **and** fixed | **84 / 91** |
| Any method change | **7** |

### All 7 q5↔q2 changes

| Vehicle | OD | Payload | SOC | Infra | Multi q5→q2 | Fixed q5→q2 | Class |
|---|---|---:|---:|---|---|---|---|
| eActros | marrakech_agadir | 15 t | 0.8 | none / amskroud / +settat | T→T | **F→T** | fixed_only |
| Volvo | marrakech_agadir | 5.3 t | 0.8 | none | **F→T** | F→F | multi_only |
| Volvo | marrakech_agadir | 15 t | 1.0 | none / amskroud / +settat | T→T | **F→T** | fixed_only |

The previous “3 flips” claim is **withdrawn**; it omitted fixed-baseline changes and is obsolete after the HOS fix (the old eActros NB 5.3 t @ 100% multi Falses are gone).

Critical q=1: agrees with q=2 on all tested northbound and Marrakech→Agadir cells above.

Source: `payload_soc_frontier_q2_confirm.csv`, `publication_tables/table_q2_flip_inventory.csv`, `critical_q1_confirms.csv`.

---

## Amskroud / more sites

On-union only for `casa_agadir` and `marrakech_agadir`. Marginal ops gain remains rare. After the rest fix, **availability** of extra AC sites no longer falsely fails no-charge high-SOC northbound witnesses. Cases where a larger install scores worse than a singleton in ladder tables still mean that **that particular install’s energy-optimal itinerary** can differ; operational coverage for budgeted placement uses best subset under the enum score (fewer sites preferred when coverage ties).

---

## Final scientific decision

1. **Three strongest positives:** (i) headline q=2 E−C = +1/3 both vehicles; (ii) eActros 6-OD depot 4/6→6/6 with two directional Benguerirs; (iii) Volvo Marrakech→Agadir / 6-OD B0 route-flexibility gains with zero chargers; plus NB 15 t SOC 80%→100% flip.
2. **Exact vs optimized fixed-route C:** headline +1/3; Volvo 6-OD q=2 +1/6; eActros 6-OD depot **parity**.
3. **Survive 80–100% SOC & 10–15 t?** Casa→Marrakech flex: **no** at ≥80%. NB 10 t eActros @ 80%: **yes** with AC. NB 15 t @ 80%: **no**. NB 15 t @ 100%: **yes** with AC. Volvo heavier NB: limited.
4. **Infrastructure:** headline eActros needs **2 Benguerirs** for 3/3; 6-OD eActros same pair for 6/6; many high-SOC light legs need **0–1** site; rest may use verified ADM nodes without charging.
5. **Rest/grid artifacts:** independent-rest fix + q=1 agrees on critical cells; remaining flips are mostly **fixed-route improvements** at finer q on Marrakech→Agadir, not false infrastructure needs.
6. **Journal readiness:** mechanism-level OR evidence is **credible for a serious transportation-research journal** as a **conditional corridor pilot**, but still needs stronger empirical freight-demand / vehicle / grid validation before national policy claims.

---

## Paper data pointers

| Item | Path |
|---|---|
| Coverage vs budget | `q2_critical_portfolio.csv`, `method_comparison_AF.csv` |
| Payload–SOC | `payload_soc_frontier.csv`, `publication_tables/table_payload_soc_feasibility.csv` |
| q2 flips | `publication_tables/table_q2_flip_inventory.csv` |
| q1 critical | `critical_q1_confirms.csv` |
| Robustness | `robustness_matrix.csv` |
| Efficiency | `operational_efficiency.csv` |
| Crosswalk | `publication_tables/evidence_crosswalk.json` |
| Figures | `figures/fig1_*.png` … `fig4_*.png` |

---

## Bottom line for the manuscript

**Keep:** q=2-confirmed +1/3 headline gap; Benguerir two-site minimum for full eActros headline/6-OD depot coverage; E=F ties; zero matched-time savings; 15 t @ 80% northbound limit.

**Add:** independent rest at verified ADM nodes; Volvo zero-charger Marrakech→Agadir flexibility; explicit 7-cell q2 change inventory.

**Do not claim:** E beats greedy; universal depot-SOC multi-route need; Amskroud as general upgrade; national freight coverage.
