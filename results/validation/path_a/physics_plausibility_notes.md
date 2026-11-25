# Physics plausibility (Path A Gate 1)

Reference-check only — **not** field validation of the eActros pack or TRU.

- Flat-cruise traction estimate: **1.342 kWh/km** (literature long-haul band ~1.11–1.14 kWh/km; different duty cycles).
- Aux: **2500 W** (assumed).
- Refrigeration setpoint **2.0 °C**, UA **80.0 W/K**;
  TRU electrical power from UA–COP model on DRIVE/CHARGE/WAIT when refrigeration is on.
- Sensitivity variants that change CdA / aux / weather must **re-bake DRIVE tables**
  (see `scripts/run_remaining_p6_extras.py`).

Table: `results/validation/path_a/physics_plausibility.csv`
