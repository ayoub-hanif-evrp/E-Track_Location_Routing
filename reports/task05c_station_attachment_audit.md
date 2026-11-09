# Task 05C — Station attachment audit

Date: 2026-11-09  
Base commit reviewed: `780774a`  
Scope: direction-specific ADM matching, topology-verified attach, fixed-graph splits.

## Defect corrected

At `780774a`, `select_grounded_chargers_on_union()` matched by name + `entrance_and_exit` only, then took the **first CSV row**. Reverse-direction Settat (`127661105`) and Benguerir (`127661098`) appear first. When `connected_node_id` missed the forward union, a **2,500 m proximity snap** still attached the wrong carriageway.

## Correct ADM mapping (Casablanca→Agadir)

| Site key | Travel direction | OSM id | Connected node | Access class |
| --- | --- | --- | --- | --- |
| `settat_ca` | Casablanca→Agadir | `127661106` | `1546869631` | topology_verified when on OD union |
| `benguerir_ca` | Casablanca→Agadir | `127661099` | `1547241544` | topology_verified when on OD union |
| `amskroud_ca` | Casablanca→Agadir | `1530179371` | `1873981321` | topology_verified when on OD union |

| Site key | Travel direction | OSM id | Notes |
| --- | --- | --- | --- |
| `settat_ac` | Agadir→Casablanca | `127661105` | reverse; used only on reverse ODs |
| `benguerir_ac` | Agadir→Casablanca | `127661098` | reverse; used only on reverse ODs |

## Policy (locked)

1. Specs **must** include `travel_direction` (and prefer explicit `osm_id`).
2. Baseline `allow_proximity_snap: false` — no geodesic snap for scientific topology.
3. Attach classes: `topology_verified` | `hypothetical` (snap only if explicitly enabled) | `unresolved`.
4. Ambiguous multi-hit on-union attach → unresolved (never first-row default).

## Casa→Marrakech verification (corrected pilot)

- Active stations: `settat_ca`, `benguerir_ca`
- OSM ids: `127661106`, `127661099` (forward carriageway)
- ADM connection distances: 39.05 m / 14.89 m (not proximity snaps)
- `casa_marrakech_low_flat_chg`: OPTIMAL, continuous replay OK, road ≈ **257.76 km**, charge **200 kWh at `settat_ca`**, non-shortest (`chose_shortest_distance_route=false`)

Wrong-carriageway selection is eliminated for this mission.

## Unresolved / incomplete access

- No Agadir→Casablanca Amskroud `entrance_and_exit` row in `candidate_sites.csv`.
- Marrakech→Agadir low-battery + only `amskroud_ca` remains **INFEASIBLE** (charger too late / insufficient for E_init=200 under quantum=10).
- HGV legality remains `unknown` (not certified).
- Hypothetical snap connectors are disabled in the baseline pilot.

## Tests

- `tests/unit/test_multiroute_station_direction.py` — both directions, both facility pairs, no-snap rejection, optional hypothetical snap labelling.
