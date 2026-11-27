# P5.3 — Effective initial SOC

Initialization rule (solver): `E_truck_init = int(round(nominal_soc_frac * usable_kwh))`.

For Volvo **475 kWh** at nominal 50%: `round(0.5*475)=238` kWh → effective SOC **238/475 ≈ 50.105%**.
This is a small upward rounding; threshold experiments should report both nominal and effective values.
The 460 kWh sensitivity pack is separate and must not be confused with the primary 475 kWh configuration.

See `effective_initial_soc.csv` / `R-T20_effective_initial_soc.csv`.
