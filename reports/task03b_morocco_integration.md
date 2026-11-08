# Task 03B — Moroccan corridor MRLS integration

## Scope

Connect the Task 03A multi-resource label-setting (MRLS) solver to the Casablanca–Agadir **fixed directed A3 baselines** (~417 km each way). This is **charging-stop selection on a fixed path**, not multi-path location–routing and not station placement B&B.

**In:** MRLS validation gates; physics→discrete macro-arc DRIVE tables; hypothetical chargers; S1–S5 experiments; continuous replay; CSV + map.

**Out:** nationwide search, ALNS/GA/MIP solvers, new truck physics, claims of continuous optimality or certified HGV chargers.

## Decision graph

For each direction:

1. Rebuild the baseline node sequence from the directed A3 graph and Task 01 anchors.
2. Insert **hypothetical** station nodes only where Task 01C reports `directed_access_status=entrance_and_exit` and `travel_direction` matches the mission:
   - Casa→Agadir: Settat ouest, Benguerir ouest, Amskroud
   - Agadir→Casa: Settat est, Benguerir est
3. Opposite-carriageway (Berrchid) and unresolved Marrakech / Oum Rbii sites are excluded.
4. Each station attaches to its `connected_node_id` on the baseline (snap distance recorded as **scenario uncertainty**).
5. Decision nodes: `O` → ordered on-path stations → `D`. **Macro-arcs** are baseline subpaths between consecutive decision nodes (OSM edge provenance).

Virtual charge nodes are co-located with attachment decision nodes (no extra road distance beyond documented snap). No claim of in-facility path continuity.

## Physics → discrete adapter

Simple net-\(\Delta E\) macros are **not** used as the sole DRIVE model.

For each macro-arc we precompute a **state-dependent DRIVE table**:

- Micro-segments are owned by the macro-arc (OSM edges, split ≈2 km).
- Terrain is **macro-local**: flat profiles use \(dz=0\); DEM mode slices the corridor COP-DEM profile into a local distance frame starting at 0 (no reused global `s_cursor` across unrelated edges).
- For every discrete start tractor energy quantum (and trailer quanta under config B + refrigeration), Task 02B `apply_drive` walks the micro-profile with regen headroom, aux/TRU, and peak-motor flags.
- Prefix SOC-floor or peak-power violations → infeasible from that start.
- Feasible outcomes store \((dt_\mathrm{steps}, E_\mathrm{end}, \ldots)\) with **conservative quantization**: ceil time to 5 min steps; floor ending kWh (never round remaining energy up).

Default corridor grid: **5 kWh** energy quantum, **5 min** time. Sensitivity: selected no-charger runs at **1 kWh**.

MRLS DRIVE on Morocco instances **looks up** the table (`ArcData.drive_table`).

## Hypothetical chargers

Documented in `configs/optimization/morocco_pilot.yaml`:

| Parameter | Research assumption |
|---|---|
| Power | 350 kW |
| \(\eta\) | 0.95 |
| Prices | Uniform 20 ¢/kWh grid, or differentiated (Settat 15 / Benguerir 25 / Amskroud 30) |
| Access | `hypothetical_access=true`, `hgv_status=unknown` |

## Experiment families (S1–S5)

| ID | Intent |
|---|---|
| S1 | No en-route chargers — feasibility |
| S2 | One mid-corridor hypothetical charger |
| S3 | All direction-matched hypothetical chargers — min-cost charge plan |
| S4 | Differentiated prices — location/amount shift |
| S5 | Refrigeration on, config A vs B |

Terrain matrix: **flat first**, then DEM when profile quality is `valid`. Peak-motor infeasibility at 80 km/h is reported honestly — chargers cannot fix it.

Baseline comparators (not external MIP): fixed path with **no charging**, and optional “charge full at first reachable station” heuristic.

## Outputs

- `results/morocco_routing_experiments.csv`
- `reports/figures/morocco_routing_corridor_map.geojson` (+ PNG legend map when generated)
- `reports/task03b_discretization_validation.md`

## Honesty

Stations are **not** certified HGV chargers. Discrete optimality is with respect to the finite integer-grid instance induced by the tables. Continuous replay must pass before Moroccan mission energy claims.
