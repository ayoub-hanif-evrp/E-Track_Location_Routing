# Path A release freeze

## Positioning

Operational feasibility and charging-infrastructure requirements for refrigerated eHDT on Moroccan motorway corridors (TRIP-oriented). MRLS / enum_cap≤2 is the research instrument — not an algorithm contribution.

## Authoritative coverage (manuscript)

| Budget | C fixed | E multi |
|--------|---------|---------|
| B0 | 9/14 | 9/14 |
| B1 | 10/14 (Larache) | 11/14 (Benguerir CA) |
| B2 | 11/14 (Benguerir+Larache) | 11/14 (Benguerir CA) |

Do **not** headline 12/14 (ablation multi_on_C only).

## Claims ⊆ evidence

See `paper/claims_to_results_crosswalk.csv` (PA01–PA10). Every manuscript number must map to a CSV cell.

## Reproduce (fast Path A)

```bash
pip install -e ".[dev]"
pytest -q tests/unit/test_hos_in_search.py
python scripts/path_a/build_coverage_reconciliation.py
python scripts/path_a/verify_energy_ops_dual.py
python scripts/path_a/build_physics_plausibility.py
python scripts/run_validation_consistency_report.py
```

## Graph / CI

CI downloads `multiroute-graph-v1` via `GRAPH_ARTIFACT_URL` (or release asset fallback). Graph CSVs are not in git.

## Non-claims

- No new LRP algorithm / SOTA vs Plaza or Cheng TR-C
- No Art.16 overnight multi-day optimality
- No field-validated physics; reference-check only
