# Task 04A — Joint placement problem formulation

## Scope

Exact exhaustive benchmark over **five directional hypothetical** charger sites on the fixed A3 baselines. No branch-and-bound. Sites are research candidates (`entrance_and_exit` topology only), not certified HGV chargers. Opposite-direction facilities do **not** share installation decisions.

## Upper-level decisions

Binary variables `y_s ∈ {0,1}` for

`y_settat_ca`, `y_benguerir_ca`, `y_amskroud_ca`, `y_settat_ac`, `y_benguerir_ac`.

Budget: `Σ_s y_s · CAPEX_s ≤ B` with illustrative CAPEX from YAML.

## Lexicographic objective

1. **Primary:** maximize `Σ_{m served} w_m` (demand weight of missions with OPTIMAL MRLS + continuous replay OK).
2. **Secondary:** among equal coverage, minimize  
   `CRF · Σ_s y_s · CAPEX_s + Σ_{m served} w_m · C_var,m`  
   where `C_var,m` is the discrete MRLS operating cost converted by `cents_to_currency`.

CRF uses illustrative interest rate and lifetime — **not** Moroccan market financing.

### Contrast with penalty formulation

A single-objective `C_infra + C_var + π · unserved_weight` can trade coverage for money when `π` is finite. Lexicographic coverage-first **never** reduces served demand to save cost.

## Lower-level routing

For each subset and mission: activate only installed sites matching the mission direction; solve discrete MRLS on state-dependent DRIVE tables; require continuous-physics replay. `LIMIT_REACHED` marks the subset **uncertified**.

## Structural infeasibility

Missions that remain infeasible under the full direction-matched install set because of fixed-speed peak-motor limits (e.g. Agadir→Casablanca DEM) are classified **structural**. They are excluded from the serviceable-demand denominator. More chargers cannot fix a motor-power policy violation under current assumptions.

## Exactness claim

The enumeration optimum is exact for the finite candidate set and the finite discrete MRLS instances when all relevant subproblems are certified (OPTIMAL or INFEASIBLE). It is **not** a continuous real-world infrastructure optimum.
