# Task 01C — Eliminate false station-accessibility results

**Reviewed commit (before):** `f5b228f44f9f9ab26358e81b0ff04576f5c30d35`  
**Pinned OSM:** `morocco-261106.osm.pbf`  
SHA-256: `e26e8b7010cf78259469f166292b351de48609b3b1f420dd469f0d49f7d05a00`

Machine-readable table: [`reports/site_access_audit.csv`](site_access_audit.csv)  
Candidates: [`data/processed/candidate_sites.csv`](../data/processed/candidate_sites.csv)

---

## 1. Original zero-length self-path bug

In Task 01B, `find_directed_access()` treated nearby **motorway carriageway nodes** as facility attachment points. When a motorway node lay near an OSM aire, the algorithm accepted a path from that node **to itself** (length **0 m**) as both entrance and exit.

All six Task 01B `entrance_and_exit` rows had `entrance_path_m = exit_path_m = 0`. That is not physical accessibility evidence.

## 2. Exact correction

1. Facility attachment nodes must have incident `motorway_link` and/or `service` edges (not pure carriageway-only motorway nodes).
2. Entrance/exit require `source ≠ target`, ≥1 edge, and length ≥ `MIN_ACCESS_PATH_M` (1 m).
3. A separate **facility-access graph** is built from the same OSM read, adding configured `facility_access_classes` (default: `service`) for probing only; the A3 **routing** graph remains motorway + motorway_link.
4. Path edge IDs are recorded (`entrance_edge_ids`, `exit_edge_ids`).
5. Residual zero-length `entrance_and_exit` rows are hard-rejected.

## 3. Duplicate directional facility matches

Task 01B picked the single highest-ranked OSM name match and reused it for both travel directions (e.g. Benguerir both → `127661098`; Settat both → `127661105`).

**Fix:** evaluate **all** plausible service-area POIs per ADM directional entry; score by directed-access quality + name side affinity; when both directions would claim the same `osm_id`, keep the better access assignment and re-match the other with that ID reserved.

## 4. New matching results (Task 01C)

| ADM facility | OSM id | Directed access | Entrance m | Exit m | HGV |
|---|---:|---|---:|---:|---|
| Amskroud Casa→Agadir | 1530179371 | entrance_and_exit | 34.35 | 42.75 | unknown |
| Benguerir Agadir→Casa | 127661098 | entrance_and_exit | 21.50 | 35.66 | unknown |
| Benguerir Casa→Agadir | 127661099 | entrance_and_exit | 14.89 | 67.49 | unknown |
| Berrechid Agadir→Casa | 286371423 | opposite_carriageway_only | — | — | unknown |
| Settat Agadir→Casa | 127661105 | entrance_and_exit | 29.75 | 75.33 | unknown |
| Settat Casa→Agadir | 127661106 | entrance_and_exit | 39.05 | 50.79 | unknown |
| Marrakech (both) | — | unmatched / unresolved | — | — | unknown |
| Oum Rbii (both) | — | unmatched / unresolved | — | — | unknown |

**Supported `entrance_and_exit` with positive lengths: 5 / 10**  
**Confirmed legal HGV from tags: 0 / 10** (all unknown)

## 5. Facilities remaining unresolved / partial

- Marrakech ×2, Oum Rbii ×2: no OSM service-area name match.
- Berrechid Agadir→Casa: OSM location found, but only **opposite carriageway** topology — not accepted for the ADM direction.

## 6. What field verification is still required

- Legal HGV / goods access at every aire (OSM tags absent → `unknown`).
- Truck parking geometry, grid capacity, charger suitability (out of scope).
- Manual confirmation of Berrechid direction-specific ramps.
- Marrakech / Oum Rbii coordinates from non-invented sources.

## 7. Before / after accessibility counts

| Metric | Task 01B (false) | Task 01C |
|---|---:|---:|
| `entrance_and_exit` claimed | 6 | **5** |
| Of which zero-length paths | **6** | **0** |
| Distinct OSM ids for dual Benguerir/Settat | No | **Yes** |
| Baseline Casa→Agadir km | 417.00 | 417.00 |
| Baseline Agadir→Casa km | 417.11 | 417.11 |
| Routing nodes / edges | 23199 / 23267 | 23199 / 23267 |

Note: pyrosm’s driving extract yielded **0** edges tagged `highway=service` inside the pilot filter for this snapshot; successful accesses use **motorway_link** attachments. Service class remains configured for future extracts.

## 8. Tests executed (actual)

```text
pytest -q
28 passed
```

Regression coverage includes: zero-length self-path rejection; proximity without connector; opposite carriageway; positive-length entrance+exit via link/service; entrance-only; independent OSM ids for opposite directions; HGV restricted vs unknown; removal of the tautological `or True` assertion.

## 9. Licensing / scope

No claim of electrical suitability or certified truck access. OSM data remain ODbL; Python code licence is separate. Energy/refrigeration/optimization **not** implemented (stop after 01C).
