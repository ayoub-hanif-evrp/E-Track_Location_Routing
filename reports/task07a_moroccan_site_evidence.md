# Task 07A — Moroccan candidate site evidence

Access date: 2026-11-11  
Sources: ADM aires de services directory; ADM Programme AZUR; in-repo `reports/site_access_audit.csv` (Task 01C).

**Problem framing:** future infrastructure planning. An ADM service area is **not** an operating 350 kW truck-compatible charger.

## Classification legend

| Class | Meaning |
| --- | --- |
| `existing_verified_truck_charger` | Documented truck-capable high-power charger with evidence |
| `existing_ev_charger_truck_access_unverified` | Some EV charger exists; truck access/power unverified |
| `hypothetical_future_truck_site` | Real ADM facility identity + topology; charger assumed for planning |
| `unresolved_access` | Identity or access not established |

## Southbound A3 candidates (Casa→Agadir)

| Site | Official ADM identity | OSM id | Directed access (OSM) | HGV (OSM) | Existing EV verified? | 350 kW truck verified? | Grid capacity | **07A class** |
| --- | --- | ---: | --- | --- | --- | --- | --- | --- |
| Settat CA | ADS SETTAT Casablanca→Agadir | 127661106 | entrance_and_exit | unknown | No (in-repo) | No | Unknown | **hypothetical_future_truck_site** |
| Benguerir CA | ADS BENGUERIR Casablanca→Agadir | 127661099 | entrance_and_exit | unknown | No | No | Unknown | **hypothetical_future_truck_site** |
| Amskroud CA | ADS AMSKROUD Casablanca→Agadir | 1530179371 | entrance_and_exit | unknown | No | No | Unknown | **hypothetical_future_truck_site** |

Topology evidence: positive-length entrance/exit paths in `site_access_audit.csv`. OSM topology ≠ legal truck certification. Parking/turning suitability unresolved.

## ADM Programme AZUR

Programme AZUR discusses EV charging at service areas in a **passenger-car** framing. It does **not** establish operating 350 kW HGV CCS/MCS chargers at Settat, Benguerir, or Amskroud in this repository’s evidence pack.

## Vehicle acceptance vs site availability

Volvo FH Electric advertises CCS ≤350 kW. That is **vehicle acceptance**, not proof that a Moroccan service area has a truck-compatible 350 kW dispenser, queue connection, or HGV parking.

## Operator / data gaps (do not invent)

- Confirm HGV legal access and parking geometry with ADM / site operators
- Confirm any existing EV hardware (connector, kW, truck bay)
- Grid connection capacity and upgrade lead times
- Contact path for AZUR / ADM infrastructure data requests

## Experiment implication

All Task 07A placement installs remain labeled `site_evidence_class=hypothetical_future_truck_site`. Results are planning recommendations under research tariffs/CAPEX, not analysis of an already-operational 350 kW motorway truck network.
