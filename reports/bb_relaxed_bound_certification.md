# B&B budget-relaxed bound certification

## Defect

`evaluate_multiroute_subset` previously set `certified = budget_ok and routing_ok`. Coverage upper bounds evaluate `installed ∪ undecided` while relaxing the budget; an over-budget but routing-resolved superset was marked uncertified, blocking safe pruning.

## Correction

- `certified` := all mission evaluations routing-resolved (not uncertified).
- `budget_ok` remains separate.
- Incumbents require `certified and budget_ok` (`_lex_better`).
- Leaves still reject over-budget CAPEX via explicit infra check.
- LIMIT_REACHED / invalid replay still cannot certify bounds or global optimality.

Monotonicity assumption unchanged: independent missions, optional sites, no shared charger capacity (see `placement_bounds.py`).

## Synthetic shared-road 8-site benchmark (after fix)

Cold-cache rows from `results/bb_relaxed_bound_before_after.csv` (wall ≈ 20.8 s):

| Budget | Enum sec | B&B sec | B&B nodes | Coverage prunes | B&B MRLS | Agree | Faster |
| --- | ---: | ---: | ---: | ---: | ---: | --- | --- |
| B2 | 0.14 | 0.77 | 111 | 0 | 308 | True | enumeration |
| B3 | 0.48 | 1.80 | 139 | 0 | 412 | True | enumeration |
| Ball | 6.13 | 2.14 | 173 | 0 | 692 | True | branch_and_bound |

Historical pre-fix snapshot (`results/task08_algorithm_benchmarks_historical_8site.csv`): same optimal sites/`CERTIFIED_OPTIMAL` agreement; cold B2/B3/Ball B&B times ≈ 0.95 / 1.35 / 2.51 s with identical node counts (111 / 139 / 173). After the certification semantics fix, node structure is unchanged on this instance; runtimes remain in the same band. Coverage prunes stay 0 on this synthetic (bound does not fire here).

Do **not** claim B&B is generally faster than enumeration. Report observed nodes/prunes/runtime honestly.

## Reproduction

```bash
python scripts/run_bb_relaxed_bound_benchmark.py
pytest -q tests/unit/test_branch_and_bound.py
```

CSV: `results/bb_relaxed_bound_before_after.csv`
