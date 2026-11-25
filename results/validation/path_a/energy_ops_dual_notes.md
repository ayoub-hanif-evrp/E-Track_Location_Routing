# Energy vs ops dual (Path A corrected)

## Mechanism

`evaluate_mission_operational(..., include_energy_only=True)` runs:

1. Energy-only: `hos_in_search=False`
2. Ops: `hos_in_search=True` + schedule audit

## B1/B2 conventional discrepancy

Mission inspection (`energy_ops_limit_contamination.csv`) shows the B1/B2
energy>ops gap is driven by **`casa_agadir` under Settat (`y_settat_ca`)** returning:

- `status = LIMIT_REACHED` (HOS-on search)
- `energy_status = OPTIMAL` / `energy_feasible = True`
- `operationally_served = False`

**Interpretation (campaign rows):** unresolved computational limit at the
original budget — **not** certified HOS/physical infeasibility from those cells.

**Escalate (conclusive):** at 1200 s / 5×10⁶ expansions, Settat `casa_agadir`
is `OPTIMAL` ops=True for both fixed and multi
(`results/validation/path_a/limit_escalate/settat_casa_agadir_escalate.csv`).
The prior energy≠ops gap was LIMIT contamination, not HOS infeasibility.

## B label correction

`B_fixed_conventional` uses fixed routing with conventional Settat-first installs:

| Budget | Sites |
|--------|-------|
| B0 | (none) |
| B1 | `y_settat_ca` |
| B2 | `y_settat_ca`, `y_settat_ac` |

Never label these rows `B_baseline_none`.
