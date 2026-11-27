# Journal-level scientific validation — status

**Baseline:** `518bc11` / tag `evidence-freeze-518bc11`  
**Inventory:** `manifests/JOURNAL_VALIDATION_EXPERIMENT_INVENTORY.md`  
**Campaign status:** **COMPLETE** (all prompt gates closed; freeze commit pending/applied separately)

## Completed gates

| Gate | Status |
|---|---|
| P0 Temporal HOS discretization | COMPLETE |
| P1 Executed geometry / DEM | COMPLETE |
| P2 Provenance + external benchmark + **P2.3 boundary checks** | COMPLETE (`engineering_boundary_checks.csv`, 26/26 pass) |
| P3 Refrigeration controlled cells | COMPLETE |
| P4 Payload/weather + heavier matched set | COMPLETE |
| P5 Reconciliation + **P5.3 effective SOC** + **P5.4 capacity CF** | COMPLETE |
| P6–P7 Figures/tables + catalog | COMPLETE (`figures/figure_catalog_complete.csv`) |
| P8 `.gitattributes` + generate/verify split | COMPLETE (`verify_release_manifest.py`) |
| P9 Literature matrix | COMPLETE |
| P10 Findings classification | COMPLETE |
| Executable validation | Re-run after freeze artifacts |

## Authoritative coverage (unchanged @5 min)

| Vehicle / scenario | I0 | I1 | I2 | I3 |
|---|---:|---:|---:|---:|
| eActros stressed | 9/14 | 11/14 | 12/14 | 13/14 |
| eActros common 80% | 11/14 | 12/14 | 13/14 | 14/14 |
| Volvo stressed | 7/14 | 7/14 | 8/14 | 8/14 |
| Volvo common 80% | 8/14 | 9/14 | 10/14 | 10/14 |

## Closing findings (this completion pass)

- Volvo 50% → effective **≈50.105%** via `int(round(0.5*475))`.
- Battery-capacity-only CF: Volvo non-battery params + **600 kWh** usable makes Casa–Marrakech @50%/I1 **feasible** (baseline Volvo 475 infeasible) — capacity matters, but main comparison remains full-configuration.
- Steep 15% @80 km/h correctly flags peak-power infeasible (no silent capping).

Do not begin manuscript writing.
