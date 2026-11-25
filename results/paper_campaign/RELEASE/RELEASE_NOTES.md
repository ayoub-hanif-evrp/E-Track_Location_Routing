# Stage C/D release `stage-c-hos-219c15cfb631`

- Git SHA: `219c15cfb631d9e12876f862894418a2c1a6c3c4`
- Pipeline: HOS-in-search Stage C artifacts under `results/paper_campaign/`
- Claims crosswalk: `paper/claims_to_results_crosswalk.csv`
- Manuscript: `paper/manuscript.tex` (Path A TRIP feasibility; claims ⊆ crosswalk)
- Path A freeze: `results/validation/path_a/RELEASE_NOTES.md`

## Reproduce

```bash
pip install -e ".[dev]"
pytest -q -m "not integration"
python scripts/path_a/build_coverage_reconciliation.py
python scripts/path_a/verify_energy_ops_dual.py
python scripts/path_a/build_physics_plausibility.py
python scripts/run_stage_c_hos_national.py --phase headline_enum
python scripts/run_stage_c_hos_national.py --phase post_portfolio
python scripts/run_validation_consistency_report.py
```

## Contribution (scoped)

Path A: operational feasibility and charging-infrastructure requirements for refrigerated eHDT on Moroccan motorway corridors. MRLS/HOS-in-search is the research instrument — not a new generic LRP algorithm.
