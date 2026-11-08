# E-Track_Location_Routing

**Provisional title:** Joint Charging Infrastructure Placement and Energy-Feasible Routing for Electric Refrigerated Heavy-Duty Trucks on Moroccan Motorway Corridors

PhD research codebase (Casablanca, Morocco). **Task 01** builds a reproducible real-data foundation for the Casablanca–Agadir motorway corridor. It does **not** solve the joint location–routing optimization problem.

## Scientific objective

Eventually determine which Moroccan motorway service areas should receive truck-compatible charging infrastructure, which routes electric refrigerated heavy-duty trucks should follow, where/how much to charge, and which freight missions are energy-feasible.

## Current scope (Tasks 01–02)

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
| **Real / manufacturer** | OSM geometry & tags; ADM names; Geofabrik hash; eActros battery/mass/power from product sheet; Open-Meteo & COP-DEM retrievals |
| **Derived** | Directed graph; shortest paths; DEM grades along baselines; SOC trajectories; pilot CSV |
| **Assumed / uncertain** | \(C_{rr}\), \(C_dA\), efficiencies, \(P_\mathrm{aux}\), UA/COP refrigeration approx, trailer pack (B), SOC floor 10%; HGV access unknown |

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

## Not yet implemented (stop after Task 02)

- Charging decisions or dwell times
- Station placement optimization (no ALNS, GA, Gurobi, OR-Tools, etc.)
- EVRP / multi-stop energy-feasible routing with en-route charge
- Redesign of Task 01C access classifiers

**Stop after Task 02** until the next phase is authorized.
