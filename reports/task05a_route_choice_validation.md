# Task 05A — Route-choice validation

## Stage 1 — B&B certification safeguards

| Gate | Result |
|---|---|
| Config validation (nonnegative CAPEX, positive weights, unique IDs, budgets, CRF) | Pass (`test_placement_config_validation.py`) |
| OPTIMAL + replay failure ⇒ `uncertified=True` (no false prune) | Pass (`test_placement_replay_certification.py`) |
| Secondary-cost prune fires (`prune_secondary > 0`) + matches enum | Pass (`test_secondary_prune_with_expensive_committed`) |
| MRLS memo fingerprint includes physics/scenario inputs | Pass (weather/GCM change ⇒ cache miss) |

## Stage 4 — Synthetic branching graphs

Config: `configs/optimization/synthetic_route_choice.yaml`. Tests in `tests/unit/test_route_choice.py`:

1. Shortest-distance path rejected when energy-infeasible; longer path optimal; MRLS = reference  
2. Lower-cost longer/branched route preferred when both feasible  
3. Activating a charger changes the optimal route; removing it restores the long path  
4. Reverse OD with only forward arcs is infeasible  
5. Refrigeration-elevated discrete load can render a mission infeasible  
6. Diverse path discovery returns alternatives on a toy digraph  

## Stage 5 — Moroccan multi-route experiments

Command: `python scripts/run_multiroute_experiments.py`  
CSV: `results/multiroute_experiments.csv`

### Path set

All six OD pairs (Casa↔Agadir, Casa↔Marrakech, Marrakech↔Agadir) have **4** verified directed alternatives each (24 path records). Exact MRLS is over a **path-set model**: `O → R_i → D` for each alternative `i` (not full 100k-edge OSM MRLS).

### Results summary (illustrative 1.0 kWh/km scenario rate)

| OD | Full battery | Low battery (200 kWh) | Low battery + hypothetical mid-route charger |
|---|---|---|---|
| casa_agadir | OPTIMAL (shortest route) | INFEASIBLE | INFEASIBLE (half-leg still too long) |
| agadir_casa | OPTIMAL (shortest) | INFEASIBLE | INFEASIBLE |
| casa_marrakech | OPTIMAL (shortest) | INFEASIBLE | OPTIMAL (charger restores) |
| marrakech_casa | OPTIMAL (shortest) | INFEASIBLE | OPTIMAL |
| marrakech_agadir | OPTIMAL (shortest) | INFEASIBLE | OPTIMAL |
| agadir_marrakech | OPTIMAL (shortest) | INFEASIBLE | OPTIMAL |

Interpretation:

- With a full battery, MRLS selects the **shortest-distance** verified alternative (road-cost ∝ length under the scenario model).  
- With a depleted battery and **no** charger, all ODs are energy-infeasible.  
- A **hypothetical** charger on the shortest-route mid-node restores feasibility for the Marrakech-linked ODs, showing routing–charging interaction. Long Casa–Agadir legs remain infeasible at 200 kWh init under this quantized model—reported honestly.  
- Chargers are **not** claimed as verified HGV-accessible infrastructure.

### Continuous replay

Moroccan path-set instances use discrete fixed `dE`/`dt` arcs (scenario consumption × length, scenario speed). Discrete replay is checked. Full continuous DEM micro-replay on every alternative geometry remains future work (Task 05B/physics coupling); network geometries and path OSM node sequences are retained in `path_alternatives.csv` / `decision_graph.json`.

## Limitations (honest)

- Exactness only over the **selected verified path set**, not nationwide OSM.  
- Scenario speeds / mean kWh/km are research parameters, not observed truck telemetry.  
- HGV legality mostly `unknown` in OSM; explicit `no` filtered.  
- Placement B&B is **not** re-coupled to multi-route choice here (Task **05B**).  
- No fabricated road links.

## Reproducibility

```bash
python scripts/build_multiroute_pilot.py --skip-download
python scripts/run_multiroute_experiments.py
pytest -q tests/unit/test_route_choice.py tests/unit/test_placement_config_validation.py tests/unit/test_placement_replay_certification.py tests/unit/test_branch_and_bound.py
```
