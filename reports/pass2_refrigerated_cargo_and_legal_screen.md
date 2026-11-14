# PASS 2A — Refrigerated cargo and legal screen

## Commodity

| Field | Value |
| --- | --- |
| Commodity | Firm-ripe fresh tomatoes |
| Setpoint | 9 °C (UNECE firm-ripe band ≈ 8–10 °C mid-point) |
| Source | UNECE ECE_TRADE_470 good-practice guidance |
| Status | Category reference — **not** measured Moroccan trailer setpoints |
| Precooled | Assumed true |
| UA / COP / infiltration | Assumed research parameters (unchanged magnitudes) |
| Config A tractor→TRU | **Unverified** compatibility |

## Legal mass screen (Decree 2-10-421 Art. 3)

Assumed 4×2 tractor + three-axle refrigerated semi → articulated **40 t** PTRA screen.
Axle-group limits (Art. 4) **not** computed — geometry unavailable.

| Payload | Empty (assumed) | GCM | ≤40 t Moroccan | ≤ manufacturer GCW | Status |
| --- | ---: | ---: | --- | --- | --- |
| 5300 / volvo_475 | 20000 | 25300 | True | True | `gross_mass_within_limit_axle_unverified` |
| 5300 / eactros_600 | 19700 | 25000 | True | True | `gross_mass_within_limit_axle_unverified` |
| 5300 / volvo_460 | 20000 | 25300 | True | True | `gross_mass_within_limit_axle_unverified` |
| 15000 / volvo_475 | 20000 | 35000 | True | True | `gross_mass_within_limit_axle_unverified` |
| 15000 / eactros_600 | 19700 | 34700 | True | True | `gross_mass_within_limit_axle_unverified` |

**Do not use `legally_certified`.** OSM topology ≠ HGV legal access certificate.

Input hashes: `{"placement_yaml": "d43fd4757cda0f90", "fridge_yaml": "55abe444b5533a4c", "dem_meta": "d3ab184bee4d92d2"}`
