# PASS 2B novelty verdict — correction

## Correction required

Prior PASS 2B reporting treated a **coverage/feasibility-class** change as if it were an infrastructure **installation** change. Those are distinct.

## Southbound H80 (q=10 → q=5)

| Field | Value |
| --- | --- |
| feasibility_class_changed | True (INFEASIBLE → OPTIMAL on Ball probe) |
| coverage_changed | True (0.0 → 2.0) |
| minimum_site_count_changed | False (0 → 0) |
| optimal_site_set_changed | False (NONE → NONE) |

Served demand weight can change while **min installed sites stay 0** and **selected set stays NONE**. That is a routing/coverage label change, not a charger-location change.

## Methodological status

- Protocol = **conditional coarse-to-fine retry** when Ball is infeasible at q=10.
- **NO-GO** for claiming a new infrastructure-design optimizer or selective refinement algorithm with proved computational advantage.
- **GO** to retain the coarse-grid false-negative as a **numerical-reliability** finding in validation sections.

`novelty_decision: NO_GO_COVERAGE_ONLY_NOT_SITE_DECISION`

## Code fix

`scripts/run_pass2b_discretization_refinement.py` now emits distinct fields:
`feasibility_class_changed`, `coverage_changed`, `minimum_site_count_changed`, `optimal_site_set_changed`, `objective_changed` (see `results/pass2_refinement_change_fields.json`).

## Reproduction

```bash
python scripts/write_northbound_correction_reports.py
# or full PASS2B regenerator:
python scripts/run_pass2b_discretization_refinement.py
```
