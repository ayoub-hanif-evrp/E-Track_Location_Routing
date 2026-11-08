# Task 03B — Discretization and continuous replay validation

## Quantization policy

| Quantity | Rule |
|---|---|
| Time | Ceil continuous travel / charge duration to 5 min steps |
| Ending energy | Floor continuous kWh onto the energy quantum grid |
| Charge increments | Multiples of the energy quantum (default 5 kWh) |
| Costs | Nonnegative road + electricity (required for cost-priority optimality) |

This bias is **conservative for feasibility**: discrete remaining energy never exceeds continuous remaining energy; discrete time never understates continuous travel time.

## State-dependent DRIVE tables

Each macro-arc stores, for every start \((E_\mathrm{truck}, E_\mathrm{trailer})\):

- `feasible` / reason (`peak_motor_power_exceeded`, SOC floors, …)
- `dt_steps`, `E_end_truck`, `E_end_trailer`

Tables are built with Task 02B `apply_drive` on micro-segments local to the macro-arc. Flat scenarios use \(dz=0\). DEM scenarios use a **macro-local** slice of the corridor COP-DEM profile (distances reset to 0).

## MRLS validation gates (pre-Morocco)

- `K_dominance_stress`: dominated twin arc pruned (`labels_dominated ≥ 1`); optimum unchanged with dominance off.
- Independent transition oracle (`tests/unit/test_transition_oracle.py`) with hand numbers; does not import production helpers for expected values.
- `validate_routing_instance` rejects negative costs, bad \(\eta\), capacities, dangling arcs/stations.
- `replay_solution` reconstructs START→actions and matches solver cost/energies on synthetic optima.

## Continuous replay

For every reported `OPTIMAL` Moroccan solution, `continuous_replay` re-simulates DRIVE micro-profiles and continuous charge/wait drains from the initial SOC. Failures mark `continuous_replay_ok=false` and invalidate Moroccan mission claims for that row.

Discretization gaps recorded in CSV: `delta_energy_kwh`, `delta_time_s` (continuous − discrete).

## Grid sensitivity

Default corridor grid: **5 kWh / 5 min**. Selected no-charger (S1) light/flat Casa→Agadir also run at **1 kWh**. Agreement of status/feasibility across grids supports that the 5 kWh control of state-space size does not flip the light no-charge conclusion.

## Experiment highlights (research, not operational)

From `results/morocco_routing_experiments.csv` (flat, cool weather):

- **Light GCM:** S1 feasible with **no** en-route charge; continuous replay OK.
- **Heavy GCM:** S1 **INFEASIBLE** without chargers (matches Task 02B SOC shortfall).
- **S2:** one mid-corridor hypothetical charger restores OPTIMAL heavy missions (~115–120 kWh charge at Benguerir).
- **S4:** differentiated prices shift Agadir→Casa charging toward cheaper Settat vs uniform-price Benguerir.
- **S5:** config A (TRU on tractor) needs slightly more charge than B on Casa→Agadir heavy/flat.

DEM rows: corridor profiles are quality=`valid` for both directions, but **Agadir→Casablanca** DEM tables mark the first macro-arc infeasible for essentially all start energies due to `peak_motor_power_exceeded` at 80 km/h cruise — chargers cannot restore those missions. Casa→Agadir DEM remains solvable for light GCM with en-route charge; heavy DEM stays infeasible even with all hypothetical chargers (grade + energy coupling).

## Map legend

`reports/figures/morocco_routing_corridor_map.*`: OSM directed baseline path vs **assumed** `entrance_and_exit` access points. Snap distances are scenario uncertainty, not verified HGV access.
