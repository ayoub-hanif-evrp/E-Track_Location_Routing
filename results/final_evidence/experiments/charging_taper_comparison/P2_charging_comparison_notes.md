# P2 — Controlled nonlinear charging comparison

## Charging model

- **Taper:** research envelope `conservative_ccs_taper_factor`
  (full ≤60% SOC; linear derate 60→80→95%).
- **Constant:** station∩vehicle nameplate power × η, no SOC derate.
- **Not** an empirically measured OEM curve.

## Propagation

`RoutingInstance.apply_charge_taper` is set on the prepared template and ops
instance; `apply_charge` records `charging_model` on each CHARGE action;
continuous replay uses the same flag when step counts are absent.

## Comparisons

1. **Identical SOC interval (continuous):** `identical_soc_interval_continuous.csv`
   / `R-T23b_*` — wall-clock minutes for the same soc_start→soc_end window.
2. **Reoptimized mission (discrete 5 min):** `constant_vs_taper_missions.csv`
   / `R-T23_*` — solver may choose the same discrete step count when continuous
   differences are smaller than the time quantum.

Matched otherwise: speed patch, HOS, terrain, payload 5300 kg, Benguerir CA, q=2.
