# Stage C/D release `stage-c-hos-6ac846a43425`

- Git SHA: `6ac846a434255c0c327488f09f983ae760a81535`
- Pipeline: HOS-in-search Stage C artifacts under `results/paper_campaign/`
- Claims crosswalk: `paper/claims_to_results_crosswalk.csv`
- Manuscript: `paper/manuscript.tex` (claims ⊆ Stage C tables)

## Reproduce

```bash
pip install -e ".[dev]"
pytest -q -m "not integration"
python scripts/run_stage_c_hos_national.py --phase all_fast
```

## Contribution (scoped)

Moroccan refrigerated eHDT + DEM + directional ADM + operational joint siting under HOS-in-search — not a new generic LRP.
