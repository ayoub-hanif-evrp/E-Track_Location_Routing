# Task 01B — Scientific audit of the Moroccan freight network foundation

**Audited baseline commit:** `35c540ec151998449de3a5cb4c74ac5c1aed952f`  
**Rebuild:** offline from pinned Geofabrik `morocco-261106.osm.pbf`  
SHA-256: `e26e8b7010cf78259469f166292b351de48609b3b1f420dd469f0d49f7d05a00`

Machine-readable site table: [`data/processed/candidate_sites.csv`](../data/processed/candidate_sites.csv)  
Static map: [`reports/pilot_corridor_overview.png`](pilot_corridor_overview.png)

---

## 1. What was wrong in Task 01

1. **Over-claimed “verified” accessibility.** Matching used OSM name + proximity + approximate motorway bearing. That is not evidence of a drivable entrance/exit from the correct carriageway.
2. **False-positive location risk.** Token matching could attach to unrelated OSM features containing the same place name (observed for Settat → “Chambre de commerce … Settat”).
3. **`nx.DiGraph` risk for parallel edges.** Distinct OSM ways sharing the same `(u,v)` would silently overwrite attributes.
4. **Possible double expansion of directions.** Edges from `pyrosm.get_network` are already travel-directed; re-expanding `oneway=no` could duplicate bidirectional roads.
5. **Route GeoJSON used node coordinates only**, not ordered edge geometries.
6. **Broken CLI entry point** (`morocco_etruck.cli:main` missing).
7. **`--skip-download` ran after download logic** and could not guarantee offline behaviour.
8. **Manifest paths were machine-absolute**, harming portability.
9. **Unit tests did not cover OSM conversion / access logic** with synthetic topology cases.

---

## 2. Corrections implemented

| Issue | Correction |
|---|---|
| Accessibility overclaim | Split `location_match_status`, `directed_access_status`, `hgv_access_status`; removed Task 01 `verified` meaning |
| False POI match | Prefer `aire de service` / `highway=services` / fuel tags; reject rank-0 name collisions |
| Parallel edges | Build `nx.MultiDiGraph`; export `edge_key`; audit collision count |
| Direction expansion | Assume pyrosm pre-expanded directed rows; only reverse on `oneway=-1` |
| Route geometry | `path_edge_geometries` concatenates travel-oriented edge WKT |
| CLI / offline | Implemented `cli.py` + `build.run_build`; `--skip-download` blocks network before download |
| Manifest | Repository-relative paths; licensing block |
| Tests / CI | Synthetic topology/access tests; GitHub Actions offline unit workflow |
| Audit figure | `reports/pilot_corridor_overview.png` |

**Field definitions**

- `location_match_status`: `matched_osm` | `unmatched`
- `directed_access_status`: `entrance_and_exit` | `entrance_only` | `exit_only` | `opposite_carriageway_only` | `proximity_only` | `unresolved`
- `hgv_access_status`: `permitted` | `restricted` | `unknown` (OSM tags along access paths only)
- Legacy `match_status` retained for continuity (`access_topology_ok` / `partial_access` / `unresolved`) — **never** “verified truck-accessible”

---

## 3. Candidate facility outcomes (Task 01B)

| Facility (ADM) | Location | Directed access | HGV |
|---|---|---|---|
| Amskroud Casa→Agadir | matched_osm | entrance_and_exit | unknown |
| Benguerir Agadir→Casa | matched_osm | entrance_and_exit | unknown |
| Benguerir Casa→Agadir | matched_osm | entrance_and_exit | unknown |
| Berrechid Agadir→Casa | matched_osm | entrance_and_exit | unknown |
| Settat Agadir→Casa | matched_osm | entrance_and_exit | unknown |
| Settat Casa→Agadir | matched_osm | entrance_and_exit | unknown |
| Marrakech (both) | unmatched | unresolved | unknown |
| Oum Rbii (both) | unmatched | unresolved | unknown |

**Counts**

- Matched OSM location: **6 / 10**
- Demonstrated directed entrance **and** exit in OSM motorway/link graph: **6 / 10**
- Confirmed legal HGV permission from tags: **0 / 10** (all `unknown`)
- Unresolved / unmatched remaining: Marrakech ×2, Oum Rbii ×2

No facility is described as verified truck-accessible from name/distance/bearing alone.

---

## 4. Network size and baseline distances

| Metric | Task 01 | Task 01B | Notes |
|---|---:|---:|---|
| Nodes | 23,199 | 23,199 | Unchanged |
| Directed edges | 23,286 | 23,267 | −19 after stopping likely double-expansion; MultiDiGraph |
| Parallel `(u,v)` collisions if DiGraph | n/a | **0** | Documented in manifest `graph_audit` |
| Casa→Agadir km | 417.00 | 417.00 | Unchanged within rounding |
| Agadir→Casa km | 417.11 | 417.11 | Unchanged |
| Asymmetry km | 0.11 | 0.11 | Unchanged |

Task 01 “verified” counts (5) are **withdrawn**; stronger access topology finds 6 entrance/exit cases after fixing Settat’s false POI, but all remain HGV-unknown and require manual review unless tags become explicit.

---

## 5. Source evidence used

- ADM directory HTML (names, partners, directions) — no coordinates.
- Geofabrik Morocco dated PBF `morocco-261106` (ODbL).
- OSM `highway=services` / fuel features for location candidates.
- OSM `motorway` / `motorway_link` topology for directed entrance/exit probes.
- ADM Trafic coordinate endpoint remains blocked/skipped offline (403 previously).

---

## 6. Tests executed (actual)

```text
pytest -q
25 passed
```

Includes offline unit tests (topology, parallel edges, inaccessible/opposite/valid access, curved geometry, skip-download, portable manifest) and integration tests on committed processed CSVs (schema, both baseline directions, edge-geometry routes).

GitHub Actions: `.github/workflows/tests.yml` runs `pytest -m "not integration"` on push/PR.

---

## 7. Remaining geographic / engineering limitations

- Marrakech and Oum Rbii still lack reliable OSM name matches.
- Motorway graph filter excludes many local `service` roads; access probes use motorway + motorway_link only.
- `entrance_and_exit` is **OSM topological** evidence only — not legal truck access, parking suitability, or grid capacity.
- Dual carriageways remain separate directed components; the full MultiDiGraph is not strongly connected.
- Electrical suitability of candidate chargers is **out of scope**.
- osmium-tool still unavailable on this Windows environment; pyrosm bbox filter is recorded in the manifest.

---

## 8. Licensing reminder

Python research code licence ≠ OSM ODbL. Derivative road/candidate databases remain under ODbL with attribution and share-alike obligations.
