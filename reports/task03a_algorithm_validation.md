# Task 03A — Algorithm validation

**Claim scope:** Exact agreement between custom MRLS and an independent exhaustive discrete-state reference solver on finite integer-grid synthetic instances A–J. **Not** continuous charging optimality; **not** Moroccan network optimality.

---

## 1. Benchmark summary

Command: `python scripts/run_routing_benchmarks.py`  
Output: `results/routing_benchmarks.csv`

| Instance | MRLS | Ref | Objective | Notes |
|---|---|---|---|---|
| A_no_charge | OPTIMAL | OPTIMAL | 10 | No charge |
| B_charge_required | OPTIMAL | OPTIMAL | 90 | Charge 40 kWh at S |
| C_station_unavailable | INFEASIBLE | INFEASIBLE | — | Active set empty |
| D_alternative_roads | OPTIMAL | OPTIMAL | 24 | Longer feasible path |
| E_partial_charge | OPTIMAL | OPTIMAL | 156 | Charge 15 (not full) |
| F_refrigeration_trailer | INFEASIBLE | INFEASIBLE | — | Config B TRU drain |
| G_soc_boundary | INFEASIBLE | INFEASIBLE | — | Mid-path SOC floor |
| H_directionality | INFEASIBLE | INFEASIBLE | — | One-way |
| I_dominance | OPTIMAL | OPTIMAL | 90 | Dominance on ≡ off |
| J_deadline | OPTIMAL | OPTIMAL | 50 | Cheap slow path cut |

All rows: `match_ref=True`, `match_expected=True`.

---

## 2. Dominance ablation (Case I)

Same optimum with `use_dominance=True` and `False` (objective 90). Dominance is conservative same-(node, time) Pareto including `can_charge`.

---

## 3. Physics adapter

[`apply_drive`](src/morocco_etruck/energy/transitions.py) accepts incoming SOC. Synthetic arcs are exact on-grid (no rounding). Full-trip `evaluate_route` remains start-from-full-SOC for Task 02 pilots.

---

## 4. Solver statuses

`OPTIMAL` / `INFEASIBLE` / `LIMIT_REACHED` are distinct. Computational limits never reported as INFEASIBLE.

---

## 5. Limitations

- Discrete 1 kWh / 5 min grid only.
- One CHARGE burst per visit (documented modeling choice).
- No upper-level station placement; no nationwide routing.
- Provisional ADM sites are not treated as operational chargers.
