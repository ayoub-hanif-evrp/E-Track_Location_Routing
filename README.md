# E-Track_Location_Routing

**Provisional title:** Joint Charging Infrastructure Placement and Energy-Feasible Routing for Electric Refrigerated Heavy-Duty Trucks on Moroccan Motorway Corridors

PhD research codebase (Casablanca, Morocco). **Task 01** builds a reproducible real-data foundation for the Casablanca–Agadir motorway corridor. It does **not** solve the joint location–routing optimization problem.

## Scientific objective

Eventually determine which Moroccan motorway service areas should receive truck-compatible charging infrastructure, which routes electric refrigerated heavy-duty trucks should follow, where/how much to charge, and which freight missions are energy-feasible.

## Current scope (Tasks 01–07A)

**Task 01 / 01B / 01C — geographic foundation**

- Download a **dated** Geofabrik Morocco OSM extract (cached + SHA-256).
- Extract a buffered Casablanca–Agadir pilot region.
- Build a **directed** motorway graph with real lengths and OSM attributes.
- Identify **ADM-directory** corridor service areas as **candidate** future charger sites (not verified e-truck chargers).
- Direction-aware OSM matching; unresolved sites are never given invented coordinates.
- Shortest-distance baseline paths Casablanca ↔ Agadir on **separate directed A3 carriageway components**.
- Access audit: provisional topological matches only (see open issue below).

**Task 02 / 02B — physics-based energy model (no optimization)**

- Longitudinal traction + aux + approximate refrigeration energy for an **eActros 600** refrigerated combination.
- Constant cruise **80 km/h** (OSM `maxspeed` not used as travel speed); peak-motor exceedances flagged (no silent power clip).
- Path-wise SOC feasibility (min SOC / first violation); invalid DEM → indeterminate mission status.
- Terrain: AWS open **COP-DEM GLO-30** with bounds-aware sampling + quality gates (flat-road baseline always retained).
- Weather: **Open-Meteo** historical cache; vector-mean daily wind.
- Refrigeration configs **A** (tractor battery) / **B** (independent trailer pack); GCM labels (not “payload”).
- Pilot CSV + figures; methodology, validation, and Task 02B audit/diagnostics reports.
- **Not claimed:** calibrated TRU reproduction, OEM coast-down parameters, empirical trip validation, or charger-feasible routing.

**Task 03A — multi-resource label-setting (MRLS) routing solver**

- Custom discrete MRLS with DRIVE / CHARGE / WAIT; active stations are **inputs** (no placement B&B yet).
- Exactness only for the **finite integer-grid** synthetic problem (1 kWh / 5 min); validated vs an independent exhaustive reference on cases A–J.
- Incremental physics adapter `apply_drive` (incoming SOC) bridges Task 02B without copying force equations into the router.
- **Not claimed:** continuous charging optimality, Moroccan network optimality, or certified operational chargers at ADM sites.

**Task 03B — Moroccan corridor charging-stop pilot**

- Validation gates: dominance stress `K`, transition oracle, instance validation, solution replay.
- Fixed A3 baselines → macro-arcs with **state-dependent DRIVE tables** (conservative floor-kWh / ceil-time); edge/macro-local terrain (no misused global DEM `s_cursor`).
- Hypothetical `entrance_and_exit` chargers only; S1–S5 experiments + continuous physics replay.
- **Not claimed:** certified HGV access, multi-path LRP, or continuous optimality beyond replay checks.

**Task 04A — Charging-grid fix + exact placement enumeration**

- Action-level stationary Wh drains + quantum-floor after CHARGE/WAIT; fingerprinted DRIVE-table cache.
- Exhaustive evaluation of all **32** subsets of five directional hypothetical sites; lex coverage-then-cost objective under illustrative budgets.
- **Not claimed:** market CAPEX/tariffs or certified HGV chargers.

**Task 04B — Certified placement branch-and-bound + MRLS**

- Full terrain fingerprint; global certification statuses; serviceability taxonomy (`peak_motor` structural only).
- Install/exclude B&B with proved budget, coverage UB, and secondary LB pruning; MRLS memoization.
- Matches all **32** Task 04A scenario optima; synthetic 12-site pruning demo.
- **Not claimed:** market prices, nationwide LRP, or metaheuristics/MIP solvers.

**Task 05A — Multi-route Moroccan freight discovery**

- Stage-1 B&B safeguards; separate expanded OSM graph under `data/processed/multiroute/`.
- Verified path alternatives for Casa↔Marrakech↔Agadir (discovery milestone).
- **Not claimed:** physics-integrated multi-route optimality (see 05B).

**Task 05B — Physics-validated multi-route MRLS**

- Audited path-union decision graph (`arc_id`, canonical aliases, length checks).
- OD-local path-union MRLS with Task 02B/03B DRIVE tables (not artificial `O→R_i→D`).
- Grounded ADM hypothetical chargers only; continuous replay of OSM-edge journeys.
- Pilot ODs: Casa→Marrakech, Casa→Agadir, Marrakech→Agadir.
- **Not claimed:** full-network optimality, certified HGV access, or joint placement (see 05C).

**Task 05C — Corrected station coupling + joint B&B–MRLS**

- Direction-specific ADM attach (`travel_direction` + OSM id); no wrong-carriageway proximity snap.
- Fixed path-union graph across install subsets (activate/deactivate only); DEM parent-slice after splits.
- Continuous-replay certification (deadline, SOC floors, DEM completeness).
- Joint placement: exhaustive enum vs existing B&B on a small multi-route portfolio.
- **Not claimed:** certified HGV access, nationwide optimality, or new metaheuristics.

**Task 06A — Speed policy + energy-grid validation**

- Per-OSM-hop research cruise speeds enter `apply_drive` (class defaults; OSM maxspeed not used as HGV cruise).
- DRIVE-table fingerprint `06a.1` includes speed schedule; no silent `E_init` bump.
- Grid sensitivity + discrete vs continuous feasibility audit; placement enum↔B&B revalidated.
- **Not claimed:** observed truck speeds, empirical vehicle validation, or B&B speedup on the tiny site set.

**Task 06B — Objective integrity, exact replay, grid-robust placement**

- Discrete/continuous replay resolve DRIVE arcs by `arc_id` (no silent parallel-arc pick); destination terminal checks.
- Explicit modes: `enroute_incremental_cost` (legacy Task 03A \(J\)) vs `energy_replenishment_cost` (terminal shortfall to usable cap at research tariff/η).
- Admissible MRLS/reference stop under terminal valuation; split-invariant road costs; placement compared at q=10/5/(2) × both modes.
- **Not claimed:** grid-robust nationwide optimality, config B Moroccan results, market tariffs, or B&B speedup.

**Task 06C — Moroccan vehicle realism and multi-vehicle validation**

- Evidence matrix for Volvo FH Electric 4×2 (prospective highway) vs eActros 600 comparator; Petit Forestier / Centrale Danone ~7.5 t dossier only (urban EV; **no** highway YAML).
- Dual usable scenarios **475 kWh (MA)** and **460 kWh (global)** — never merged; discrete `E_cap/min/init` derived from loaded vehicle (no hard-coded 600/60).
- CCS acceptance `min(charger, vehicle_ccs_max)`; Config A refrigeration labeled declared assumption.
- Certification: unresolved portfolio probe → `UNRESOLVED_SERVICEABILITY` / `CONDITIONAL_RESTRICTED_PORTFOLIO`, never false full-portfolio `CERTIFIED_OPTIMAL`.
- Research monetary convention for 06C CSVs: solver integers = cents; `road_cost_per_km=100` ¢/km.
- Identical-mission eActros vs Volvo B&B–MRLS comparison on path-union ODs.
- **Not claimed:** FH Electric already in Moroccan refrigerated long-haul fleets; FE Electric as FH; Aero Extended Range mix-in; measured OEM curb/CdA.

### Claim taxonomy (read before citing results)

| Label | Meaning |
|---|---|
| **(A) Real Moroccan refrigerated EV** | Petit Forestier ~7.5 t / Centrale Danone urban–peri-urban duty (dossier only) |
| **(B) Prospective long-haul scenario** | Volvo FH Electric 4×2 on MA product pages — research highway pack |
| **(C) Manufacturer specs** | Published installed/usable kWh, CCS ceiling, GCW, driveline menu |
| **(D) Assumed physics / demand** | CdA, Crr, η, curb mass bounds, Config A TRU, illustrative tariffs/demand |

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
| ADM A3 Casablanca–Agadir | https://www.adm.co.ma/fr/nos-autoroutes/a3-casablanca-agadir |
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

## Task 02 — energy pilot

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

Package API: `morocco_etruck.energy.evaluate_route(...)` — independent of charger/station logic.

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
| **Real / manufacturer** | OSM geometry & tags; ADM names; Geofabrik hash; eActros battery/mass/power from product sheet; Volvo FH installed/usable (MA 475 / global 460), CCS≤350 kW, GCW≤65 t; Open-Meteo & COP-DEM retrievals |
| **Derived** | Directed graph; shortest paths; DEM grades along baselines; SOC trajectories; discrete energy bounds from usable kWh; pilot CSV |
| **Assumed / uncertain** | \(C_{rr}\), \(C_dA\), efficiencies, \(P_\mathrm{aux}\), UA/COP refrigeration approx, trailer pack (B), SOC floor 10%; Volvo curb 12 t research bound; mid-menu 400 kW continuous=peak; Config A TRU; HGV access unknown |
| **Operating evidence (non-highway)** | Petit Forestier / Centrale Danone ~7.5 t urban EV (dossier; not a tractor YAML) |

## Known limitations

- ADM HTML has **no coordinates**; matching depends on OSM naming quality.
- No silent snap to the **opposite** carriageway.
- Service area ≠ grid capacity ≠ truck parking ≠ high-power charging.
- Baseline routes are **not** certified HGV routes.
- **Task 01C open issue:** 5 provisional topological access matches; **0** legally confirmed HGV; entrance/exit paths independent; no continuous facility traversal; **not** optimization-ready.
- Energy model uses **assumed** aero/rolling/TRU parameters; not OEM-calibrated; not empirically validated on measured e-truck logs.
- DEM is a **DSM** (surface), not pavement.
- See `reports/task02_energy_validation.md`.

## Licences and attribution

- **Python research code** in this repository is provided for academic reproducibility of Task 01/01B. That grant does **not** change OSM licensing.
- **OpenStreetMap-derived data** (road graphs, candidate location matches, route geometries): © OpenStreetMap contributors, **ODbL 1.0**. Attribution and share-alike apply to derivative databases. See https://www.openstreetmap.org/copyright
- **Geofabrik** distributes OSM extracts under the same OSM licence terms.
- **ADM** pages are cited for official naming and direction labels; ADM content is not treated as an open geospatial database.
- **Copernicus DEM** (DOI 10.5270/ESA-c5d3d65) via AWS Open Data; **Open-Meteo** weather under their terms; eActros specs cited from manufacturer materials (not redistributed as a datasheet PDF here).

### Accessibility field definitions (Task 01B)

| Field | Meaning |
|---|---|
| `location_match_status` | `matched_osm` / `unmatched` — geographic identification only |
| `directed_access_status` | `entrance_and_exit` / `entrance_only` / `exit_only` / `opposite_carriageway_only` / `proximity_only` / `unresolved` |
| `hgv_access_status` | `permitted` / `restricted` / `unknown` from OSM tags along access paths |

Proximity or bearing alone never yields truck-accessible verification. OSM topology ≠ legal HGV certification.

## Task 03A — routing benchmarks

```bash
python scripts/run_routing_benchmarks.py
pytest -q tests/unit/test_label_setting.py tests/unit/test_routing_reference.py
```

Outputs: `results/routing_benchmarks.csv`, `reports/task03a_problem_formulation.md`, `reports/task03a_algorithm_validation.md`.

## Task 03B — Morocco MRLS integration

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

## Task 04A — joint placement enumeration

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

## Task 04B — certified placement B&B

```bash
python scripts/run_branch_and_bound.py
pytest -q tests/unit/test_branch_and_bound.py tests/unit/test_placement_bounds.py tests/unit/test_placement_certification.py
```

Outputs:

- `results/branch_bound_comparison.csv`
- `reports/task04b_branch_bound_methodology.md`
- `reports/task04b_algorithm_validation.md`
- `configs/optimization/branch_bound_benchmarks.yaml` (synthetic prune demo)

## Task 05A — multi-route discovery

```bash
python scripts/build_multiroute_pilot.py --skip-download
```

## Task 05B — physics-validated multi-route MRLS

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

## Task 05C — joint multi-route placement

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

## Task 06A — numerical validation

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

## Task 06B — objective / replay / grid placement

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

## Task 06C — multi-vehicle comparison

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

**Vehicle scope:** eActros 600 comparator + prospective Volvo FH Electric 4×2 (dual usable). Petit Forestier is documented separately and is **not** run as a 40 t motorway pack.

**Task 06C routing CSV is invalidated** by a GCM state-leak bug (light-labeled rows inherited 40 t). Retained as `results/task06c_vehicle_comparison_INVALIDATED_gcm_leak.csv`. Use Task 06D results instead.

## Task 06D — fair multi-vehicle integrity + placement revalidation

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

## Task 07A — cold-chain benchmark integrity

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

**Framing:** future infrastructure planning at ADM service areas (`hypothetical_future_truck_site`). Illustrative demand weights — not observed Moroccan freight volumes.

## Not yet implemented (stop after Task 07A)

- Refrigeration configuration B Moroccan optimization
- Nationwide search / large scalability B&B study
- ALNS, GA, Gurobi, OR-Tools, etc.
- Paper writing

**Stop after Task 07A** until the researcher reviews.
