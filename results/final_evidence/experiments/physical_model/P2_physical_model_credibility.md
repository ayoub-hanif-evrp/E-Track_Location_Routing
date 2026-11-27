# P2 — Physical-model provenance and credibility

See `parameter_provenance_matrix.csv` and `R-T15_parameter_provenance.csv`.

- Assumed aero, Crr, efficiencies, trailer curb, aux and regen limits are **engineering assumptions**, not experimentally validated for these packs.
- Primary Volvo pack remains **475 kWh usable** (MA page); `*_usable460.yaml` is sensitivity-only.
- External eActros 600 tour (~1.03 kWh/km at 40 t) is **order-of-magnitude plausibility**, not calibration.
- Refrigeration: firm-ripe tomato 9 °C (UNECE mid-band; UC Davis 7–10 °C consistent). Bank et al. (2025) is methodological inspiration only. Electrical demand without cargo-temperature evolution ⇒ no temperature-compliance claim.
