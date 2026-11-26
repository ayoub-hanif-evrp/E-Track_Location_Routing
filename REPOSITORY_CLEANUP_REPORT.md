# Repository Cleanup Report

**Checkpoint before corrections:** Git tag `path-a-pre-correction-c8d9769` (`c8d9769`)  
**Date:** 2026-11-25  

## Scientific integrity first

Cleanup is secondary to Path A numerical corrections. Authoritative evidence under `results/validation/path_a/` and mission-level campaign CSVs were **preserved**. Contradictory / LIMIT outcomes retained.

## Deleted or emptied

| Path | Reason |
|------|--------|
| `results/validation/p_physics/` | Empty directory; superseded by `path_a/physics_plausibility.*` |

## Archived (recoverable)

| From | To | Reason |
|------|-----|--------|
| `scripts/run_task06b_placement_grid.py` | `archive/historical_scripts/` | Early Task 06 placement grid; superseded by Stage C / Path A |
| `scripts/run_task06c_vehicle_comparison.py` | same | Early vehicle comparison |
| `scripts/run_task06d_vehicle_comparison.py` | same | Duplicate vehicle comparison stage |
| `scripts/run_bb_relaxed_bound_benchmark.py` | same | B&B bound experiment; not Path A core |
| `scripts/run_moroccan_energy_grid_convergence.py` | same | Pre-campaign energy grid |
| `scripts/run_multiroute_numerical_sensitivity.py` | same | Early numerical sensitivity; Path A uses rebaked P6 |
| `scripts/rebuild_baseline_report.py` | same | Legacy baseline report builder |
| `reports/PAPER_SCIENTIFIC_RESULTS_CAMPAIGN.md` | `archive/historical_reports/` | Pre–Path A narrative; regenerable under `results/paper_campaign/` |
| `review.txt` | `archive/historical_reports/` | Local review scratch |

Recovery: `archive/` + Git history.

## Duplicate implementations consolidated

- Coverage narrative: single source `results/validation/path_a/coverage_reconciliation.csv` with separate **historical_enum_selection** vs **observed_infra_ladder** tables.
- Campaign markdown writer now targets `results/paper_campaign/PAPER_SCIENTIFIC_RESULTS_CAMPAIGN.md`.

## `.gitignore` updates

- `data/processed/multiroute/nodes.csv`, `edges.csv`
- `review.txt`, `scripts/_*.py`, `__pycache__`

## Structure (after)

```
configs/          vehicles, energy (tomato fridge), optimization
src/              core physics + MRLS
scripts/          Stage C/D + path_a/ + retained priority runners
scripts/path_a/   Path A correction & evidence builders
results/paper_campaign/   historical enum / ablation evidence
results/validation/path_a/  authoritative Path A tables
results/validation/p1–p7/   prior validation blocks (kept)
archive/          historical scripts/reports
paper/            manuscript + crosswalk + bib
tests/            unit + regression
```

## Size / file count

| Metric | Approx. |
|--------|---------|
| Tracked-ish file count (excl. `.git`/caches) | ~801 |
| Working tree size (excl. `.git`) | ~1041 MB (dominated by local graph CSVs + data caches) |

Baseline checkpoint file count at start of session: ~886 (includes caches).

## Tests

| Suite | Result |
|-------|--------|
| `tests/unit/test_hos_in_search.py` | 11 passed |
| Full `pytest -m "not integration"` | baseline run started; prefer unit + graph CI asset check |

Graph CI: `multiroute-graph-v1` HTTP 200 (`results/validation/path_a/ci_graph_check.json`).

## Retained for further investigation

- Early runners still in `scripts/` (`run_high_impact_*`, `run_energy_pilot`, `run_morocco_routing`, …) — may still support data rebuild; not deleted blindly.
- `results/validation/baseline_453d391/` — historical baseline archive; keep.
- Settat `casa_agadir` LIMIT escalate still pending conclusive status.

## Confirmation

- Scientific Path A evidence and historical campaign CSVs remain accessible.
- Manuscript cites observed I2=12/14 and historical E=11/14 separately.
- Executable corrections regenerated: infra ladder, cold-chain, P6 rebake (16 cells), consistency warnings.
- No READY claim from documentation alone — evidence freeze remains CONDITIONAL pending Settat LIMIT escalate outcome.


## Final evidence campaign addendum

Authoritative numerical/figure package lives under `results/final_evidence/`.
Path A historical evidence remains under `results/validation/path_a/`.
Do not duplicate evidence into `paper/` during this campaign (manuscript work deferred).
Campaign status: COMPLETE.
