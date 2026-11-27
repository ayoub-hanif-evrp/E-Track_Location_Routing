# P9 — Literature comparison matrix (compact)

Not a manuscript. Verified bibliographic anchors and relationship to Path A evidence.

| # | Reference | Dataset / scope | Vehicle / energy | Ops constraints | Infrastructure | Validation | Relation to this work |
|---|---|---|---|---|---|---|---|
| 1 | Vidotte Plaza et al. (2026), *Transp. Res. Part C*, DOI 10.1016/j.trc.2026.105598 — charger location with routing and driver hours for long-haul e-HDTs | Constructed / stylized long-haul networks | Battery-electric heavy trucks; routing+HOS | Driver working hours with charger location | Charger siting integrated with routes | Model/algorithmic | Closest CLP+HOS peer; we fix a small directional candidate set on a Moroccan motorway graph and emphasize feasibility/physics rather than global placement optimality |
| 2 | Cheng et al. (2026), *Transp. Res. Part C*, DOI 10.1016/j.trc.2026.106066 — temperature-aware large-scale charging siting/sizing | Large-scale long-haul | Temperature-aware charging demand | Operational + temperature effects on charging | Siting and sizing | Computational case | Complements our weather/refrigeration sensitivities; we do not size grid capacity or optimize national fleets |
| 3 | Bank et al. (2025), *Int. J. Refrig.* 176:425–436, DOI 10.1016/j.ijrefrig.2025.04.026 — electrically refrigerated trailer thermal/power model | >40 h test drives (ES/SE/DE); setpoint −23…+18 °C; ambient 1…36 °C | Detailed TRU electrical model | Duty-cycle energy | n/a | Experimental (RMSE <0.7 °C; energy error <1.5% closed-loop) | Methodological inspiration for cold-chain electricity; our UA/COP tomato pack is **not** a calibrated Bank reproduction; we claim electrical demand, not cargo-temperature compliance |
| 4 | TRIP Ontario archetypal EV charging network (2023), DOI 10.1016/j.trip.2023.100825 | Provincial archetypal road network | Long-haul EV charging potential | Simplified routing | Potential location identification | GIS / network analysis | Shares TRIP applied-transport framing; we add DEM energy, refrigeration, directional access and HOS-in-search on a reduced decision graph |
| 5 | Morocco HGV energy-efficiency case study (ScienceDirect S2213624X24001159) | Moroccan road freight context | Conventional HGV energy efficiency | Operational context | n/a | Empirical/statistical (as published) | Regional freight context; does **not** calibrate our BEV physics |

## Additional relevant themes (to expand with full citations during freeze)

- Heavy-duty BEV measured consumption tours (e.g. eActros 600 European Testing Tour 2024 ≈1.03 kWh/km @40 t) — external plausibility only.
- Directional / carriageway-specific charging access studies.
- Terrain-aware energy models and numerical time/energy discretization effects on HOS feasibility.
- Refrigerated transport power measurements beyond Bank et al.

## Positioning rules (enforced)

- Do **not** claim novelty solely from combining known techniques.
- Do **not** claim first-of-kind without exhaustive evidence.
- Contribution emerges from controlled findings: directional motorway feasibility under DEM + refrigeration + HOS discretization on a constructed Moroccan corridor panel.
