# Task 08 — Algorithm performance (synthetic shared-road)

Label: **synthetic**. Not Moroccan traffic. Not national-scale proof.

Benchmark: 8 candidate sites on a shared trunk + long alternate path; 4 missions with battery limits; enum vs B&B.

| Budget | enum sites | bb sites | agree | enum_s | bb_s | nodes | prune_cov | prune_cost | status |
| --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | --- |
| B2 | s00 | s00 | True | 0.1145270999986678 | 0.9462515000050188 | 111 | 0 | 10 | CERTIFIED_OPTIMAL |
| B3 | s00 | s00 | True | 0.3095217999943997 | 1.3540575999941211 | 139 | 0 | 17 | CERTIFIED_OPTIMAL |
| Ball | s00 | s00 | True | 3.175707699992927 | 2.508414800002356 | 173 | 0 | 41 | CERTIFIED_OPTIMAL |

All reported budgets: **enumeration and B&B agree** on the synthetic shared-road instance.

Reference: independent-mission 12-site demo remains in `configs/optimization/branch_bound_benchmarks.yaml` (not shared-road).
