# Final evidence — reproducibility instructions

**Baseline commit:** `8b0cbf716cc342550299895d4da58889b8239d37`  
**No manuscript work in this campaign.**

## Layout

```
results/final_evidence/
  dataset/          # recounts, accessibility, quality report
  experiments/      # primary comparison, settat, diagnosis, …
  validation/       # consistency gates
  tables/dataset/   # D-T01…D-T07
  tables/results/   # R-T01…R-T13
  figures/dataset/  # D-Figure 1–6
  figures/results/  # R-Figure 1–11
  manifests/        # design freeze, inventory, catalog, fingerprints
```

Historical Path A evidence remains under `results/validation/path_a/`.

## Canonical workflow (order)

```powershell
# P0 — dataset audit + inventory
python scripts/final_evidence/audit_dataset.py
python scripts/final_evidence/build_dt07_and_inventory.py

# P1 — primary 2×2×3×14 comparison (resumable by block)
python scripts/final_evidence/run_primary_comparison.py
python scripts/final_evidence/run_settat_benguerir_compare.py

# Figures from validated CSVs only
python scripts/final_evidence/plot_d_figure1_study_area.py
python scripts/final_evidence/plot_d_figure6_dataset_stats.py
python scripts/final_evidence/plot_r_figure1_coverage.py
```

## Status vocabulary

`OPTIMAL` · `INFEASIBLE` · `LIMIT_REACHED` (unresolved) · audit-failed · `MULTI_DAY_OUT_OF_SCOPE`.

Never equate `LIMIT_REACHED` with infeasibility.

## Fingerprints

Each experiment writes `run_fingerprint.json` with git SHA, q, budgets, fridge path, vehicle keys.

## HOS single-duty

Elapsed-duty screen uses journey ≥ **24 h** (`daily_rest_horizon_min=1440`), consistent with Art.16’s 24 h period (not a 12 h journey cutoff). See `results/validation/path_a/hos_single_duty_policy.md`.
