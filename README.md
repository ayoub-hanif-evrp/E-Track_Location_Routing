# E-Track_Location_Routing

**Paper campaign (authoritative numerics):** `results/paper_campaign/` + `reports/PAPER_SCIENTIFIC_RESULTS_CAMPAIGN.md` + `paper/manuscript.tex`.

## One-command path: clone → tests → regenerate paper tables

```bash
pip install -e ".[dev]"
# Optional: restore ~95MB graph CSVs for nesting/physics tests (CI uses GRAPH_ARTIFACT_URL secret)
python scripts/pack_multiroute_graph_artifact.py   # local pack → artifacts/multiroute_graph.zip
pytest -q -m "not integration"
python scripts/run_stage_c_hos_national.py --phase headline_enum   # Gate 2; multi-hour/day
python scripts/run_stage_c_hos_national.py --phase post_portfolio  # ablation, q1, blind, cert, manifest
python scripts/run_paper_scientific_results_campaign.py --phase frontier --confirm-mode decisive
python scripts/run_paper_scientific_results_campaign.py --phase robustness
python scripts/run_paper_scientific_results_campaign.py --phase figures
python scripts/run_paper_scientific_results_campaign.py --phase report
python scripts/run_stage_d_release_package.py
```

`headline_enum` runs full HOS-aware A–F exhaustive enum (pipeline `hos_in_search_full_enum`) with uniform 600~s / 500k limits.
`post_portfolio` rebuilds matched ablation, LIMIT retry, q=1 boundary, blind greedy, larger-instance cert, stability, mini panel, and `campaign_manifest.json`.
`all_fast` is the frozen-site rescore path (legacy); prefer `headline_enum` + `post_portfolio` for submission tables.

Authoritative numerics: `results/paper_campaign/` + `campaign_manifest.json` + `paper/claims_to_results_crosswalk.csv`.
Graph CSVs (`nodes.csv`/`edges.csv`) are not always in git (push size); pack with `pack_multiroute_graph_artifact.py` and host as a release asset for CI.

---
**Provisional title:** Joint Charging Infrastructure Placement and Energy-Feasible Routing for Electric Refrigerated Heavy-Duty Trucks on Moroccan Motorway Corridors

PhD research codebase (Casablanca, Morocco). **Task 01** builds a reproducible real-data foundation for the Casablancaâ€“Agadir motorway corridor. It does **not** solve the joint locationâ€“routing optimization problem.

## Scientific objective

Eventually determine which Moroccan motorway service areas should receive truck-compatible charging infrastructure, which routes electric refrigerated heavy-duty trucks should follow, where/how much to charge, and which freight missions are energy-feasible.

## Current scope (Tasks 01â€“08 freeze)

**Task 01 / 01B / 01C â€” geographic foundation**

- Download a **dated** Geofabrik Morocco OSM extract (cached + SHA-256).
- Extract a buffered Casablancaâ€“Agadir pilot region.
- Build a **directed** motorway graph with real lengths and OSM attributes.
- Identify **ADM-directory** corridor service areas as **candidate** future charger sites (not verified e-truck chargers).
- Direction-aware OSM matching; unresolved sites are never given invented coordinates.
- Shortest-distance baseline paths Casablanca â†” Agadir on **separate directed A3 carriageway components**.
- Access audit: provisional topological matches only (see open issue below).

**Task 02 / 02B â€” physics-based energy model (no optimization)**

- Longitudinal traction + aux + approximate refrigeration energy for an **eActros 600** refrigerated combination.
- Constant cruise **80 km/h** (OSM `maxspeed` not used as travel speed); peak-motor exceedances flagged (no silent power clip).
- Path-wise SOC feasibility (min SOC / first violation); invalid DEM â†’ indeterminate mission status.
- Terrain: AWS open **COP-DEM GLO-30** with bounds-aware sampling + quality gates (flat-road baseline always retained).
- Weather: **Open-Meteo** historical cache; vector-mean daily wind.
- Refrigeration configs **A** (tractor battery) / **B** (independent trailer pack); GCM labels (not â€œpayloadâ€).
- Pilot CSV + figures; methodology, validation, and Task 02B audit/diagnostics reports.
- **Not claimed:** calibrated TRU reproduction, OEM coast-down parameters, empirical trip validation, or charger-feasible routing.

**Task 03A â€” multi-resource label-setting (MRLS) routing solver**

- Custom discrete MRLS with DRIVE / CHARGE / WAIT; active stations are **inputs** (no placement B&B yet).
- Exactness only for the **finite integer-grid** synthetic problem (1 kWh / 5 min); validated vs an independent exhaustive reference on cases Aâ€“J.
- Incremental physics adapter `apply_drive` (incoming SOC) bridges Task 02B without copying force equations into the router.
- **Not claimed:** continuous charging optimality, Moroccan network optimality, or certified operational chargers at ADM sites.

**Task 03B â€” Moroccan corridor charging-stop pilot**

- Validation gates: dominance stress `K`, transition oracle, instance validation, solution replay.
- Fixed A3 baselines â†’ macro-arcs with **state-dependent DRIVE tables** (conservative floor-kWh / ceil-time); edge/macro-local terrain (no misused global DEM `s_cursor`).
- Hypothetical `entrance_and_exit` chargers only; S1â€“S5 experiments + continuous physics replay.
- **Not claimed:** certified HGV access, multi-path LRP, or continuous optimality beyond replay checks.

**Task 04A â€” Charging-grid fix + exact placement enumeration**

- Action-level stationary Wh drains + quantum-floor after CHARGE/WAIT; fingerprinted DRIVE-table cache.
- Exhaustive evaluation of all **32** subsets of five directional hypothetical sites; lex coverage-then-cost objective under illustrative budgets.
- **Not claimed:** market CAPEX/tariffs or certified HGV chargers.

**Task 04B â€” Certified placement branch-and-bound + MRLS**

- Full terrain fingerprint; global certification statuses; serviceability taxonomy (`peak_motor` structural only).
- Install/exclude B&B with proved budget, coverage UB, and secondary LB pruning; MRLS memoization.
- Matches all **32** Task 04A scenario optima; synthetic 12-site pruning demo.
- **Not claimed:** market prices, nationwide LRP, or metaheuristics/MIP solvers.

**Task 05A â€” Multi-route Moroccan freight discovery**

- Stage-1 B&B safeguards; separate expanded OSM graph under `data/processed/multiroute/`.
- Verified path alternatives for Casaâ†”Marrakechâ†”Agadir (discovery milestone).
- **Not claimed:** physics-integrated multi-route optimality (see 05B).

**Task 05B â€” Physics-validated multi-route MRLS**

- Audited path-union decision graph (`arc_id`, canonical aliases, length checks).
- OD-local path-union MRLS with Task 02B/03B DRIVE tables (not artificial `Oâ†’R_iâ†’D`).
- Grounded ADM hypothetical chargers only; continuous replay of OSM-edge journeys.
- Pilot ODs: Casaâ†’Marrakech, Casaâ†’Agadir, Marrakechâ†’Agadir.
- **Not claimed:** full-network optimality, certified HGV access, or joint placement (see 05C).

**Task 05C â€” Corrected station coupling + joint B&Bâ€“MRLS**

- Direction-specific ADM attach (`travel_direction` + OSM id); no wrong-carriageway proximity snap.
- Fixed path-union graph across install subsets (activate/deactivate only); DEM parent-slice after splits.
- Continuous-replay certification (deadline, SOC floors, DEM completeness).
- Joint placement: exhaustive enum vs existing B&B on a small multi-route portfolio.
- **Not claimed:** certified HGV access, nationwide optimality, or new metaheuristics.

**Task 06A â€” Speed policy + energy-grid validation**

- Per-OSM-hop research cruise speeds enter `apply_drive` (class defaults; OSM maxspeed not used as HGV cruise).
- DRIVE-table fingerprint `06a.1` includes speed schedule; no silent `E_init` bump.
- Grid sensitivity + discrete vs continuous feasibility audit; placement enumâ†”B&B revalidated.
- **Not claimed:** observed truck speeds, empirical vehicle validation, or B&B speedup on the tiny site set.

**Task 06B â€” Objective integrity, exact replay, grid-robust placement**

- Discrete/continuous replay resolve DRIVE arcs by `arc_id` (no silent parallel-arc pick); destination terminal checks.
- Explicit modes: `enroute_incremental_cost` (legacy Task 03A \(J\)) vs `energy_replenishment_cost` (terminal shortfall to usable cap at research tariff/Î·).
- Admissible MRLS/reference stop under terminal valuation; split-invariant road costs; placement compared at q=10/5/(2) Ã— both modes.
- **Not claimed:** grid-robust nationwide optimality, config B Moroccan results, market tariffs, or B&B speedup.

**Task 06C â€” Moroccan vehicle realism and multi-vehicle validation**

- Evidence matrix for Volvo FH Electric 4Ã—2 (prospective highway) vs eActros 600 comparator; Petit Forestier / Centrale Danone ~7.5 t dossier only (urban EV; **no** highway YAML).
- Dual usable scenarios **475 kWh (MA)** and **460 kWh (global)** â€” never merged; discrete `E_cap/min/init` derived from loaded vehicle (no hard-coded 600/60).
- CCS acceptance `min(charger, vehicle_ccs_max)`; Config A refrigeration labeled declared assumption.
- Certification: unresolved portfolio probe â†’ `UNRESOLVED_SERVICEABILITY` / `CONDITIONAL_RESTRICTED_PORTFOLIO`, never false full-portfolio `CERTIFIED_OPTIMAL`.
- Research monetary convention for 06C CSVs: solver integers = cents; `road_cost_per_km=100` Â¢/km.
- Identical-mission eActros vs Volvo B&Bâ€“MRLS comparison on path-union ODs.
- **Not claimed:** FH Electric already in Moroccan refrigerated long-haul fleets; FE Electric as FH; Aero Extended Range mix-in; measured OEM curb/CdA.

### Claim taxonomy (read before citing results)

| Label | Meaning |
|---|---|
| **(A) Real Moroccan refrigerated EV** | Petit Forestier ~7.5 t / Centrale Danone urbanâ€“peri-urban duty (dossier only) |
| **(B) Prospective long-haul scenario** | Volvo FH Electric 4Ã—2 on MA product pages â€” research highway pack |
| **(C) Manufacturer specs** | Published installed/usable kWh, CCS ceiling, GCW, driveline menu |
| **(D) Assumed physics / demand** | CdA, Crr, Î·, curb mass bounds, Config A TRU, illustrative tariffs/demand |

## Requirements

- Python **3.11+** (developed with 3.12)
- Optional but preferred: [`osmium-tool`](https://docs.osmcode.org/osmium/latest/osmium-extract.html) on `PATH` for geographic extracts (`complete_ways`). If missing, the build falls back to **pyrosm** bbox filtering and records the tool in `data/metadata/build_manifest.json`.

## Installation

```bash
cd E-Track_Location_Routing
python -m venv .venv
# Windows:
.venv\Scripts\activate
pip install -e ".[dev,extract]"
```

## Exact data sources

| Source | URL |
|---|---|
| ADM aires de services | https://www.adm.co.ma/fr/gares-de-peage-et-aires-de-services |
| ADM A3 Casablancaâ€“Agadir | https://www.adm.co.ma/fr/nos-autoroutes/a3-casablanca-agadir |
| Geofabrik Morocco | https://download.geofabrik.de/africa/morocco.html |
| Pinned snapshot (default) | https://download.geofabrik.de/africa/morocco-261106.osm.pbf |
| OSM copyright / ODbL | https://www.openstreetmap.org/copyright |
| Osmium extract docs | https://docs.osmcode.org/osmium/latest/osmium-extract.html |
| Open-Meteo Historical API | https://open-meteo.com/ |
| AWS COP-DEM GLO-30 Public | https://registry.opendata.aws/copernicus-dem/ (DOI 10.5270/ESA-c5d3d65) |
| Mercedes-Benz eActros 600 | Manufacturer product sheet (model 983403 class) |
| Volvo FH Electric (MA) | https://www.volvotrucks.ma/fr-ma/trucks/electric/volvo-fh-electric.html |
| Volvo FH Electric (global) | https://www.volvotrucks.com/en-en/trucks/electric/volvo-fh-electric.html |
| Petit Forestier Morocco EV | https://www.petitforestier.com/fr-ma/posts/270_petit-forestier-met-en-circulation-le-premier-poids-lourd-frigorifique-100-electrique-au-maroc |

Full registry after build: `data/metadata/sources.csv`.

## Build the pilot dataset

```bash
python scripts/build_pilot.py --config configs/pilot_corridor.yaml
```

Outputs:

- `data/processed/road_nodes.csv`
- `data/processed/road_edges.csv`
- `data/processed/candidate_sites.csv`
- `data/processed/pilot_network.graphml`
- `data/processed/pilot_network.geojson`
- `data/metadata/sources.csv`
- `data/metadata/build_manifest.json`
- `results/baseline_routes.json`
- `reports/pilot_corridor_report.html`

Large raw PBF files stay under `data/raw/` and are **gitignored**.

## Task 02 â€” energy pilot

```bash
pip install -e ".[dev]"
# optional DEM sampling dependency:
pip install -e ".[dem]"

python scripts/fetch_corridor_weather.py
python scripts/fetch_corridor_dem.py          # needs rasterio; falls back to flat if tiles fail
python scripts/run_energy_pilot.py
```

Outputs:

- `results/energy_pilot.csv`
- `reports/figures/energy_vs_payload_refrig.png`
- `reports/figures/elevation_cumulative_energy.png`
- `reports/energy_model_methodology.md`
- `reports/task02_energy_validation.md`
- `reports/task02b_physics_audit.md`
- `reports/task02b_dem_diagnostics.md`
- `data/processed/energy/elevation_profile_*.json` (when DEM succeeds)

Weather/DEM raw caches under `data/raw/weather/` and `data/raw/dem/` are **gitignored**. CI uses `tests/fixtures/weather/`.

Package API: `morocco_etruck.energy.evaluate_route(...)` â€” independent of charger/station logic.

## Tests

```bash
pytest -q
pytest -q -m integration
```

Unit tests use offline fixtures and **do not require internet**. Integration tests skip if processed pilot artifacts are absent.

## Visualizations

Open `reports/pilot_corridor_report.html` after a successful build. Literature overlap note: `reports/novelty_risks.md`. Energy figures under `reports/figures/`.

## Real vs derived vs assumed

| Kind | Examples |
|---|---|
| **Real / manufacturer** | OSM geometry & tags; ADM names; Geofabrik hash; eActros battery/mass/power from product sheet; Volvo FH installed/usable (MA 475 / global 460), CCSâ‰¤350 kW, GCWâ‰¤65 t; Open-Meteo & COP-DEM retrievals |
| **Derived** | Directed graph; shortest paths; DEM grades along baselines; SOC trajectories; discrete energy bounds from usable kWh; pilot CSV |
| **Assumed / uncertain** | \(C_{rr}\), \(C_dA\), efficiencies, \(P_\mathrm{aux}\), UA/COP refrigeration approx, trailer pack (B), SOC floor 10%; Volvo curb 12 t research bound; mid-menu 400 kW continuous=peak; Config A TRU; HGV access unknown |
| **Operating evidence (non-highway)** | Petit Forestier / Centrale Danone ~7.5 t urban EV (dossier; not a tractor YAML) |

## Known limitations

- ADM HTML has **no coordinates**; matching depends on OSM naming quality.
- No silent snap to the **opposite** carriageway.
- Service area â‰  grid capacity â‰  truck parking â‰  high-power charging.
- Baseline routes are **not** certified HGV routes.
- **Task 01C open issue:** 5 provisional topological access matches; **0** legally confirmed HGV; entrance/exit paths independent; no continuous facility traversal; **not** optimization-ready.
- Energy model uses **assumed** aero/rolling/TRU parameters; not OEM-calibrated; not empirically validated on measured e-truck logs.
- DEM is a **DSM** (surface), not pavement.
- See `reports/task02_energy_validation.md`.

## Licences and attribution

- **Python research code** in this repository is provided for academic reproducibility of Task 01/01B. That grant does **not** change OSM licensing.
- **OpenStreetMap-derived data** (road graphs, candidate location matches, route geometries): Â© OpenStreetMap contributors, **ODbL 1.0**. Attribution and share-alike apply to derivative databases. See https://www.openstreetmap.org/copyright
- **Geofabrik** distributes OSM extracts under the same OSM licence terms.
- **ADM** pages are cited for official naming and direction labels; ADM content is not treated as an open geospatial database.
- **Copernicus DEM** (DOI 10.5270/ESA-c5d3d65) via AWS Open Data; **Open-Meteo** weather under their terms; eActros specs cited from manufacturer materials (not redistributed as a datasheet PDF here).

### Accessibility field definitions (Task 01B)

| Field | Meaning |
|---|---|
| `location_match_status` | `matched_osm` / `unmatched` â€” geographic identification only |
| `directed_access_status` | `entrance_and_exit` / `entrance_only` / `exit_only` / `opposite_carriageway_only` / `proximity_only` / `unresolved` |
| `hgv_access_status` | `permitted` / `restricted` / `unknown` from OSM tags along access paths |

Proximity or bearing alone never yields truck-accessible verification. OSM topology â‰  legal HGV certification.

## Task 03A â€” routing benchmarks

```bash
python scripts/run_routing_benchmarks.py
pytest -q tests/unit/test_label_setting.py tests/unit/test_routing_reference.py
```

Outputs: `results/routing_benchmarks.csv`, `reports/task03a_problem_formulation.md`, `reports/task03a_algorithm_validation.md`.

## Task 03B â€” Morocco MRLS integration

```bash
python scripts/run_morocco_routing.py
# faster subset:
python scripts/run_morocco_routing.py --flat-only
pytest -q tests/unit/test_transition_oracle.py tests/unit/test_morocco_adapter_offline.py
```

Outputs:

- `results/morocco_routing_experiments.csv`
- `reports/figures/morocco_routing_corridor_map.geojson` / `.png`
- `reports/task03b_morocco_integration.md`
- `reports/task03b_discretization_validation.md`
- Cached DRIVE tables under `data/processed/optimization/drive_tables/`

## Task 04A â€” joint placement enumeration

```bash
python scripts/run_location_enumeration.py
pytest -q tests/unit/test_charge_grid_invariant.py tests/unit/test_placement_enumeration.py
```

Outputs:

- `results/location_enumeration.csv`, `results/location_optimal_solutions.csv`
- `reports/task04a_charging_grid_correction.md`
- `reports/task04a_joint_problem_formulation.md`
- `reports/task04a_location_enumeration_results.md`
- `reports/figures/placement_budget_*_CA.png`

## Task 04B â€” certified placement B&B

```bash
python scripts/run_branch_and_bound.py
pytest -q tests/unit/test_branch_and_bound.py tests/unit/test_placement_bounds.py tests/unit/test_placement_certification.py
```

Outputs:

- `results/branch_bound_comparison.csv`
- `reports/task04b_branch_bound_methodology.md`
- `reports/task04b_algorithm_validation.md`
- `configs/optimization/branch_bound_benchmarks.yaml` (synthetic prune demo)

## Task 05A â€” multi-route discovery

```bash
python scripts/build_multiroute_pilot.py --skip-download
```

## Task 05B â€” physics-validated multi-route MRLS

```bash
python scripts/regenerate_multiroute_decision_graph.py
python scripts/fetch_multiroute_dem.py
python scripts/run_multiroute_experiments.py
pytest -q tests/unit/test_multiroute_physics.py tests/unit/test_route_choice.py
```

Outputs:

- `data/processed/multiroute/decision_graph.json` (arc_id + osm_edge_pairs)
- `data/processed/multiroute/elevation/arc_*.json` (per-macro COP-DEM)
- `results/multiroute_physics_experiments.csv`
- `reports/task05b_decision_graph_audit.md`
- `reports/task05b_physics_integration.md`
- `reports/task05b_route_choice_validation.md`
- `reports/figures/multiroute_physics_paths.png`

## Task 05C â€” joint multi-route placement

```bash
pytest -q tests/unit/test_multiroute_station_direction.py \
         tests/unit/test_multiroute_station_monotonicity.py \
         tests/unit/test_multiroute_placement.py \
         tests/unit/test_multiroute_physics.py
python scripts/run_multiroute_experiments.py
python scripts/run_multiroute_placement.py
```

Outputs:

- `results/multiroute_physics_experiments.csv` (corrected 05B pilot)
- `results/multiroute_placement_enumeration.csv`
- `results/multiroute_placement_branch_bound.csv`
- `reports/task05c_station_attachment_audit.md`
- `reports/task05c_joint_multiroute_validation.md`
- `reports/task05c_comparative_results.md`

## Task 06A â€” numerical validation

```bash
pytest -q tests/unit/test_multiroute_speed_and_grid.py tests/unit
python scripts/run_multiroute_numerical_sensitivity.py
python scripts/run_multiroute_experiments.py
python scripts/run_multiroute_placement.py
```

Outputs:

- `results/multiroute_numerical_sensitivity.csv`
- `results/multiroute_numerical_sensitivity_osm_maxspeed.csv` (contrast)
- `results/task06a_placement_comparison.csv`
- `reports/task06a_speed_and_physics_audit.md`
- `reports/task06a_discretization_validation.md`
- `reports/task06a_corrected_placement_comparison.md`

## Task 06B â€” objective / replay / grid placement

```bash
pytest -q tests/unit/test_exact_arc_replay.py \
         tests/unit/test_terminal_energy_cost.py \
         tests/unit/test_placement_grid_robustness.py
python scripts/run_task06b_placement_grid.py --quanta 10,5,2
```

Outputs:

- `results/task06b_objective_comparison.csv`
- `results/task06b_placement_grid_comparison.csv`
- `reports/task06b_objective_and_replay_audit.md`
- `reports/task06b_grid_robustness.md`
- `reports/task06b_bb_certification.md`

**Objective scope:** legacy en-route incremental cost vs energy-replenishment cost (terminal shortfall). Exactness only on the finite discrete model; continuous replay certifies served Moroccan journeys under research physics assumptions.

## Task 06C â€” multi-vehicle comparison

```bash
pytest -q tests/unit/test_multi_vehicle_06c.py tests/unit
python scripts/run_task06c_vehicle_comparison.py --quanta 10,5
```

Outputs:

- `configs/vehicles/volvo_fh_electric_4x2_540kwh.yaml` (usable 475 MA)
- `configs/vehicles/volvo_fh_electric_4x2_540kwh_usable460.yaml` (usable 460 global)
- `results/task06c_vehicle_comparison.csv`
- `results/task06c_vehicle_placement.csv`
- `reports/task06c_vehicle_evidence_matrix.md`
- `reports/task06c_vehicle_model_validation.md`
- `reports/task06c_moroccan_operating_ev_dossier.md`
- `reports/task06c_vehicle_comparison.md`

**Vehicle scope:** eActros 600 comparator + prospective Volvo FH Electric 4Ã—2 (dual usable). Petit Forestier is documented separately and is **not** run as a 40 t motorway pack.

**Task 06C routing CSV is invalidated** by a GCM state-leak bug (light-labeled rows inherited 40â€¯t). Retained as `results/task06c_vehicle_comparison_INVALIDATED_gcm_leak.csv`. Use Task 06D results instead.

## Task 06D â€” fair multi-vehicle integrity + placement revalidation

```bash
pytest -q tests/unit/test_task06d_gcm_integrity.py tests/unit
python scripts/run_task06d_vehicle_comparison.py --quanta 10,5
```

Outputs:

- `results/task06d_vehicle_comparison.csv` (immutable GCM / fixed-payload / equal-SOC)
- `results/task06d_vehicle_placement.csv` (legacy default + `refrigerated_06d`)
- `reports/task06d_gcm_bug_root_cause.md`
- `reports/task06d_fair_vehicle_comparison.md`
- `reports/task06d_refrigerated_freight_sensitivity.md`
- `reports/task06d_corrected_placement.md`

**Scientific gate:** equal-mass and equal-payload comparisons; equal departure SOC vs equal absolute kWh labeled separately; certification downgrades on `replay_invalid` as well as `limit_reached`.

**Task 06D `refrigerated_06d` is non-primary** (ablation/hot mixed into demand). Use Task 07A cold-chain baseline.

## Task 07A â€” cold-chain benchmark integrity

```bash
pytest -q tests/unit/test_task07a_demand_integrity.py tests/unit
python scripts/run_task07a_benchmark.py
```

Outputs:

- `configs/optimization/multiroute_placement_07a.yaml` (separated baseline / ablation / hot / cool)
- `results/task07a_refrigerated_routing.csv`
- `results/task07a_placement.csv`
- `results/task07a_sensitivity.csv`
- `reports/task07a_demand_portfolio_audit.md`
- `reports/task07a_moroccan_site_evidence.md`
- `reports/task07a_refrigeration_ablation.md`
- `reports/task07a_placement_robustness.md`
- `reports/task07a_research_claims_and_limitations.md`

**Framing:** future infrastructure planning at ADM service areas (`hypothetical_future_truck_site`). Illustrative demand weights â€” not observed Moroccan freight volumes.

## Task 07B â€” physical realism and scientific validation

```bash
pytest -q tests/unit/test_task07b_physical_realism.py
python scripts/run_task07b_physical_validation.py --stages all
python scripts/write_task07b_reports.py
```

Outputs:

- `reports/task07b_07a_baseline_manifest.md` + `results/task07b_07a_manifest.json`
- `results/task07b_physical_sensitivity.csv` / `reports/task07b_refrigeration_uncertainty.md`
- `results/task07b_charging_duration.csv` / `reports/task07b_charge_time_and_deadlines.md`
- `results/task07b_discretization_diagnostics.csv` / `reports/task07b_discretization_diagnostics.md`
- `results/task07b_routing_baselines.csv` / `reports/task07b_routing_baselines.md`
- `results/task07b_placement_robustness.csv` / `reports/task07b_infrastructure_robustness.md`
- `configs/optimization/multiroute_placement_07b.yaml` + `configs/energy/task07b_thermal_*.yaml`

**Framing:** stress-test of the Task 07A eActros one-site vs Volvo two-site finite-model contrast under DEM, documented UA ladder, charge-duration/deadlines, and q-grid diagnostics. Not a Moroccan install recommendation.

**Invalidated:** Task 07B `task07b_routing_baselines.csv` shortest-vs-multi-route nesting claims (different physical graphs via `max_alts` rebuild). See Task 07C.

## Task 07C â€” route nesting integrity (still stands)

```bash
pytest -q tests/unit/test_task07c_route_nesting.py
python scripts/run_task07c_final_freeze.py --stages all --terrain dem
python scripts/write_task07c_reports.py
```

Outputs:

- `reports/task07c_route_nesting_integrity.md`
- `reports/task07c_final_scientific_results.md`
- `reports/task07c_evidence_and_novelty_matrix.md`
- `results/task07c_matched_routing_baselines.csv`
- `results/task07c_final_placement.csv`
- `results/task07c_final_sensitivity.csv`
- `reports/figures/task07c_*.png`

**Correction:** build the scientific pilot path-union once; restrict routes with `allowed_arc_ids`; toggle chargers with `active_stations` only.

**Freeze framing:** evidence-grounded prospective optimization study. Not field-validated Moroccan deployment.

## Task 08 â€” final SOC/payload realism and algorithm validation

```bash
pytest -q tests/unit/test_task08_nesting_and_realism.py tests/unit/test_task07c_route_nesting.py
python scripts/run_task08_final_validation.py --stages all
python scripts/write_task08_reports.py
```

Outputs:

- `reports/task08_final_model_audit.md`
- `reports/task08_realism_and_soc_payload_robustness.md`
- `reports/task08_algorithm_performance.md`
- `reports/task08_claims_evidence_limitations.md`
- `results/task08_soc_payload_comparison.csv`
- `results/task08_placement_economics.csv`
- `results/task08_algorithm_benchmarks.csv`
- `results/task08_final_summary.csv`
- `reports/figures/task08_*.png`

**Headline:** the 50%-SOC one-site eActros vs two-site Volvo contrast does **not** universally survive 80%/100% departure SOC or 15 t cargo â€” report without retuning.

## Publication-readiness checkpoint (post Task 08)

```bash
pytest -q -m "not integration"
python scripts/run_final_heavy_vehicle_diagnosis.py
python scripts/run_task08_final_validation.py --stages benchmark
```

Outputs:

- `reports/final_publication_results.md`
- `reports/final_heavy_vehicle_feasibility_diagnosis.md`
- `reports/final_algorithm_benchmark_audit.md`
- `reports/final_economic_units_and_provenance_audit.md`
- `results/final_heavy_vehicle_feasibility_diagnosis.csv`
- `results/task08_algorithm_benchmarks.csv` (corrected cert/timings)
- `results/task08_algorithm_benchmarks_historical_8site.csv`

**Defensible headline:** charger requirements depend strongly on vehicle configuration, departure SOC, cargo payload, and route flexibility â€” not a universal one-truck / one-site ranking.

## PASS 1 â€” Moroccan scientific integrity (awaiting independent review)

Before any PASS 2 northbound scenario rewiring:

- `reports/morocco_realism_and_freight_direction_audit.md`
- `reports/morocco_law_vehicle_coldchain_evidence.md`
- `reports/methodological_novelty_go_nogo.md`
- `reports/moroccan_data_request_specification.md`

**Key PASS 1 findings:** Task 07/08 portfolios are southbound-only; primary Moroccan refrigerated export motivation is northbound (Souss-Massaâ†’Casablanca); reverse OD road data exist; reverse Amskroud missing; legal label `gross_mass_within_limit_axle_unverified`; methodological novelty is CONDITIONAL GO for certification-aware q-refinement diagnostics (NO-GO for unproved continuous-optimal adaptive theorems).

## PASS 2 â€” Northbound benchmark + bounded discretization test

```bash
python scripts/fetch_multiroute_dem.py --od-ids agadir_casa --merge-meta --max-alts 4
python scripts/run_pass2a_northbound_benchmark.py
python scripts/run_pass2b_discretization_refinement.py
pytest -q -m "not integration"
```

- Case A proxy: firm-ripe tomatoes, `agadir_casa`, DEM validated, `settat_ac`/`benguerir_ac` only.
- Under assumed power packs, Case A is peak-motor / model-infeasible (chargers do not restore).
- PASS 2B: `CONDITIONAL_DIAGNOSTIC_ONLY` â€” q-refinement can change serviceability conclusions; not a top-tier new optimizer.
- Ledger: `reports/pass2_final_claims_and_provenance.md`

## Not yet implemented (manuscript + external operator data)

- Refrigeration configuration B Moroccan optimization
- Nationwide network search
- ALNS, GA, Gurobi, OR-Tools, etc.
- Paper writing (use freeze artifacts)
- External fleet GPS/TRU logs and certified HGV charger-access data

**STOP DEVELOPMENT.** No Task 09 feature chain. Next activity is manuscript preparation and external Moroccan operational evidence.

