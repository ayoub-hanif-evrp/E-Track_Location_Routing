# P2.3 — Engineering boundary checks

Analytical segment checks for both vehicle packs (payload 5.3 t, cruise 80 km/h unless noted).

| Case family | Intent |
|---|---|
| Flat steady | Positive battery draw; order-of-magnitude kWh/km |
| Uphill 4% | Higher demand than flat |
| Downhill 4% | Net demand ≤ flat via regen |
| Steep 15% / 100 m | Peak motor feasibility flag (not silently capped) |
| Empty vs loaded | Loaded demand ≥ empty |
| CCS taper | High-SOC acceptance < mid-SOC |
| Stationary refrigeration | Electrical load rises with ambient ΔT |
| SOC init/reserve | Integer-kWh init above reserve floor |

**Result:** 26 checks, **0 failed**.

Source: `engineering_boundary_checks.csv` / `R-T19_engineering_boundary_checks.csv`.
