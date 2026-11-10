# Task 06B — B&B certification after objective change

## Bound validity

Assumptions in `placement_bounds.py` were reassessed for both operating-cost modes:

- Optional charging, no queues / shared capacity.
- Nonnegative CapEx and nonnegative operating costs (road, en-route charge, terminal shortfall).
- Ignore-new-station: adding a compatible site cannot worsen feasibility or optimal mission \(C_{\mathrm{var}}\) when terminal tariff/η are fixed and nonnegative.

Coverage UB and secondary LB therefore remain valid with \(C_{\mathrm{var}}\) = selected-mode MRLS objective. Uncertified or `LIMIT_REACHED` evaluations still disable coverage/secondary pruning.

## Empirical enum ↔ B&B

Every fully completed cell in `results/task06b_placement_grid_comparison.csv` reports `enum_agreement=True`.

Prune counts on this three-site instance remain **zero coverage / zero secondary** (budget prunes only) — consistent with Task 05C/06A: algorithmic agreement, not speedup evidence.

## Certification layers (unchanged taxonomy)

1. **Certified discrete optimum** — enum↔B&B on the finite site set + path union + energy/time grid + objective mode.
2. **Continuous-replay validation** — served missions must pass arc-id continuous physics replay.
3. **Real-world uncertainty** — HGV access, measured speeds, DEM/weather field validity, and config B are **out of scope** for Moroccan claims in 06B.

## Road-cost representation

Charger-split children redistribute a parent integer road cost via `allocate_path_road_costs(..., total_units=parent)` so \(\sum\) children = parent. Legacy path-set `max(1,…)` floors removed. Independent rounding of originally distinct alternatives may still differ by ±1 from a hypothetical path-total; that residual is measured, not hidden.

## Remaining limitations

- Config A only in the Moroccan adapter.
- q=2 replenishment: Agadir-low `LIMIT_REACHED` — partial portfolio only.
- Small site set; B&B pruning power not demonstrated.
- Illustrative tariffs/CAPEX, not Moroccan market data.
