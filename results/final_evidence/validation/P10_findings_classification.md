# P10 — Central findings classification

Baseline freeze: `518bc11`. Journal corrections may refine interpretation without silently rewriting coverage.

| Finding | Support | Experiment / data | Mechanism | Limitations |
|---|---|---|---|---|
| I0→I3 directional installs raise eActros/Volvo operational coverage on the 14-OD × 2-SOC panel | Supported within the model | `primary_i0_i3_missions.csv` (224 cells) | En-route directional charging reduces reserve violations | Equal mission weights; constructed ODs; 5.3 t headline; hypothetical installs |
| Volvo Marrakech→Agadir @80% I2 energy-OK / ops-INF at 5 min is HOS **ceil inflation** (phys 265.6 < 270; disc 285) | Supported within the model | `time_discretization/*` | Per-arc `ceil(dt/ts)` on continuous-driving resource | Modeled uninterrupted-break HOS; not full multi-day regulation |
| Refining ts to 2/1 min restores Volvo MA ops feasibility without relaxing physical HOS | Supported only under specified conditions | `hos_timestep_sweep.csv` | Discrete resource ≤270 | Must not mix into unlabeled 5-min coverage table |
| Casa–Tangier waiting (10+35 min) forms modeled 45 min break under discrete inflation | Supported within the model | `casa_tangier_wait_schedule_excerpt.csv` | Modeled break policy + ceil | Not proven legally mandatory beyond model |
| Missing child DEM JSON was visualization-only; solver used parent slices | Supported within the model | `executed_route_summary.csv` | `build_macro_with_terrain` parent window | GIS figures must use P1 reconstruction |
| Arc 343a… ~23% max grade is a 2.6 m DEM artifact | Supported within the model | `P1_steep_gradient_*.md` | Short sampling interval | Do not auto-clip; report length context |
| Nominal tomato refrigeration is a tiny share of traction; hot+UA×1.5 still small; no I1 infra change on tested cells | Supported within the model | `refrigeration_controlled_missions.csv` | Electrical demand model; precooled cargo | Not cargo-temperature compliance; Bank et al. not calibrated here |
| 5.3 t is a light research assumption; 10–15 t can remove I1 feasibility at stressed SOC on Casa–Marrakech/Agadir | Supported within the model | `heavier_payload_infra_missions.csv` | Mass → traction energy | Finite matched set, not full 224 re-panel |
| Volvo Settat vs Benguerir preference reversal | Supported only under specified conditions | Volvo matched infra panel @5 min | Corridor/SOC-specific enablement | Intersection-only efficiency comparisons |
| External eActros ~1.03 kWh/km @40 t | Order-of-magnitude plausibility | Tour 2024 + modeled samples | Dissimilar payload/terrain/fridge | Not calibration |

## Explicit non-claims (surviving)

- Constructed OD scenarios ≠ observed freight trips
- Equal mission weights ≠ national demand
- Hypothetical directional installs; unverified commercial charger / HGV access
- No Moroccan BEV field calibration
- Assumed refrigeration UA/COP; simplified single-duty HOS
- Restricted route alternatives; no queuing / fleet / grid / economic sizing
- No global minimum-infrastructure proof

## Campaign gate

- Correctness gates for P0 mechanism + P1 geometry: **pass**
- Headline coverage rewritten under 1–2 min HOS: **not done** (correct — labeled sensitivity only)
- Remaining: release manifest regeneration + clean-checkout verify; literature matrix present
