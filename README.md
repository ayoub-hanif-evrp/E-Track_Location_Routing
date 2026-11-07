# E-Track_Location_Routing

**Provisional title:** Joint Charging Infrastructure Placement and Energy-Feasible Routing for Electric Refrigerated Heavy-Duty Trucks on Moroccan Motorway Corridors

PhD research codebase (Casablanca, Morocco). **Task 01** builds a reproducible real-data foundation for the Casablanca–Agadir motorway corridor. It does **not** solve the joint location–routing optimization problem.

## Scientific objective

Eventually determine which Moroccan motorway service areas should receive truck-compatible charging infrastructure, which routes electric refrigerated heavy-duty trucks should follow, where/how much to charge, and which freight missions are energy-feasible.

## Current scope (Task 01 only)

- Download a **dated** Geofabrik Morocco OSM extract (cached + SHA-256).
- Extract a buffered Casablanca–Agadir pilot region.
- Build a **directed** motorway graph with real lengths and OSM attributes.
- Identify **ADM-directory** corridor service areas as **candidate** future charger sites (not verified e-truck chargers).
- Direction-aware OSM matching; unresolved sites are never given invented coordinates.
- Shortest-distance baseline paths Casablanca ↔ Agadir on **separate directed A3 carriageway components** (dual motorways are not one strongly connected digraph).
- Pytest suite + HTML research report + literature overlap note.

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

## Tests

```bash
pytest -q
pytest -q -m integration
```

Unit tests use offline fixtures and **do not require internet**. Integration tests skip if processed pilot artifacts are absent.

## Visualizations

Open `reports/pilot_corridor_report.html` after a successful build. Literature overlap note: `reports/novelty_risks.md`.

## Real vs derived vs assumed

| Kind | Examples |
|---|---|
| **Real** | OSM road geometry & tags; ADM official names/partners/directions; Geofabrik snapshot hash |
| **Derived** | Directed graph edges; geodesic `length_m`; shortest paths; OSM–ADM name matches |
| **Assumed / uncertain** | Motorway `oneway` when tag missing; `hgv_access=unknown` when tags absent; search anchors for city-end baseline nodes |

## Known limitations

- ADM HTML has **no coordinates**; matching depends on OSM naming quality.
- No silent snap to the **opposite** carriageway.
- Service area ≠ grid capacity ≠ truck parking ≠ high-power charging.
- Baseline routes are **not** certified HGV routes.
- See report limitations section for more.

## Licences and attribution

- **Python research code** in this repository is provided for academic reproducibility of Task 01/01B. That grant does **not** change OSM licensing.
- **OpenStreetMap-derived data** (road graphs, candidate location matches, route geometries): © OpenStreetMap contributors, **ODbL 1.0**. Attribution and share-alike apply to derivative databases. See https://www.openstreetmap.org/copyright
- **Geofabrik** distributes OSM extracts under the same OSM licence terms.
- **ADM** pages are cited for official naming and direction labels; ADM content is not treated as an open geospatial database.

### Accessibility field definitions (Task 01B)

| Field | Meaning |
|---|---|
| `location_match_status` | `matched_osm` / `unmatched` — geographic identification only |
| `directed_access_status` | `entrance_and_exit` / `entrance_only` / `exit_only` / `opposite_carriageway_only` / `proximity_only` / `unresolved` |
| `hgv_access_status` | `permitted` / `restricted` / `unknown` from OSM tags along access paths |

Proximity or bearing alone never yields truck-accessible verification. OSM topology ≠ legal HGV certification.

## Not yet implemented

- Energy consumption model (payload, elevation, weather, battery)
- Refrigeration / TRU simulator
- Charging decisions or dwell times
- Station placement optimization (no ALNS, GA, Gurobi, OR-Tools, etc.)
- Mission feasibility under budgets

Stop after Task 01 until the next phase is authorized.
