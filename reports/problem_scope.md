# Problem-scope clarification (pre–Task 02)

This note separates two mathematical problem families that must not be conflated in later papers.

## A. Fixed-corridor charging placement and charging-stop optimization

**Decision space**

- A small set of **candidate sites** along a prescribed corridor (here: ADM aires on A3).
- Routes are essentially the **motorway carriageways** already used by long-haul freight between endpoints (Casablanca ↔ Agadir).
- Optimization chooses **which candidates receive chargers**, and/or **where trucks stop to charge** along near-fixed paths, under energy/budget constraints.

**What the current pilot graph supports**

- Directed A3 dual carriageways with real lengths.
- Direction-aware candidate attachment (when OSM topology allows).
- Shortest-distance baselines as connectivity checks.

This is the natural next modelling target for Task 02 energy/charging work **on this dataset**.

## B. Genuine multi-route location–routing

**Decision space**

- Joint choice of **paths on a richer road network** (alternative motorways, trunks, urban access) **and** charger locations.
- Multiple freight missions with heterogeneous OD pairs, time windows, and fleet constraints.
- Path choice can react to missing chargers, congestion proxies, or access restrictions.

**What would be required to claim B**

- Broader highway classes (and validated HGV access), not motorway-only filtering.
- Multiple OD missions and demand data.
- Explicit modelling of alternative corridors (e.g. A1/A3 interactions, urban last-mile).
- Stronger facility access and legal-truck evidence than OSM topology alone.

**Current pilot status:** the Task 01/01B graph **does not yet support scientifically claiming problem B**. It supports **A** with honest uncertainty on HGV legality and unresolved ADM sites.

## Implication for future claims

Any optimization result built on this pilot should be framed as **corridor infrastructure / stop planning on A3 candidates**, unless and until the network and demand layers are extended to problem B.
