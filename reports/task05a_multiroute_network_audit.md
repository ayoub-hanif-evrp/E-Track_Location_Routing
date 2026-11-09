# Task 05A — Multi-route network audit

## Scope

Separate expanded Moroccan road dataset for **Casablanca–Marrakech–Agadir** route choice. Does **not** overwrite Task 01–04 A3 artifacts (`data/processed/road_*.csv`).

- Config: [`configs/multiroute_corridor.yaml`](../configs/multiroute_corridor.yaml)
- Build: `python scripts/build_multiroute_pilot.py --skip-download`
- Outputs: `data/processed/multiroute/`

## Source data

| Item | Value |
|---|---|
| OSM snapshot | Geofabrik `morocco-261106.osm.pbf` (ODbL; © OpenStreetMap contributors) |
| Bbox | W -9.60, S 30.25, E -7.40, N 33.70 |
| Highway classes | motorway, motorway_link, trunk, trunk_link, primary, primary_link |

## Graph size (build manifest)

| Metric | Count |
|---|---:|
| Directed nodes | 98,693 |
| Directed edges | 100,261 |
| Explicit `hgv=no` edges rejected | (see `hgv_audit.csv`) |
| Path alternative records | 24 (6 OD × 4 routes) |
| Decision-graph arcs (path union) | 251 |

## HGV policy

- Edges with `hgv_access=no` are **removed** from the multiroute routing graph (stricter than the A3 pilot, which kept them).
- `unknown` and `yes` are retained; missing OSM tags are **not** treated as confirmed legal HGV access.
- Audit: `data/processed/multiroute/hgv_audit.csv`, counts in `build_manifest.json`.

## Origin–destination pairs and alternatives

Connectivity-aware snaps were required so reverse directions are feasible on one-way carriageways.

| OD | Alternatives found | Note |
|---|---:|---|
| casa_agadir | 4 | Diverse paths via edge-penalty |
| agadir_casa | 4 | |
| casa_marrakech | 4 | |
| marrakech_casa | 4 | |
| marrakech_agadir | 4 | |
| agadir_marrakech | 4 | |

All six directed ODs support **genuine alternative routes** under the documented Jaccard/length thresholds. Details: `path_alternatives.csv`.

## Map

- `reports/figures/multiroute_path_alternatives.png`
- `reports/figures/multiroute_path_alternatives.geojson`

## Claims

Exact discrete routing later is **only** over the selected verified path set / reduced decision representation—not the full Moroccan OSM network.
