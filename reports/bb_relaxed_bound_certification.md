# B&B budget-relaxed bound certification

## Defect

`evaluate_multiroute_subset` previously set `certified = budget_ok and routing_ok`. Coverage upper bounds evaluate `installed ∪ undecided` while relaxing the budget; an over-budget but routing-resolved superset was marked uncertified, blocking safe pruning.

## Correction

- `certified` := all mission evaluations routing-resolved (not uncertified).
- `budget_ok` remains separate.
- Incumbents require `certified and budget_ok` (`_lex_better`).
- Leaves still reject over-budget CAPEX via explicit infra check.
- LIMIT_REACHED / invalid replay still cannot certify bounds or global optimality.
- Dedicated budget-relaxed coverage-UB path: `evaluate_coverage_ub_fn` /
  `evaluate_multiroute_subset(..., relax_budget=True, max_capex=None)` so the
  UB evaluation does not inherit the original installation budget.

Monotonicity assumption unchanged: independent missions, optional sites, no shared charger capacity (see `placement_bounds.py`).

## Synthetic shared-road 8-site benchmark (after fix)

| Budget / row | Key fields |
| --- | --- |
| B2/cold | agree=True opt=CERTIFIED_OPTIMAL nodes=111 prune_cov=0 mrls=308 bb_sec=0.7578840000205673 faster=enumeration |
| B2/warm_shared_after_enum | agree=True opt=CERTIFIED_OPTIMAL nodes=111 prune_cov=0 mrls=308 bb_sec=0.69135079998523 faster=enumeration |
| B3/cold | agree=True opt=CERTIFIED_OPTIMAL nodes=139 prune_cov=0 mrls=412 bb_sec=1.7217826999840327 faster=enumeration |
| B3/warm_shared_after_enum | agree=True opt=CERTIFIED_OPTIMAL nodes=139 prune_cov=0 mrls=412 bb_sec=1.4615352000109851 faster=enumeration |
| Ball/cold | agree=True opt=CERTIFIED_OPTIMAL nodes=173 prune_cov=0 mrls=692 bb_sec=2.18962509999983 faster=branch_and_bound |
| Ball/warm_shared_after_enum | agree=True opt=CERTIFIED_OPTIMAL nodes=173 prune_cov=0 mrls=692 bb_sec=0.002549199969507754 faster=branch_and_bound |

Do **not** claim B&B is generally faster than enumeration. Report observed nodes/prunes/runtime honestly.

## Reproduction

```bash
python scripts/run_bb_relaxed_bound_benchmark.py
pytest -q tests/unit/test_branch_and_bound.py
```

CSV: `results/bb_relaxed_bound_before_after.csv`
