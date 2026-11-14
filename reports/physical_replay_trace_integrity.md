# Physical replay trace integrity

## Problem

A publication-oriented `_speed_power_profile` diagnostic previously reported ~353.6 km while full continuous replay reported ~429 km for the same eActros solution. That diagnostic processed DRIVE micros without applying CHARGE state updates and could terminate early while still emitting trip-like statistics.

## Correction

Authoritative journey metrics now come exclusively from `continuous_replay_multiroute(..., emit_trace=True)` + `summarize_complete_trace`. Incomplete traces are labelled `INCOMPLETE` and excluded from complete-trip stats.

Tolerances: distance ≤ 1.0 m; SOC ≤ 1e-06.

## Results

| Case | Status | Auth. km | Charge kWh | Min SOC | Arrival SOC | Trace |
| --- | --- | ---: | ---: | ---: | ---: | --- |
| rebuild_max_alts2_q10 | OPTIMAL | 429.15 | 240.0 | 0.2353 | 0.3651 | COMPLETE |
| canonical_max_alts4_q5 | OPTIMAL | 429.15 | 175.0 | 0.2352 | 0.2574 | COMPLETE |

Reconciliation (rebuild max_alts=2, q=10): historical defective DRIVE-only profile **353.65 km** vs historical continuous journey **429.15 km** vs regenerated authoritative COMPLETE trace **429.15 km** (`auth_vs_hist_journey_agree=True` within 1 m). The ~353.6 km figure is **SUPERSEDED**.

## Reproduction

```bash
python scripts/run_physical_trace_reconciliation.py
pytest -q tests/unit/test_physical_replay_trace.py
```

CSV: `results/physical_trace_reconciliation.csv`
