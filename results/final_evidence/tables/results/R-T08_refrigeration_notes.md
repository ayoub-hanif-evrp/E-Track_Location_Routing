# R-T08 — Refrigeration contribution (interim)

## Headline tomato 9 °C (from primary eActros stressed I1 traces)

| OD | Traction kWh | Aux kWh | Refrig kWh | Regen credit kWh | Refrig / (traction+aux+refrig) |
|----|-------------:|--------:|-----------:|-----------------:|-------------------------------:|
| casa_marrakech | 313.6 | 9.2 | **0.31** | 5.6 | ~0.09% |
| casa_agadir | 590.5 | 16.9 | **0.82** | 41.1 | ~0.13% |

Under the justified firm-ripe tomato 9 °C setpoint with cool ambient and precooled-cargo assumption, refrigeration is a **small** energy term relative to traction. Path A historical on/off diffs at 15 t / 80% also showed tiny min-SOC deltas (~0.001).

Do not inflate refrigeration demand. Full controlled on/off + adverse UA packs under headline 5.3 t conditions remain on the P2 queue; historical Path A coldchain retained under `experiments/refrigeration/path_a_historical_*`.
