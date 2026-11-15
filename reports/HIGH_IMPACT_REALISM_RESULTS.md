# HIGH_IMPACT_REALISM_RESULTS

Date: 2026-11-15  
Git SHA (base): `22f2a0ca618e14d38d11324da3024c9a6d96a798` (sprint edits may be uncommitted)  
Speed policy under peak adaptation: **40 km/h floor** (`min_adapt_speed_kmh`) — segments that cannot be climbed at ≥40 km/h are power-infeasible (no walking-speed crawl).  
Schedule validation uses **physical** continuous-replay `dt_s`, not rounded 5-minute routing steps.  
eActros CCS acceptance cap: **400 kW** (manufacturer public constant envelope).

This package prioritizes transportation decisions (coverage, infrastructure efficiency, operational time) under realistic physics. Numerical certification is a reliability gate, not the selling point.

---

## 1. Strongest experimentally supported positive findings

### Finding 1 — Route flexibility restores Casa→Marrakech service (ops-credible)

Under identical infrastructure `{settat_ca, benguerir_ca}`, SOC₀=0.5, payload 5300 kg, q=5, refrigerated, peak-adapt with 40 km/h floor:

| OD | Truck | Fixed-shortest | Multi-route | Ops-credible multi | Detour |
|---|---|---|---|---|---:|
| casa_marrakech | eActros 600 | INFEASIBLE | OPTIMAL | **yes** | **+20.9 km (8.8%)** |
| casa_marrakech | Volvo 475 | INFEASIBLE | OPTIMAL | **yes** | **+20.9 km (8.8%)** |
| casa_agadir | Volvo 475 | OPTIMAL | OPTIMAL | yes (both) | 0% |

**Mechanism (Casa→Marrakech):** fixed shortest does not visit active charger nodes; multi-route detours ~8.8% to charge at Settat. Min arc speed = 60 km/h; physical drive ≈199.7 min vs discrete 220 min (Δ ≈ −20.3 min); schedule OK; audit + continuous replay OK; min SOC ≈0.145 (eActros) / 0.156 (Volvo); charge 105 / 160 kWh.

**Honest exception (Casa→Agadir):** with peak-adapt ≥40 km/h, the previous sprint-01 “fixed INFEASIBLE → multi OPTIMAL” gain **does not persist** — fixed-shortest becomes OPTIMAL on the same graph. Sprint-01 Agadir H1 was run without peak adaptation. Do not claim Agadir route-flexibility gain under the realism gates.

Artifact: `results/high_impact_h1_realism.csv`

### Finding 2 — Joint multi-route placement doubles B1 coverage vs fixed-route planning

Equal-weight 3-mission eActros corridor portfolio (DEM-complete path-union, max_alts=2):

1. Casa→Marrakech SOC 0.5 refrigerated  
2. Casa→Agadir SOC 0.5 refrigerated  
3. Agadir→Casablanca SOC 0.8 refrigerated  

Direction-specific grounded candidates: `settat_ca`, `benguerir_ca`, `settat_ac`, `benguerir_ac`.

| Budget | B fixed+conventional | C fixed+optimized | D multi+conventional | **E joint multi opt** | F greedy multi |
|---|---:|---:|---:|---:|---:|
| B0 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 |
| **B1** | 0.33 | 0.33 | **0.67** | **0.67** (`settat_ca`) | 0.67 |
| **B2** | 0.33 | 0.67 | 0.67 | **1.00** (`settat_ca`+`benguerir_ac`) | 1.00 |
| B3 | 0.33 | 0.67 | 0.67 | **1.00** (same 2 sites) | 1.00 |
| Ball | 0.67 | 0.67 | 1.00 | **1.00** (same 2 sites) | 1.00 |

**Transportation reading:**

- At one-site budget, **multi-route + Settat CA serves 2/3 missions (67%)**; fixed-route with the same site serves only **1/3 (33%)** — Casa→Marrakech still needs route flexibility.
- Full coverage requires **two directed sites** (`settat_ca` + `benguerir_ac`); joint optimization finds this at B2. Fixed-route planning **never exceeds 67%** even with all four sites (Casa→Marrakech remains fixed-infeasible).
- Greedy multi matches joint optimum on coverage at B2+ (report parity honestly). Conventional Settat-pair ordering wastes budget on the wrong carriageway.

**Operational metrics on E@B2 certified missions:**

| Mission | Road (km) | Phys drive (min) | Charge (min) | min SOC | Schedule OK |
|---|---:|---:|---:|---:|---|
| Casa→Marrakech | 257.8 | 199.7 | 20 | 0.146 | yes |
| Casa→Agadir | 445.6 | 339.7 | 70 | 0.162 | no (HOS clock) |
| Agadir→Casa | 429.2 | 322.1 | 30 | 0.235 | no (HOS clock) |

Artifacts: `results/high_impact_corridor_portfolio.csv`, `results/high_impact_coverage_vs_budget.csv`, `results/figures/high_impact_coverage_vs_budget.png`

### Finding 3 — Reserve-SOC “15% cliff” was a coarse-grid artifact

Northbound Agadir→Casablanca, Benguerir, SOC₀=0.8, eActros, peak-adapt 40 km/h:

| Policy | q | Discrete status (Benguerir) | Continuous min SOC |
|---|---:|---|---:|
| 10% rebuild | 5 | OPTIMAL | **0.235** (meets 15% and 20% physically) |
| 10% rebuild | 2 | OPTIMAL | 0.150 (meets 15%, not 20%) |
| 15% rebuild | 5 | **INFEASIBLE** | — |
| 15% rebuild | 2 | **OPTIMAL** | 0.199 |
| 20% rebuild | 5 | INFEASIBLE | — |
| 20% rebuild | 2 | **OPTIMAL** | 0.235 |

**Corrected claim:** do **not** assert that a 15% reserve is physically impossible from q=5 discrete unserved alone. Finer battery resolution (q=2) restores OPTIMAL service at 15% and 20%. The q=5 10% physical witness already has min SOC 23.5%.

Artifact: `results/high_impact_reserve_soc_witness.csv`

---

## 2. Evidence and physical validity

- Same canonical DEM graph; fixed vs multi via `allowed_arc_ids` (no rebuild).
- Certified service requires discrete replay + continuous replay + `audit_solved_actions_exact`.
- Physical HOS screen: 45 min break after 4.5 h continuous driving, timed from replay `dt_s`.
- Speed: min adapted arc speeds on successful H1/portfolio trips = **60 km/h**; fraction of time below 40 km/h = 0.
- Sites: ADM-named service areas with verified directed OSM access; chargers remain **hypothetical** HGV CCS (no grid-capacity claim).
- `marrakech_casa` excluded from portfolio: `dem_complete=False` on verified path-union (not fabricated).
- Path-union capped at **2** verified alternatives (alts=4 pulled DEM-incomplete arcs and invalidated certification).

---

## 3. Fair comparisons against alternative planning methods

| ID | Method |
|---|---|
| A | No new infrastructure |
| B | Fixed-shortest + conventional site order (Settat CA/AC then Benguerir) |
| C | Fixed-shortest + optimized sites under budget |
| D | Multi-route + conventional sites |
| E | Joint multi-route optimized placement |
| F | Greedy multi-route marginal coverage |

Mission population fixed before viewing outcomes. Equal weights (documented proxies, not observed freight counts).

---

## 4. Sensitivity ranges and exceptions

- **Casa→Agadir H1 gain** disappears under peak-adapt + 40 km/h (report as exception).
- **Long northbound/Agadir trips:** physical drive ~322–340 min exceeds 4.5 h; `schedule_phys_ok=False` when charge/rest timing does not reset the continuous-driving clock — energy-feasible ≠ fully HOS-feasible. Charge/rest overlap can be 45 min when the stop is long enough (Casa→Agadir charge ≈70 min).
- **Refrigeration:** under cool tomato assumptions, refrigeration energy remains small vs traction (do not inflate).
- **Reserve:** q=5 vs q=2 disagree on discrete 15%/20%; physical witness reconciles.

---

## 5. Remaining scientific weaknesses

- Three-mission equal-weight portfolio is a corridor research proxy, not nationwide Moroccan OD demand.
- No observed annual freight weights; no grid-capacity evidence.
- OEM SOC-dependent CCS taper unavailable — constant envelope only.
- Moroccan axle-law compliance unverified.
- HOS validator screens/pads; it does not yet **re-optimize** stop placement.
- Volvo vehicle panel for the full portfolio not yet run.
- Pre-registered aero/rolling/DEM-noise robustness matrix still pending.

---

## 6. Journal-contribution assessment

**Supportable contribution (with these numbers):**

1. **Routing:** energy-aware multi-route planning is an operational coverage instrument — Casa→Marrakech refrigerated HGV service with 8.8% detour under realistic speed and physical-time HOS screens.
2. **Infrastructure:** under a fixed one-site budget, multi-route placement serves **twice** the weighted missions of fixed-route planning on the same candidate; full corridor coverage needs **two directed sites**, and fixed-route methods cannot recover the Marrakech mission even with all candidates.
3. **Methodology integrity:** reserve-SOC and Agadir H1 corrections show willingness to withdraw over-claims when realism/finer grids change the story — strengthens trustworthiness.

This is closer to a persuasive transportation paper than a “numerical failures” paper, provided the manuscript leads with Findings 1–2 and treats certification/discretization as validation.

---

## 7. Prioritized remaining experiments

**Completed in §8:** H1 q=2, Volvo portfolio, HOS pad analysis, robustness matrix, refrigeration/taper audits.  
**Still deferred:** full DEM-noise Monte Carlo; system/integration CI in remote pipeline; **manuscript revision** only after accepting these CSVs.

---

## Reproduction

```bash
python -m pytest tests/unit -q
python scripts/run_high_impact_realism_sprint.py --phase h1 --q 5
python scripts/run_high_impact_realism_sprint.py --phase h1 --q 2
python scripts/run_high_impact_realism_sprint.py --phase portfolio --q 5
python scripts/run_high_impact_completion.py --phase all --q 5
```

## Artifacts

- `results/high_impact_h1_realism.csv` (q=5 and q=2)
- `results/high_impact_reserve_soc_witness.csv`
- `results/high_impact_corridor_portfolio.csv` / `high_impact_coverage_vs_budget.csv`
- `results/high_impact_volvo_portfolio.csv` / `high_impact_volvo_coverage_vs_budget.csv`
- `results/high_impact_robustness_matrix.csv`
- `results/high_impact_refrigeration_audit.csv`
- `results/high_impact_charging_taper.csv`
- `results/high_impact_hos_rest_adjustment.csv`
- `results/figures/high_impact_*.png`
- `configs/optimization/multiroute_placement_corridor_portfolio.yaml`
- `reports/HIGH_IMPACT_REALISM_RESULTS.md`

## 8. Completion addendum

Generated by `scripts/run_high_impact_completion.py`. Git: `22f2a0ca618e14d38d11324da3024c9a6d96a798`.

### 8.1 H1 at q=2
H1 at q=2: route-flexibility gains in **2/3** charged cells (both Casa→Marrakech trucks; ops-credible). Casa→Agadir remains fixed+multi OPTIMAL (no flexibility gain) but the q=2 multi solution is **not** ops-credible (`schedule_phys_ok=False`, continuous driving 330.7 min) — energy-feasible ≠ HOS-feasible.

### 8.2 Pre-registered robustness matrix (northbound + Benguerir)
Cells fixed before outcomes: base SOC0.8, SOC0.5, payload 10 t, reserve 15%/20%, charger 250 kW, hot weather, Cd×1.10, Crr×1.10.

Benguerir subset status:
- R0_base: OPTIMAL
- R1_soc05: INFEASIBLE
- R2_payload10t: INFEASIBLE
- R3_reserve15: INFEASIBLE
- R4_reserve20: INFEASIBLE
- R5_chg250: OPTIMAL
- R6_hot: OPTIMAL
- R7_aero110: OPTIMAL
- R8_roll110: OPTIMAL

Artifact: `results/high_impact_robustness_matrix.csv`, figure `results/figures/high_impact_robustness_heatmap.png`.

### 8.3 Refrigeration realism audit
Modeled TRU electrical power at setpoint 9°C / UA=80: 0.373 kW at 20°C ambient vs 1.182 kW at 35°C (EPRI e-TRU average ~8 kWh/h; CE Delft electric standby ~9.8 kWh/h at 0°C). Low cool-corridor load is a legitimate consequence of chilled tomato setpoint + modest UA + precooled cargo — not inflated.

Literature anchors: EPRI e-TRU ~5–19 kW (avg ~8 kWh/h); CE Delft (2016) electric standby continuous ~9.8 kWh/h at 0°C / 6.3 at −20°C; Bank et al. 2025 methodological inspiration only (not a calibrated reproduction). Operational relevance rises under **hot ambient** and higher UA — quantify, do not inflate cool-corridor duty.

Artifact: `results/high_impact_refrigeration_audit.csv`.

### 8.4 Charging taper sensitivity
Conservative SOC-dependent CCS envelope (OEM curve unavailable): full power to 60% SOC, derate to 70% by 80% SOC, to 35% by 95% SOC. Default planning remains constant min(charger, CCS cap). Time penalty for 100 kWh battery energy grows sharply above 80% SOC — see `results/high_impact_charging_taper.csv`.

### 8.5 HOS rest adjustment (executable pad, not re-optimizer)
Distinguishes energy feasibility from full operational feasibility. Pads include aux + refrigeration energy.

- casa_agadir/volvo_475: sched_ok=True, pad=0.0 min at `nan`, pad energy=0.0 kWh, ops_with_pad=True
- agadir_casa/eactros_600: energy OK but HOS fail — first stop (`settat_ac`) arrives **after** 4.5 h continuous driving; a 45 min pad there (≈2.15 kWh aux+fridge) cannot cure a past exceedance without an earlier rest site or route change (`ops_with_pad=False`)
- casa_marrakech/eactros_600: sched_ok=True, pad=0.0 min at `nan`, pad energy=0.0 kWh, ops_with_pad=True

Artifact: `results/high_impact_hos_rest_adjustment.csv`.

### 8.6 Volvo corridor portfolio
Volvo portfolio: B1 E=0.33, B2 E=0.67.

Artifacts: `results/high_impact_volvo_portfolio.csv`, `results/high_impact_volvo_coverage_vs_budget.csv`.

### 8.7 Literature context (what strong papers quantify)
Published BET corridor / location–routing work typically reports: **flow capture / coverage vs budget**, **number of stations** (often diminishing returns), **detour / deadhead**, **HOS-compatible feasible routes**, and sometimes **grid/capacity** constraints (e.g. Fraunhofer ISI European charging networks; Norwegian stochastic location under demand/grid uncertainty; Swedish spatio-temporal en-route energy placement; Batteries 2025 zero-carbon corridor MILP + queueing calibration). Our Moroccan contribution aligns with coverage-vs-budget and HOS/energy-constrained routing, while adding **DEM physics + refrigerated TRU + directed service-area access** on a specific corridor — not a claim of nationwide observed OD optimization.

### 8.8 Remaining after completion pass
- Full system/integration CI beyond unit (run separately in CI).
- DEM noise Monte Carlo still light (not a full uncertainty set).
- Manuscript revision still deferred until these CSVs are accepted as trustworthy.
