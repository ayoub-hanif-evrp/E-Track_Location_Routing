# Battery quantization and grid convergence

## Quantization policy

Conservative flooring after DRIVE (table build) and CHARGE/WAIT (stationary snap) is **retained**. Removing it would risk optimistic discrete feasibility.

- Novel algorithm claim: `False`
- Adopted representation change: `None`
- Rationale: Removing flooring would risk optimistic discrete feasibility. Publication-facing infrastructure claims require fine-grid stability (see battery_quantization_and_convergence report).

Unit proof that CHARGE can yield zero discrete gain: `tests/unit/test_quantization_error_and_charge.py`.

## Northbound canonical max_alts=4 (eActros, peak-adapt)

| q | Ball status | Served | Best sites (Ball) | Opt sets | B&B↔enum | Cont replay | sec |
| --- | --- | --- | --- | --- | --- | --- | ---: |
| 10 | INFEASIBLE | False |  | ['NONE'] | True | False | 30.9 |
| 5 | OPTIMAL | True | y_benguerir_ac | ['y_benguerir_ac'] | True | True | 50.9 |
| 2 | OPTIMAL | True | y_benguerir_ac | ['y_benguerir_ac'] | True | True | 122.4 |
| 1 | OPTIMAL | True | y_benguerir_ac | ['y_benguerir_ac'] | True | True | 399.9 |

**Verdict:** among **served** northbound rows (q = 5, 2, 1) the Ball optimum is stable at **`{y_benguerir_ac}`** (single equivalent opt set). At **q = 10** the same physical graph is Ball-**INFEASIBLE** — coarse quantization changes *feasibility*, not the fine-grid site decision. Do **not** claim that q-refinement changes the optimal charger installation within the tested fine range q ∈ {5, 2, 1}.

Charge energy under Ball falls with finer q (175 → 110 → 94 kWh) while continuous replay remains OK — consistent with reduced floor-induced conservatism, not a continuous optimality proof.

Historical DRIVE-floor rounding on a related northbound path (integrity JSON): ~58.5 kWh (rebuild max_alts=2, q=10) vs ~85.6 kWh (same nodes on canonical-4, q=10). Conservative flooring is retained; publication claims require the fine-grid stability above.

q=1 is **not** an exact continuous optimum. Continuous replay validates a candidate path; it does not prove uniqueness among continuous-feasible paths.

## Southbound H80 counterexample (Task 08)

| q | Ball status | Served | Best sites |
| --- | --- | --- | --- |
| 10 | INFEASIBLE | False |  |
| 5 | OPTIMAL | True | (empty / NONE — served with zero installed sites) |

q-sensitivity of feasibility is **not unique** to the northbound mission: H80 is infeasible at q=10 and feasible at q=5 on the same Task-08 graph.

## Reproduction

```bash
python scripts/run_moroccan_energy_grid_convergence.py
pytest -q tests/unit/test_quantization_error_and_charge.py
```

CSV: `results/moroccan_energy_grid_convergence.csv`

Config hashes: vehicle=f703c0c4ede002cd fridge_nb=55abe444b5533a4c
