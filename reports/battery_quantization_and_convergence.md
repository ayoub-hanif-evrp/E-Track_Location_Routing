# Battery quantization and grid convergence

## Quantization policy

Conservative flooring after DRIVE (table build) and CHARGE/WAIT (stationary snap) is **retained**. Removing it would risk optimistic discrete feasibility.

- Novel algorithm claim: `False`
- Adopted representation change: `None`
- Alternatives decision: adopted=`False`; safe_within_scope=`finer_fixed_grids_only`
- Rationale: Removing flooring would risk optimistic discrete feasibility. Publication-facing infrastructure claims require fine-grid stability (see battery_quantization_and_convergence report).

Unit proof that CHARGE can yield zero discrete gain: `tests/unit/test_quantization_error_and_charge.py`.

## Northbound canonical max_alts=4 (eActros, peak-adapt)

| q | Ball | Sites | Drive floor loss kWh | Charge/WAIT loss kWh | MRLS gen/exp | Peak MiB | sec |
| --- | --- | --- | ---: | ---: | --- | ---: | ---: |
| 10 | INFEASIBLE |  | None | None | None/None | 415.1 | 54.4 |
| 5 | OPTIMAL | y_benguerir_ac | 42.22854304689406 | 3.465283209662516 | 10596/3840 | 416.0 | 80.6 |
| 2 | OPTIMAL | y_benguerir_ac | 14.773847757165612 | 1.1230189769500214 | 88207/22290 | 436.6 | 544.7 |
| 1 | OPTIMAL | y_benguerir_ac | 7.773847757165612 | 0.1230189769500214 | 320961/66017 | 411.6 | 1243.4 |

**Verdict:** among **served** northbound rows (q = 5, 2, 1) the Ball optimum is stable at **`{y_benguerir_ac}`**. At **q = 10** the same physical graph is Ball-**INFEASIBLE**. Drive-floor rounding loss falls with finer q (42.2 → 14.8 → 7.8 kWh). Do **not** claim fine-grid installation change; coarse q=10 changes feasibility only.

q=1 is **not** an exact continuous optimum. Continuous replay validates a candidate path; it does not prove uniqueness among continuous-feasible paths.

## Southbound H80 counterexample (Task 08)

| q | Ball status | Served | Best sites | Drive floor loss |
| --- | --- | --- | --- | ---: |
| 10 | INFEASIBLE | False |  | None |
| 5 | OPTIMAL | True |  | 14.218240181102246 |

## Reproduction

```bash
python scripts/run_moroccan_energy_grid_convergence.py
pytest -q tests/unit/test_quantization_error_and_charge.py
```

CSV: `results/moroccan_energy_grid_convergence.csv`

Config hashes: vehicle=f703c0c4ede002cd fridge_nb=55abe444b5533a4c
