# Dataset construction, selection and quality report

Generated (UTC): 2026-11-25T18:19:58.994024+00:00
Baseline commit: `8b0cbf716cc342550299895d4da58889b8239d37`

## Verified counts vs claimed

| Metric | Claimed | Verified |
|---|---:|---:|
| motorway_nodes | 58002 | 58002 |
| motorway_edges | 58157 | 58157 |
| expanded_nodes | 391653 | 391653 |
| expanded_edges | 397255 | 397255 |
| decision_nodes | 198 | 198 |
| decision_arcs | 293 | 293 |
| od_pairs | 18 | 18 |
| path_records | 36 | 36 |
| service_area_inventory | 19 | 19 |
| headline_missions | 14 | 14 |

### Discrepancies
- {'metric': 'expanded_nodes_vs_graph_audit', 'claimed': 391653, 'verified': 391885, 'note': 'CSV n_nodes after isolate removal; graph_audit may be pre-prune'}

### Graph-audit note
Multiroute `graph_audit.n_nodes`=391885, `n_edges_multidigraph`=397493 vs CSV after isolate removal 391653/397255.

## Network layers

- **Motorway-only**: routing baseline for facility access probes / A3-style baselines; 58002 nodes, 58157 edges; directed length 3964.3 km; approx unique physical 3964.3 km.
- **Expanded (motorway+trunk+primary)**: used to construct multi-route OD alternatives; 391653 nodes, 397255 edges; directed length 17496.5 km; approx unique physical 17496.5 km.
- **Decision graph**: path-union reduction to 198 nodes / 293 arcs for operational search. Exact optimality claims apply only on this selected graph.

## OD selection

- **18 constructed directional OD pairs** (36 path records = 2 alternatives each).
- **14 headline missions** exclude the four Oujda-related ODs: fes_oujda, oujda_fes, casa_oujda, oujda_casa.
**Why Oujda ODs are excluded from the headline campaign:** they extend the eastern Fes–Oujda / Casa–Oujda corridor beyond the core Atlantic–Atlas long-haul panel used for matched I0–I2 infrastructure comparison; several eastern ADM sites (Laayoune, Msoun) remain OSM-unmatched with unresolved directed access; including them would expand geography and confound the Benguerir/Larache infrastructure ladder without a separate eastern candidate set.

## Candidate selection

- **19** ADM service-area inventory records; **11** matched with entrance_and_exit; **9** retained in the core headline candidate pool after exclusion rules (unmatched, opposite-carriageway-only, eastern corridor, off-panel corridors).
Excluded inventoried sites include unmatched Marrakech/Oum Rbii/Laayoune/Msoun entries, Berrchid (opposite carriageway only), and Bir Jdid (Safi corridor, outside headline OD unions).
**Chargers are hypothetical research installations** at matched service areas — not claimed as existing operational truck chargers.

## HGV accessibility

Expanded-network HGV tags are overwhelmingly **unknown**. Unknown must not be treated as confirmed legal HGV accessibility.

## Quality checks (summary)

- [pass] `motorway_duplicate_node_ids` n=0: duplicate OSM node ids
- [pass] `motorway_invalid_coords` n=0: non-finite lon/lat
- [pass] `motorway_coords_outside_morocco_bbox` n=0: outside loose MA bbox
- [pass] `expanded_duplicate_node_ids` n=0: duplicate OSM node ids
- [pass] `expanded_invalid_coords` n=0: non-finite lon/lat
- [pass] `expanded_coords_outside_morocco_bbox` n=0: outside loose MA bbox
- [pass] `motorway_duplicate_edges` n=0: duplicate u,v,key
- [pass] `motorway_nonpositive_length` n=0: length_m <= 0
- [warn] `motorway_hgv_tag_unknown_fraction` n=58157: counts={'unknown': 58157}; unknown HGV must NOT be treated as confirmed legal access
- [pass] `expanded_duplicate_edges` n=0: duplicate u,v,key
- [pass] `expanded_nonpositive_length` n=0: length_m <= 0
- [warn] `expanded_hgv_tag_unknown_fraction` n=397255: counts={'unknown': 397255}; unknown HGV must NOT be treated as confirmed legal access
- [pass] `dem_unrealistic_grade_gt_20pct` n=0: arcs with |grade|>0.20
- [warn] `dem_non_valid_quality` n=1: {'valid': 176, 'invalid': 1}
- [pass] `weather_cache_files_present` n=18: files under C:\Users\AYOUB\OneDrive - EMSI\Bureau\PHD_WORK\E-Track_Location_Routing\data\raw\weather
- [info] `candidate_matched_entrance_and_exit` n=11: match={'matched_osm': 12, 'unmatched': 7}; access={'entrance_and_exit': 11, 'unresolved': 7, 'opposite_carriageway_only': 1}

## Constructed vs observed freight

OD missions and path alternatives are **constructed research scenarios**, not observed freight-trip diaries. Demand weights in experiments are analytical (unit weight), not calibrated flows — do not encode line thickness as freight volume.
