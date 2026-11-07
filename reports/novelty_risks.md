# Novelty / overlap risks (Task 01 literature check)

**Access note:** This note is based on **publicly available abstracts and repository pages** accessed during Task 01 (access date ≈ 2026-11-07). Full texts behind publisher paywalls were **not** used. Do not treat this as a complete literature review.

Morocco as a case study is **not** by itself a novelty claim.

---

## 1. Plaza et al. (2026) — charger location with routing and driver HOS

- **Citation:** Conrado Vidotte Plaza, Okan Arslan, Gilbert Laporte, Glaydston Mattos Ribeiro, Laura Bahiense, Glaubos Clímaco. *The charger location problem with routing and driver working hours for long-haul electric heavy-duty trucks.* Transportation Research Part C, DOI: [10.1016/j.trc.2026.105598](https://doi.org/10.1016/j.trc.2026.105598).
- **What the abstract establishes:** Joint optimization of charger **locations, types, and quantities** together with long-haul eHDT **routing** and **driver hours-of-service** scheduling. Road network is transformed into a **communication-time-expanded network** via temporal discretization; model-reduction mechanisms are proposed; numerical experiments assess efficiency and feature impacts.
- **Overlap risk:** High on the broad problem class “joint charger placement + electric heavy-duty routing.”
- **Distinctions still open for investigation (not proven novel here):** refrigerated trailer energy load; Moroccan motorway **service-area** candidate set grounded in operator directories; explicit treatment of **uncertain HGV access** in OSM; energy-feasibility under payload/elevation/weather as planned later phases. HOS is central in Plaza et al.; our Task 01 has **not** modelled HOS.

## 2. Cheng et al. (2026) — temperature-aware siting and sizing

- **Citation:** Xi Cheng et al. *Temperature-aware large-scale charging station siting and sizing for long-haul electric trucks.* Transportation Research Part C, DOI: [10.1016/j.trc.2026.106066](https://doi.org/10.1016/j.trc.2026.106066) (listed with 2026/2027 issue timing; abstract available online at time of check).
- **What the abstract establishes:** Bi-level framework for **locations and capacities** on the **U.S. national highway** network; upper-level greedy siting/sizing under budget; lower-level **user-equilibrium** flows with congestion, charging queues, and **temperature-dependent range**; clustering/regional decomposition for tractability. Winter vs summer impacts quantified (e.g. travel time and charging delay increases).
- **Overlap risk:** Temperature / climate-aware range and national-scale siting/sizing.
- **Distinctions still open:** refrigerated cargo (trailer TRU load, not only ambient battery derating); joint discrete candidate set from **ADM aires**; corridor-scale Moroccan freight missions; our future work is not UE traffic assignment on a national US network. Full methodological details beyond the abstract were not accessed.

## 3. Bank et al. (2025) — electrically refrigerated trailer thermal/power model

- **Citation:** D. Bank, J. P. Kobler, T. Zeller, P. Cujic, T. Seel, S. F. G. Ehlers. *Thermal and power consumption model of an electrically refrigerated trailer.* International Journal of Refrigeration, DOI: [10.1016/j.ijrefrig.2025.04.026](https://doi.org/10.1016/j.ijrefrig.2025.04.026).
- **What the abstract establishes:** Validated **thermal model** of an electrified refrigerated trailer using >40 h of test drives (−23 °C to +18 °C internal; 1 °C to 36 °C ambient) in Spain, Sweden, and Germany; detailed **TRU electrical consumption** over drive cycles; parameter identification; RMSE &lt; 0.7 °C (open-loop temperature) and &lt; 1.5% energy error (closed-loop).
- **Overlap risk:** Refrigeration energy modelling for electric trailers — highly relevant **component** literature, not a location-routing paper.
- **Distinctions:** Bank et al. provide a vehicle/trailer energy model; they do not site chargers or route fleets on a national motorway graph. Future phases of this PhD may **cite or adapt** such models rather than re-deriving them; Task 01 does **not** implement a refrigeration simulator.

---

## Provisional positioning (honest)

Relative to these abstracts, a **potential** research niche—still to be validated after deeper reading and method design—is the **joint** treatment of:

1. Candidate truck-compatible chargers at **real operator service areas** on a specific corridor,
2. **Energy-feasible** routing under **refrigerated** eHDT loads,
3. Transparent handling of **real-network data uncertainty** (OSM HGV tags, unresolved facilities),

without claiming novelty from the Moroccan geography alone and without claiming that Task 01 has solved the optimization problem (it has not).
