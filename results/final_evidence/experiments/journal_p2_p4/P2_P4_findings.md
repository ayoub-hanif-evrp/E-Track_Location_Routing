# P2–P4 controlled findings

## P2 — Physical credibility

- Provenance matrix: `experiments/physical_model/parameter_provenance_matrix.csv` / `R-T15_parameter_provenance.csv`.
- External eActros 600 tour ~**1.03 kWh/km @40 t** recorded as order-of-magnitude plausibility only (`R-T16_external_benchmarks.csv`).
- Assumed parameters remain classified as engineering assumptions (not experimentally validated).

## P3 — Refrigeration (matched eActros cells)

| OD | Variant | E_refrig (kWh) | Share of traction | min SOC | Ops |
|---|---|---:|---:|---:|:---:|
| Casa–Marrakech | off | 0.00 | 0% | 0.115 | Yes |
| Casa–Marrakech | 9°C cool | 0.31 | ~0.10% | 0.114 | Yes |
| Casa–Marrakech | 9°C hot | 3.41 | ~1.1% | 0.119 | Yes |
| Casa–Marrakech | UA×1.5 hot | 5.12 | ~1.6% | 0.116 | Yes |
| Casa–Agadir | off | 0.00 | 0% | 0.120 | Yes |
| Casa–Agadir | 9°C cool | 0.82 | ~0.14% | 0.118 | Yes |
| Casa–Agadir | 9°C hot | 6.27 | ~1.1% | 0.114 | Yes |
| Casa–Agadir | UA×1.5 hot | 9.41 | ~1.6% | 0.109 | Yes |

**Finding (supported within the model):** Under these near-threshold eActros missions, refrigeration does **not** change infrastructure requirements. Even the combined adverse (hot + UA×1.5) case remains operationally served; refrigerator energy stays a small share of traction. Refrigeration-off is a counterfactual energy benchmark only. No cargo-temperature compliance claim.

Volvo Casa–Marrakech @50% SOC remains energy/ops infeasible with or without refrigeration (battery-reserve / corridor energy dominated).

## P4 — Payload / weather

- **5.3 t** is a deliberately light research assumption (`P4_payload_justification.md`), not typical Moroccan freight.
- At stressed 50% SOC, raising payload to **10 t / 15 t** makes Casa–Marrakech and Casa–Agadir **INFEASIBLE** at I1 (Benguerir CA) where 5.3 t succeeded.
- Casa–Tangier @80% SOC / I2 remains feasible at **10 t**.
- Therefore: principal I1 enablement of southern corridors under stressed SOC **does not automatically persist** at heavier payloads; report the reduction rather than forcing coverage.

Infeasible rows leave energy columns as missing (not zero).
