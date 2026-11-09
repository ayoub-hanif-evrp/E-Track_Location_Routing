# Task 05C — Comparative results

Date: 2026-11-09  
Portfolio: `configs/optimization/multiroute_placement_pilot.yaml`  
CAPEX scenario: `equal` (illustrative 100 / site)  
Prep time (DRIVE tables + serviceability): **79.8 s** (reported separately from search)

## Serviceability (all candidates installed)

| Mission | OD | E_init | Result |
| --- | --- | --- | --- |
| M_casa_marrakech_low | casa_marrakech | 200 | serviceable |
| M_casa_agadir_low | casa_agadir | 200 | serviceable |
| M_marrakech_agadir_low | marrakech_agadir | 200 | **unserved_all_candidates** (only Amskroud; insufficient) |
| M_casa_marrakech_refrig | casa_marrakech | 300 + TRU | serviceable |

Serviceable weight = 2+2+1 = **5.0** (Marrakech→Agadir excluded from coverage UB).

## B&B vs exhaustive enumeration

| Budget | max_capex | Enum best | B&B best | Coverage | Secondary | Status | Agree |
| --- | --- | --- | --- | --- | --- | --- | --- |
| B0 | 0 | NONE | NONE | 0.0 | 0.0 | CERTIFIED_OPTIMAL | yes |
| B1 | 100 | `y_settat_ca` | `y_settat_ca` | 5.0 | 331.993 | CERTIFIED_OPTIMAL | yes |
| B2 | 200 | `y_settat_ca` | `y_settat_ca` | 5.0 | 331.993 | CERTIFIED_OPTIMAL | yes |
| Ball | ∞ | `y_settat_ca` | `y_settat_ca` | 5.0 | 331.993 | CERTIFIED_OPTIMAL | yes |

Adding Benguerir or Amskroud does **not** improve coverage beyond Settat alone on this portfolio (Settat already enables both Casa→Marrakech and Casa→Agadir low-battery missions). Extra sites only raise CAPEX.

## Joint routing value (honest)

### Baseline A — fixed A3 corridor placement (Task 04B)

Unchanged A3 artifacts retained. That model uses a single prescribed A3 path per direction, not path-union alternatives.

### Baseline B — multi-route with prescribed shortest distance

On the corrected physics pilot:

- `casa_agadir_low_flat_chg` selects the **shortest** path (~445.6 km) with Settat charge.
- `casa_marrakech_low_flat_chg` selects a **non-shortest** path (~257.76 km vs ~236.85 km shortest) with Settat charge.

### Proposed — joint multi-route B&B–MRLS

- Optimal infrastructure under B1+: **Settat Casablanca→Agadir only** (`y_settat_ca` / OSM `127661106`).
- Coverage of all serviceable missions (weight 5.0) is achieved without Benguerir/Amskroud on this small portfolio.
- Route choice remains energy-feasible and continuously replay-certified for served missions.

### Does alternative-road choice change infrastructure?

On **this** portfolio: selected charger location is still Settat (same qualitative site as a shortest-only intuition for Casa-origin missions). However:

1. Casa→Marrakech **does** use a longer energy-feasible road when charging is available — joint routing matters for operating path/energy/charge quantity even when the install set is unchanged.
2. Marrakech→Agadir remains unserved — alternative roads + Amskroud alone do not close the gap at E_init=200 / quantum=10.
3. No evidence here that Benguerir becomes necessary once non-shortest Casa→Marrakech is allowed; we do **not** invent a different optimum.

## Synthetic certification

`tests/unit/test_multiroute_placement.py`:

- Two alternatives; without charger the mission is infeasible; installing `chg_a` enables the short charged route.
- Exhaustive enumeration and B&B agree; B&B status `CERTIFIED_OPTIMAL`.

## Timings (measured)

| Phase | Time |
| --- | --- |
| Placement prep (4 missions, fixed graphs) | 79.8 s |
| Enum+B&B B0 | ~1.4 s search (after memo warm) |
| Enum+B&B B1 | ~0.2 s |
| Enum+B&B B2 / Ball | <0.01 s (cache hits) |

No algorithmic speedup claim beyond these measured comparable timings.

## Unresolved issues (retained)

- HGV access not certified (`unknown` tags).
- Marrakech→Agadir low-battery unserved under current candidates.
- Fixed-graph quantization can render some DRIVE-only full-battery Casa→Agadir missions infeasible without charging (documented in Stage 1 delta).
- Exactness only over the finite site set + verified OD path unions + discrete resource grid.
