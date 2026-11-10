# Task 06B — Objective and replay audit

Date: 2026-11-10  
Base: `4126a53` → this checkpoint.

## Parallel-arc replay

**Defect:** discrete `replay_solution` selected DRIVE arcs by destination + first matching `road_cost`, ignoring `arc_id`. A3 `continuous_replay` keyed macros by `(u,v)` only. Neither required the journey to end at the destination.

**Fix:**

- Prefer unique `arc_id`; verify endpoints.
- Without `arc_id`, allow only a unique `u→v` candidate, or a unique fingerprint on `(road_cost, dt_steps, dE_truck_kwh)` for legacy synthetics.
- Never silently take the first of several parallels.
- Require final node = destination; check energy floors and (when provided) total objective including terminal add-on.
- Multiroute continuous replay: same identity + destination checks.

Tests: `tests/unit/test_exact_arc_replay.py`.

## Operating-cost modes

| Mode | Definition | Units |
| --- | --- | --- |
| `enroute_incremental_cost` (legacy) | \(\sum c_{\mathrm{road}} + \sum p_s E^{\mathrm{grid}}_s\) | integer cents (road illustrative km×rate) |
| `energy_replenishment_cost` | legacy \(J\) + \(p^{\mathrm{repl}}\lceil\max(0,E^{\mathrm{target}}-E^{\mathrm{final}})/\eta\rceil\) | same cents |

Locked defaults: \(E^{\mathrm{target}}=E^{\mathrm{truck}}_{\mathrm{cap}}\); \(p^{\mathrm{repl}}=20\) ¢/grid-kWh; \(\eta=0.95\) (research scenario from pilot YAML). Trailer shortfall valued only when config-B fields are present; Moroccan adapter remains config A.

**Interpretation:** legacy treats departure energy as sunk and does not value terminal SOC. Replenishment prices the shortfall to a declared target without double-counting en-route purchases.

## MRLS termination

- Legacy: first destination label popped by (en-route cost, time) remains optimal.
- Replenishment: maintain incumbent \(J^*=J_{\mathrm{enroute}}+c^{\mathrm{term}}\); do not expand from destination; prune any label with `cost >= J*` (residual en-route + terminal ≥ 0). Empty heap ⇒ return incumbent.

Same rule in `reference_solver`. Dominance on \((J_{\mathrm{enroute}},E^{\mathrm{tr}},E^{\mathrm{tl}})\) at fixed \((v,t)\) remains valid under nonnegative prices.

Tests: `tests/unit/test_terminal_energy_cost.py` (MRLS ≡ reference; first destination ≠ global under replenishment).

## Illustration (Casa→Marrakech, chargers available)

At q=10, same Settat charge pattern under both modes for the low-battery mission, but replenishment objective is much larger because terminal shortfall to full usable pack is priced (~11 k¢ for ~540 kWh grid energy at 20 ¢ after η).

Historical Task 03–06A CSVs are **not** rewritten; they remain legacy-objective artifacts.
