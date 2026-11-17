# PAPER_SCIENTIFIC_RESULTS_CAMPAIGN

**Critical assessment first:** the campaign **strengthens** the paper’s mechanism story, but it also **narrows** where the joint multi-route advantage is real. Headline B2 coverage gaps **survive q=2**. Under realistic depot SOC (80%), Casablanca→Marrakech flexibility disappears because fixed-route also becomes ops-feasible. Northbound Agadir→Casablanca at **15 t / 80% SOC remains unserved** even with both AC chargers—chargers do not rescue every heavy dispatch; **100% depot SOC** does. On the expanded 6-OD depot portfolio, eActros shows **E=C=F** (no joint gap), while Volvo at q=2 retains a **+1/6** E−C gap.

Primary metric: **operational coverage** = energy-feasible ∧ continuous replay ∧ schedule/HOS valid.  
Chargers = hypothetical HGV CCS. Scenario counts ≠ traffic samples.  
Artifacts: `results/paper_campaign/`.

---

## Experiment 0 — DEM recovery

Bounded COP-DEM GLO-30 sampling on verified OSM macros (`scripts/fetch_multiroute_dem.py --od-ids marrakech_casa,agadir_marrakech --max-alts 2 --merge-meta`):

| OD | dem_complete | On-union stations | Amskroud CA on union? |
|---|---|---|---|
| agadir_casa | True | settat_ac, benguerir_ac | No |
| marrakech_casa | True (recovered) | settat_ac, benguerir_ac | No |
| agadir_marrakech | True (recovered) | *(none — amskroud_ac missing)* | No |
| casa_agadir | True | settat_ca, benguerir_ca, **amskroud_ca** | **Yes** |
| casa_marrakech | True | settat_ca, benguerir_ca | No |
| marrakech_agadir | True | **amskroud_ca** | **Yes** |

Source: `results/paper_campaign/od_dem_site_audit.csv`.

---

## Table 1 — Headline E vs C vs F (q=2, 3-mission equal-weight)

Denominator: **3 equal-weight missions** (casa_marrakech SOC0.5, casa_agadir SOC0.5, agadir_casa SOC0.8; payload 5.3 t; cool tomato; 350 kW hyp. CCS; ops metric).

| Vehicle | Budget | C ops | E ops | F ops | E−C | E=F? | E sites |
|---|---|---:|---:|---:|---:|---|---|
| eActros | B0 | 0.00 | 0.00 | 0.00 | 0.00 | Yes | — |
| eActros | B1 | 0.33 | 0.67 | 0.67 | **+0.33** | Yes | benguerir_ca |
| eActros | **B2** | **0.67 (2/3)** | **1.00 (3/3)** | **1.00** | **+0.33** | Yes | both Benguerirs |
| eActros | B3/Ball | 0.67 | 1.00 | 1.00 | +0.33 | Yes | both Benguerirs |
| Volvo | B0 | 0.00 | 0.00 | 0.00 | 0.00 | Yes | — |
| Volvo | B1 | 0.00 | 0.33 | 0.33 | +0.33 | Yes | settat_ca |
| Volvo | **B2** | **0.33 (1/3)** | **0.67 (2/3)** | **0.67** | **+0.33** | Yes | settat_ca+benguerir_ca |
| Volvo | B3/Ball | 0.33 | 0.67 | 0.67 | +0.33 | Yes | settat_ca+benguerir_ca |

Source: `results/paper_campaign/q2_critical_portfolio.csv`.  
**Do not claim E beats F** — they tie at every budget. Primary comparator = **C**.

---

## Table 2 — Expanded 6-OD depot portfolio (SOC 80%, 5.3 t)

Demand: `realistic_depot_soc08_p5300` — six unique ODs (N+S panels), equal weight, depot SOC 80%.

| Vehicle | q | Budget | C ops | E ops | F ops | E−C | E=F? | E sites |
|---|---:|---|---:|---:|---:|---:|---|---|
| eActros | 5 | B0 | 0.67 | 0.67 | 0.67 | 0.00 | Yes | — |
| eActros | 5 | B1 | 0.83 | 0.83 | 0.83 | 0.00 | Yes | benguerir_ac |
| eActros | 5 | B2+ | **1.00** | **1.00** | **1.00** | 0.00 | Yes | benguerir_ac+ca |
| eActros | 2 | B0–Ball | same as q=5 | same | same | **0.00** | Yes | same |
| Volvo | 5 | B0 | 0.33 | 0.33 | 0.33 | 0.00 | Yes | — |
| Volvo | 5 | B1–Ball | 0.50 | 0.50 | 0.50 | 0.00 | Yes | benguerir_ca |
| Volvo | **2** | B0 | 0.50 | **0.67** | 0.67 | **+0.17 (+1/6)** | Yes | — |
| Volvo | **2** | B1–Ball | 0.67 | **0.83** | 0.83 | **+0.17** | Yes | benguerir_ca |

Source: `results/paper_campaign/method_comparison_AF.csv`.

**Interpretation:** under scheduled depot SOC, eActros joint placement adds **no** ops coverage vs optimized fixed-route (C catches up). Volvo’s q=2 gap is real but modest (+1 mission / 6). Headline E>C is therefore **stress-SOC / 3-mission-mix** specific, not a universal 6-OD depot result.

---

## Table 3 — Efficiency / flexibility types

| Comparison type | eActros | Volvo | Total |
|---|---:|---:|---:|
| serviceability_gain (E yes, C no) | 5 | 9 | **14** |
| matched_time (both feasible) | 60 | 36 | **96** |
| neither_or_C_only | 10 | 30 | 40 |

Source: `results/paper_campaign/operational_efficiency.csv` (refreshed from 6-OD + headline missions).  
Matched Δtrip_min median = **0** when both are feasible — do not invent travel-time savings; lead with **serviceability**.

---

## Table 4 — Payload × SOC frontier (q=5 screen; decisive q=2 confirms)

Frontier: 288 cells (144 eActros + 144 Volvo) across 4 ODs × 3 payloads × 3 SOCs × infra ladders.  
Decisive q=2 confirms: **143** cells; **97.2%** agree with q=5; **3** flips only (eActros `agadir_casa` 5.3 t @ SOC 100% with AC — borderline quantum effect, not a site-count headline).

### 4a. Casablanca→Marrakech flexibility (both vehicles)

| Payload | SOC 50% | SOC 80% | SOC 100% |
|---|---|---|---|
| 5.3 / 10 / 15 t | multi **Y**, fixed **N** (**flex**) | multi Y, fixed **Y** | multi Y, fixed Y |

Flexibility ops-gains at SOC≥80%: only **2** cells overall (`marrakech_agadir` heavy), not Casa→Marrakech.  
At SOC 50%: **6** flex cells, all Casa→Marrakech.

### 4b. Agadir→Casablanca multi-route (best over AC ladder)

| Vehicle | Payload | SOC 50% | SOC 80% | SOC 100% |
|---|---|---|---|---|
| eActros | 5.3 / 10 t | unserved | **served** (needs ≥1 AC) | served |
| eActros | **15 t** | unserved | **unserved (both AC)** | **served** (needs charger) |
| Volvo | 5.3 / 10 t | unserved | unserved | **served** (needs charger) |
| Volvo | 15 t | unserved | unserved | unserved |

**Effect size (eActros):** 15 t northbound SOC 80%→100% flips ops **0→1** under identical sites; extra AC site cannot rescue 80%. Confirmed at q=2.

Sources: `payload_soc_frontier.csv`, `payload_soc_frontier_q2_confirm.csv`.

---

## Robustness matrix (eActros, pre-registered)

Targets: Agadir→Casa multi with Benguerir AC (± Settat AC); Casa→Marrakech multi/fixed with Settat CA. q ∈ {5,2}.

| Cell | Agadir→Casa ops (q=2, 1 AC) | Casa→Marrakech multi/fixed |
|---|---|---|
| base (5.3 t, SOC80%, 350 kW, cool, reserve10%) | **True** | True / True |
| reserve 15% / 20% | True | True / True |
| charger 250 / 150 kW | True | True / True |
| hot weather | True | True / True |
| Cd ×1.10 / Crr ×1.10 | True | True / True |
| payload 10 t @ SOC80% | True | True / True |
| **payload 15 t @ SOC80%** | **False** | True / True |
| payload 15 t @ SOC100% | **True** | True / True |

Source: `results/paper_campaign/robustness_matrix.csv` (88 rows; speed-policy patch applied).  
**Survives** moderate kW / hot / aero / rolling / reserve shocks at light depot northbound. **Breaks** only at the pre-registered 15 t @ 80% stress — same frontier Finding C.

---

## Infrastructure required / Amskroud CA

Headline eActros (ops, q=2): **0→0/3**, **1 site (benguerir_ca)→2/3**, **2 sites (both Benguerirs)→3/3** minimum for full headline coverage.

6-OD depot eActros: same Benguerir AC+CA pair reaches **6/6** at B2.

Amskroud CA on-union only for `casa_agadir` and `marrakech_agadir`. Marginal ops gain vs best non-Amskroud ladder: **1/27** cells (`casa_agadir`, 15 t, SOC 50%). Larger installs including Amskroud can **lose** ops vs Benguerir-only. Not a general coverage upgrade.

Source: `amskroud_ca_value.csv`.

---

## Charging / rest / refrigeration credibility

- Chronological HOS pads at verified stops; traces in mission CSVs.
- Firm-ripe tomato cool scenario retained (not inflated).
- 350 kW hyp. station with vehicle CCS cap; taper = research envelope, not OEM-measured.
- q=2 decisive confirms: **143** cells, **97.2%** q5 agreement; 3 borderline `agadir_casa` 5.3 t @ SOC100% flips only.

---

## What generalizes vs case-specific?

| Generalizes | Case-specific |
|---|---|
| Ops metric must include schedule | Headline SOC0.5 southbound mix |
| E ties F on these candidate sets | Exact Benguerir pair as unique optimum |
| Depot SOC is a first-order lever | 15 t @ 80% northbound failure |
| Flexibility helps low-SOC Casa→Marrakech | Marrakech flex at SOC≥80% |
| More sites ≠ always more ops | Amskroud-inclusive installs |
| E>C on stress headline | E=C on 6-OD eActros depot portfolio |

---

## Stronger than the prior 3-mission pilot?

**Yes for scientific honesty; mixed for coverage marketing.**

Completed: q=2 headline both vehicles; DEM recovery; full Volvo+eActros payload×SOC frontier (288) + decisive q=2 confirms (143); 6-OD A–F at q=5 and q=2; robustness matrix; Amskroud on-union test; figures refreshed.

Manuscript should lead with **conditional serviceability and infrastructure efficiency**, not a single 100% coverage slogan.

---

## Remaining barriers to journal submission

1. No observed OD truck counts / charger uptime / grid capacity.  
2. Axle compliance unverified; ADM HGV access unknown.  
3. `agadir_marrakech` has DEM but no validated AC charger without inventing `amskroud_ac`.  
4. CCS taper is a research envelope, not OEM-measured.  
5. Equal / illustrative weights ≠ Moroccan traffic sample.

---

## Paper data pointers

| Item | Path |
|---|---|
| Table 1 Headline E/C/F | `results/paper_campaign/q2_critical_portfolio.csv` |
| Table 2 Expanded 6-OD | `results/paper_campaign/method_comparison_AF.csv` |
| Table 3 Efficiency | `results/paper_campaign/operational_efficiency.csv` |
| Table 4 Frontier + q2 | `payload_soc_frontier.csv`, `payload_soc_frontier_q2_confirm.csv` |
| Robustness | `results/paper_campaign/robustness_matrix.csv` |
| Fig1 | `results/paper_campaign/figures/fig1_coverage_vs_budget_*.png` |
| Fig2 | `results/paper_campaign/figures/fig2_payload_soc_*_*.png` |
| Fig3–4 | `figures/fig3_flexibility_and_time.png`, `fig4_infra_robustness.png` |
| Frozen registry | `results/paper_campaign/scenario_registry_frozen.csv` |

---

## Bottom line for the manuscript

**Keep:** q=2-confirmed +1 mission ops gap of joint/greedy vs optimized fixed-route on the equal-weight pilot; Benguerir-directed two-site minimum for 3/3 eActros; schedule-valid coverage as the service metric.

**Reframe:** Marrakech multi-route benefit as **stress-SOC dispatch**, not automatic at depot SOC; 6-OD depot eActros as **E=C=F**.

**Add:** northbound 15 t frontier + robustness — infrastructure alone insufficient without adequate departure SOC; Volvo q=2 6-OD gap (+1/6) as secondary, finer-grid result.

**Do not claim:** E beats greedy; Amskroud as generally material; national freight coverage from this corridor pilot.
