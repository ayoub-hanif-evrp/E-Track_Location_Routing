# Task 06D — GCM state-leak root cause and invalidated 06C conclusions

Access date: 2026-11-10  
Reviewed HEAD (bug present): `6a10a3a`

## Root cause

In `scripts/run_task06c_vehicle_comparison.py` the loop used:

```python
("light", float(cfg.gcm_kg))
...
cfg.gcm_kg = gcm_kg   # heavy sets 40000 and never restores
```

Light GCM was read from the **mutable** shared pilot config. After the first vehicle’s heavy iteration, every subsequent “light” cell inherited **40 000 kg** while retaining `gcm_label="light"`.

`build_physics_od_instance` originally had no `gcm_kg=` override and always consumed `cfg.gcm_kg`.

## Impact on committed Task 06C CSV

Artifact retained as:

- `results/task06c_vehicle_comparison_INVALIDATED_gcm_leak.csv`
- `results/task06c_vehicle_placement_UNRECONCILED_pre06d.csv`

| Category | Rows |
| --- | ---: |
| Clean light (`label=light`, `gcm_kg=25000`) | 18 (eActros · q10 · enroute only) |
| Contaminated light (`label=light`, `gcm_kg=40000`) | 126 |
| True heavy | 12 |

**Headline withdrawal:** Casa→Agadir full / no-charge “light” compared eActros at **25 t** (OPTIMAL) vs Volvo at **40 t** (INFEASIBLE). That unequal-mass comparison is **not** a valid vehicle conclusion.

**Do not use Task 06C routing figures in papers or presentations.**

Placement prep restored `cfg.gcm_kg` in a `finally` block, so the placement table was less clearly contaminated, but it still used absolute kWh inits and a mostly non-refrigerated portfolio. It is treated as **unreconciled** until Task 06D re-runs.

## Fix (Task 06D)

1. Freeze `gcm_light` / `gcm_heavy` from YAML physics once.
2. Pass immutable `gcm_kg=` into `build_physics_od_instance` (no shared-config mutation).
3. Assert `cfg.gcm_kg` unchanged after each build; assert realized GCM equals requested.
4. Regression tests in `tests/unit/test_task06d_gcm_integrity.py`.
5. Regenerate fair results under `results/task06d_*.csv` and reports in this folder.

## Conclusions that may change

Any claim that Volvo cannot complete Casa→Agadir without charging while eActros can — **when both were labeled light** — must be re-established under equal mass / equal payload. Placement “Volvo needs Benguerir” remains a **hypothesis** until `task06d_corrected_placement.md`.
