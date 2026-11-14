# Final algorithm benchmark audit

Reviewed after correcting [`scripts/run_task08_final_validation.py`](../scripts/run_task08_final_validation.py) `run_shared_road_benchmark()`.

Historical Task 08 HEAD numbers (pre-instrumentation fix) are preserved in
`results/task08_algorithm_benchmarks_historical_8site.csv`.

## Defects fixed

| Issue | Before | After |
| --- | --- | --- |
| Subset `certified` | Hardcoded `True` | `False` iff any mission returns MRLS `LIMIT_REACHED` |
| `bb_mrls_calls` / hits | Always 0 (no `PlacementMemo`) | Counted via real memo get/put |
| Timing fairness | Enum then B&B on shared evaluator state; prep untimed | Cold-cache primary (fresh memo each method) + warm-shared secondary |
| Claim | Implied algorithmic speed story | Correctness / pruning demo; speed reported honestly |

Unit guard: `test_mrls_limit_reached_style_uncertified_blocks_certified_optimal` in
`tests/unit/test_branch_and_bound.py`.

## Corrected cold-cache results (8-site synthetic)

| Budget | Enum (s) | B&B (s) | Faster | Enum MRLS calls | B&B MRLS calls | Agree | Status |
| --- | ---: | ---: | --- | ---: | ---: | --- | --- |
| B2 | 0.12 | 0.79 | enumeration | 88 | 308 | True | CERTIFIED_OPTIMAL |
| B3 | 0.46 | 1.08 | enumeration | 176 | 412 | True | CERTIFIED_OPTIMAL |
| Ball | 4.14 | 1.41 | branch_and_bound | 1024 | 692 | True | CERTIFIED_OPTIMAL |

Warm-shared (enum first, then B&B on the same memo) makes Ball B&B near-instant via cache hits; that row is **secondary** and must not be used as a cold-start speed claim.

## What this does / does not show

- **Does:** enum and B&B agree on the optimum for this synthetic shared-road instance; certification status is honest; MRLS call counters are non-zero and meaningful.
- **Does not:** prove a general B&B wall-time advantage. On this instance enumeration is faster for B2 and B3; B&B is faster only for the full Ball budget under cold cache.
- **Does not:** demonstrate nationwide Moroccan scalability.

The eight largely interchangeable charger branches with a common optimal cheap site remain a **correctness** benchmark, not a hard joint-placement stress test.
