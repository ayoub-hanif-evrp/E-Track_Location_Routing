# Task 08 — Algorithm performance (synthetic shared-road)

Label: **synthetic**. Not Moroccan traffic. Not national-scale proof.

Benchmark: 8 candidate sites on a shared trunk + long alternate path; 4 missions with battery limits; enum vs B&B.

| Budget | enum sites | bb sites | agree | enum_s | bb_s | nodes | prune_cov | prune_cost | status |
| --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | --- |
| B2 | s00 | s00 | True | 0.1234418000094592 | 0.7858326000277884 | 111 | 0 | 10 | CERTIFIED_OPTIMAL |
| B2 | s00 | s00 | True | 0.1543098000111058 | 0.6603202000260353 | 111 | 0 | 10 | CERTIFIED_OPTIMAL |
| B3 | s00 | s00 | True | 0.4563924999674782 | 1.0788503999938257 | 139 | 0 | 17 | CERTIFIED_OPTIMAL |
| B3 | s00 | s00 | True | 0.3870873000123538 | 0.961706400034018 | 139 | 0 | 17 | CERTIFIED_OPTIMAL |
| Ball | s00 | s00 | True | 4.137166099972092 | 1.4133544999640435 | 173 | 0 | 41 | CERTIFIED_OPTIMAL |
| Ball | s00 | s00 | True | 3.8451127000153065 | 0.0012526999926194 | 173 | 0 | 41 | CERTIFIED_OPTIMAL |

All reported budgets: **enumeration and B&B agree** on the synthetic shared-road instance.

Reference: independent-mission 12-site demo remains in `configs/optimization/branch_bound_benchmarks.yaml` (not shared-road).
