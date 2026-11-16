# Paper Scientific Results Campaign — Plan (for review)

**Status:** awaiting approval before execution  
**Base commit:** `0a8d56b`  
**Overview:** Pre-register an expanded DEM-validated Moroccan refrigerated freight portfolio, then run q=2 confirmation, payload×SOC frontiers, matched A–F comparisons, and robustness using existing MRLS/ops-coverage machinery—producing paper tables/figures and `PAPER_SCIENTIFIC_RESULTS_CAMPAIGN.md` with verified effect sizes.

## Scientific stance (locked)

- Primary application: **northbound Souss-Massa refrigerated tomato export corridor** (illustrative planning scenarios). Context cites WITS/Comtrade 2025 tomato exports (~747.7 kt; ~US$1.38B) and regional dominance of Souss-Massa; **do not treat export tonnes as Agadir→Casablanca truck OD counts**.
- Primary metric remains **operational coverage** (energy + continuous replay + schedule/HOS valid), already implemented in `scripts/run_final_operational_correction.py`.
- Comparator hierarchy: **C (fixed + optimized sites) is the main baseline**; B is diagnostic only. Report E vs F ties honestly.
- No solver/architecture rewrite. One thin campaign runner that reuses `evaluate_mission_operational` / subset evaluation / chronological HOS.

## What the repo already supports

- Path alternatives exist for all six ODs in `data/processed/multiroute/path_alternatives.csv` (4 alts each).
- **DEM-complete ODs (scientific use):** `agadir_casa`, `casa_agadir`, `casa_marrakech`, `marrakech_agadir`.
- **DEM-gated out (data gap, not physics failure):** `marrakech_casa`, `agadir_marrakech` (no DEM arcs in `dem_sampling_meta`; keep excluded).
- Topology-validated ADM candidates in `data/processed/candidate_sites.csv`: **`settat_ca/ac`, `benguerir_ca/ac`, `amskroud_ca`**. Exclude Marrakech ADS, Oum Rbii (unresolved), Berrchid (opposite carriageway), `amskroud_ac` (no validated entrance/exit).
- Current paper portfolio is only three light-payload missions in `configs/optimization/multiroute_placement_corridor_portfolio.yaml`.
- Reuse path confirmed: loop `prepare_multiroute_placement_context` → `evaluate_mission_operational` (ops+HOS); do **not** use energy-only robustness for frontier claims.

## Pre-registered design (before seeing outcomes)

### Experiment 1 — OD / site audit then portfolio

1. Confirm `dem_complete` under `max_alternatives_for_union=2` for the four expected-complete ODs; re-document the two DEM gaps.
2. Locked panels (no mixing into one “Morocco freight” claim):
   - **Panel N (northbound priority):** `agadir_casa` (flagship agricultural flow). Segment `marrakech_casa` / `agadir_marrakech` stay out until DEM exists.
   - **Panel S (return / southbound research):** `casa_agadir`, `casa_marrakech`, `marrakech_agadir`.
3. Expand beyond three missions by pre-registering **distinct ODs + labeled dispatch scenarios** (e.g. Panel S three ODs × SOC 0.8 @ 5.3 t; Panel N `agadir_casa` @ 5.3/10/15 t × SOC 0.8/1.0 as scenario rows, not fake independent OD demand).
4. Freeze scenario registry CSV **before** solving.

Weights: equal within each panel for unweighted coverage counts; optional illustrative northbound-priority weights reported separately and labeled non-observed.

### Experiment 2 — Feasibility frontier (highest priority after q=2 check)

For each vehicle ∈ `{eactros_600, volvo_475}` and each DEM-complete OD:

- Payload ∈ `{5300, 10000, 15000}` kg (flag `legal_mass_status` from existing gross-mass screen; axle unverified).
- Departure SOC ∈ `{0.5, 0.8, 1.0}` (0.8/1.0 = scheduled depot charge; 0.5 = stress).
- Reserve ∈ `{0.10, 0.15, 0.20}` on a reduced site ladder first.
- Infrastructure ladder (no post-hoc site invention): `none`, optimized-1, optimized-2, all direction-valid candidates for that OD (CA: up to Settat/Benguerir/Amskroud; AC: Settat/Benguerir only).

Screen at **q=5**; re-evaluate every **frontier-changing** cell at **q=2**. Record ops-served, energy-only, min/arrival SOC, charge events/time, HOS pad, road km.

### Experiment 3 — Matched A–F comparison

On a **fixed mission population** (Panel N + Panel S at a pre-registered representative dispatch: payload 5.3 t and 10 t; SOC 0.8 for northbound, SOC 0.8 for southbound primary; SOC 0.5 retained only as stress rows, not as the headline dispatch):

- Methods A–F as specified; budgets B0–B3/Ball.
- Candidate set for placement: validated four-site corridor **plus** `amskroud_ca` for CA-direction missions only.
- Exhaustive enum for E when |S|≤5; independent greedy for F; do not call enum a B&B result.
- Primary contrast: **E/F vs C** (same physics). Report all ties.

### Experiment 4 — Operator-relevant efficiency

For every mission where **both C and E are ops-feasible** under identical install (or under each method’s own B2 optimum, clearly labeled):

- Trip duration, drive/charge/wait, charge overlapping qualifying rest, detour km vs shortest, min SOC margin, cool vs hot fridge (existing firm-ripe tomato YAML + hot weather cell).
- If only E is feasible: report **serviceability gain**, not fake % time savings.

### Experiment 5 — Robustness

Pre-registered moderate matrix: payload, SOC, ambient/fridge, charger `{150,250,350}` kW, Cd/Crr ±10%, reserve, taper sensitivity on actual charge intervals. Principal A–F coverage curves at **q=2**; q=1 only on borderline site-count flips.

## Implementation (minimal)

- New focused script: `scripts/run_paper_scientific_results_campaign.py` wrapping existing APIs from `scripts/run_final_operational_correction.py`.
- New config: `configs/optimization/paper_scientific_portfolio.yaml`.
- Outputs under `results/paper_campaign/`:
  - `od_dem_site_audit.csv`
  - `q2_critical_portfolio.csv`
  - `payload_soc_frontier.csv`
  - `method_comparison_AF.csv`
  - `operational_efficiency.csv`
  - `robustness_matrix.csv`
  - figures `fig1_coverage_vs_budget.png` … `fig4_infra_robustness.png`
- Final narrative: `reports/PAPER_SCIENTIFIC_RESULTS_CAMPAIGN.md`.

## Execution order

1. OD/DEM/site audit + freeze registry.
2. **q=2 critical check** of current eActros/Volvo B2 E vs C (confirm 3/3 vs 2/3 and 2/3 vs 1/3 survive).
3. Payload×SOC frontier (q=5 screen → q=2 confirmation of flips).
4. Expanded matched A–F + efficiency.
5. Robustness + figures + campaign report.

## Honest-expectation guardrails

- If heavier payloads erase the joint advantage, report that and identify which legitimate levers (depot SOC, validated extra CA site Amskroud, rest/charge overlap) restore service—without weakening physics.
- National tomato exports contextualize application only; scenario counts ≠ traffic samples.
- Manuscript polish only if needed to cite new tables/figures after results exist.
