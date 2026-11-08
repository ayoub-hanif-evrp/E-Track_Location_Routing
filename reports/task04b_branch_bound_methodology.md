# Task 04B — Certified charger-placement branch-and-bound methodology

## Scope

Exact lexicographic charger **placement** on the Task 04A Morocco pilot (five directional binary sites), with MRLS leaf evaluation and proved pruning. No ALNS/GA/PSO/Gurobi. STOP after 04B.

## Financial period (illustrative)

Planning period = **one year**. `CRF × CAPEX` is an annualized illustrative infrastructure cost. Mission `weight` is an illustrative annual demand index, so `Σ w_m C_var,m` is an annual operating-cost index. Units are compatible for the lex objective; they are **not** Moroccan market prices. Same lex objective as Task 04A: maximize serviceable coverage, then minimize secondary cost.

## Stage 1 fixes carried into 04B

1. **Terrain fingerprint** — `terrain_sample_hash` digests the full `distances_m`, `elevations_m`, `valid_mask`, and `source` (no head/tail truncation). `DRIVE_TABLE_CACHE_VERSION = 04b.1`.
2. **Global certification** — `CERTIFIED_OPTIMAL` only if every budget-feasible competitor is resolved (or bound-dominated). Unresolved competitors ⇒ `INCUMBENT_UNPROVED`. Also: `NO_FEASIBLE`, `LIMIT_REACHED`.
3. **Serviceability taxonomy** — full direction-compatible install probe per mission: `serviceable` | `peak_motor` | `unserved_all_candidates` | `limit_reached` | `replay_invalid`. Structural reporting uses **`peak_motor` only**.

## Node state

```text
BBNode:
  installed, excluded, undecided   # partition of all sites
  committed_capex, depth
  last_branch: (site_id, install|exclude) | None
  status: open | pruned_* | incumbent | …
```

Branch on next undecided site (deterministic id order): Install child and Exclude child.

## Pseudocode

```text
incumbent ← none; open ← {root}
while open:
  N ← pop(open)   # DFS order (heuristic only)
  if committed_capex(N) > B: prune_budget; continue
  if undecided(N)=∅:
     eval ← evaluate(installed); update incumbent if certified lex-better; continue
  ub ← coverage_UB(N)   # MRLS on installed ∪ undecided (budget relaxed)
  if not ub.certified: branch; continue   # never prune on uncertified bound
  if ub.cov < cov(incumbent): prune_coverage; continue
  if ub.cov == cov(incumbent):
     lb ← CRF·CAPEX(installed) + Σ w_m C_var_m(UB)
     if lb > sec(incumbent)+ε: prune_secondary; continue
  branch on next site
```

Search complete with all open nodes resolved/pruned by proved bounds ⇒ `CERTIFIED_OPTIMAL`.

## Bound proofs (locked)

### Feasibility monotonicity (assumption)

Independent missions, optional charging, no capacity/queues, nonnegative costs, fixed paths: adding a compatible site cannot make a feasible mission infeasible, and cannot increase that mission’s optimal discrete operating cost.

Invalidated by shared charger capacity, queues, coupled schedules, negative costs, or mandatory energy-increasing detours.

### Coverage upper bound

Active stations = direction-filter(`installed ∪ undecided`). Budget is relaxed (undecided free). By monotonicity, any descendant’s served weight ≤ this value when the evaluation is **certified**. Uncertified MRLS/replay ⇒ **do not prune**.

### Secondary-cost lower bound

When `ub_cov = cov*` and UB is certified:

`LB = CRF · CAPEX(installed) + Σ_{m served in UB} w_m · C_var_m(UB)`

Prune only if `LB > sec* + ε` (strict).

### Budget pruning

`committed_capex > B` ⇒ prune (nonnegative CAPEX).

## Memoization

`placement_cache.PlacementMemo` keys:

`(mission_id, frozenset(active_station_keys), price_mode, energy_model_fingerprint, q, time_step_min)`

Shared across subsets/nodes/budgets within a price mode. Invalidated when the energy-model fingerprint changes.

## Modules

| Module | Role |
|---|---|
| `branch_and_bound.py` | Search + Morocco runner |
| `placement_bounds.py` | UB/LB + proof docstrings |
| `placement_cache.py` | MRLS memo |
| `placement_certification.py` | Status / serviceability enums |
| `synthetic_placement.py` | Synthetic 12-site demo (not Moroccan traffic) |
| `scripts/run_branch_and_bound.py` | 32-scenario match + synthetic prune stats |
