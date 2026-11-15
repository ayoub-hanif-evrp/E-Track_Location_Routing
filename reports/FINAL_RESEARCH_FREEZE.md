# FINAL RESEARCH FREEZE

- Commit: 9761efc1420975fbdf1493faeac615bb39915a2c
- Mode: sprint completion
- Tests: 280 passed, 2 deselected (`pytest -q -m "not integration"`)

## Strongest results

1. Authoritative COMPLETE continuous replay distance **429.15 km** (353.6 km SUPERSEDED).
2. Action-exact rounding audit: **25 DRIVE** actions at q=5/2/1; identical DRIVE arc sequence; audit_ok.
3. Discrete charge **175 / 110 / 94 kWh**; floor loss **94.45 / 30.11 / 14.11 kWh**; drop ≈ flooring-driven (B+C), not route change.
4. Microsegment minimum SOC tracked (not macro-end only).
5. Robustness: baseline Benguerir at SOC0.8/5.3t/peak-adapt; **CONDITION_DEPENDENT** under SOC0.5 (unserved), SOC1.0 (Settat at q=5), 15t (unserved), fixed speed (unserved), Settat-only (unserved).

## Moroccan site decisions

- `GRID_STABLE_WITHIN_TESTED_RANGE` for baseline fine-q panel at Benguerir.
- **Not** `PHYSICAL_SCENARIO_STABLE` across dispatch SOC / payload / speed policy.
- Label chargers hypothetical; replay = `SIMULATION_REPLAY_VALIDATED` ≠ field validation.

## High-impact paper support

Supports a **decision-reliability under numerical and physical uncertainty** corridor paper.
Does **not** support novel exact joint siting+routing novelty, nor investment optimality from illustrative costs, nor nationwide representativeness.

## Remaining gaps

Field OD/payload/TRU duty; ADM HGV access and power; axle-verified mass; surveyed pavement grades; annual trip economics.

## Reproduction

```bash
pytest -q -m "not integration"
python scripts/run_final_numerical_integrity.py
python scripts/run_final_moroccan_robustness.py
python scripts/generate_publication_figures.py
python scripts/run_publication_freeze.py --quick
```

## Paths

- `paper/manuscript.tex`, `paper/references.bib`, `paper/figures/`
- `reports/final_numerical_integrity.md`
- `reports/charging_energy_convergence_explanation.md`
- `reports/final_moroccan_robustness_results.md`
- `reports/final_methodology_and_baseline_evaluation.md`
- `reports/final_moroccan_evidence_matrix.md`
- `reports/moroccan_operator_and_infrastructure_outreach.md`
