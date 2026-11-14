# Final heavy-vehicle feasibility diagnosis (Volvo 15 t)

Base Task 08 finding: Volvo FH Electric 475 kWh @ 15 t cargo serves **0 / 5.5** at SOC 0.5 and 0.8 even with all hypothetical candidate sites (Ball). This note diagnoses *why* under the **assumed** vehicle model.

**Publishable phrasing:** these missions are infeasible under this assumed vehicle configuration and reduced path-union network. **Not** a claim that Volvo cannot transport 15 tonnes in Morocco.

## Vehicle configuration under test

| Field | Value | Provenance |
| --- | ---: | --- |
| Usable battery | 475 kWh | manufacturer (MA page conflict note) |
| Continuous / peak power | 400 / 400 kW | **assumed_variant_pick** (OEM menu 300–540, no cont/peak split) |
| Empty tractor / trailer | 12 t / 8 t | **assumed** |
| GCM at 15 t cargo | 35 t | empty+payload; tech GCW 65 t manufacturer |
| Path union | max_alts=2 DEM | scientific pilot |
| Refrigeration | ON, Task 07B nominal UA | research |

## Diagnosis matrix

| Cell | OD | q | Power scan kW | Continuous | MRLS none | MRLS Ball | Class |
| --- | --- | ---: | ---: | --- | --- | --- | --- |
| H50 | casa_agadir | 5 | 400.0 | peak_motor | INFEASIBLE | INFEASIBLE | **peak_motor** |
| H50 | casa_agadir | 10 | 400.0 | peak_motor | INFEASIBLE | INFEASIBLE | **peak_motor** |
| H50 | casa_marrakech | 5 | 400.0 | soc_floor | INFEASIBLE | INFEASIBLE | **soc_floor** |
| H50 | casa_marrakech | 10 | 400.0 | soc_floor | INFEASIBLE | INFEASIBLE | **soc_floor** |
| H50 | marrakech_agadir | 5 | 400.0 | soc_floor | INFEASIBLE | INFEASIBLE | **soc_floor** |
| H50 | marrakech_agadir | 10 | 400.0 | soc_floor | INFEASIBLE | INFEASIBLE | **soc_floor** |
| H80 | casa_agadir | 5 | 400.0 | peak_motor | INFEASIBLE | INFEASIBLE | **peak_motor** |
| H80 | casa_agadir | 10 | 400.0 | peak_motor | INFEASIBLE | INFEASIBLE | **peak_motor** |
| H80 | casa_marrakech | 5 | 400.0 | continuous_ok | OPTIMAL | OPTIMAL | **served** |
| H80 | casa_marrakech | 10 | 400.0 | continuous_ok | INFEASIBLE | INFEASIBLE | **discrete_grid_reject** |
| H80 | marrakech_agadir | 5 | 400.0 | soc_floor | INFEASIBLE | INFEASIBLE | **soc_floor** |
| H80 | marrakech_agadir | 10 | 400.0 | soc_floor | INFEASIBLE | INFEASIBLE | **soc_floor** |

## Cause summary (default 400 kW YAML, no power override)

```
{
  "soc_floor": 6,
  "peak_motor": 4,
  "discrete_grid_reject": 1,
  "served": 1
}
```

## Interpretation

**Mixed, corridor-specific causes — not a single physical story.**

1. **Casablanca→Agadir:** continuous **peak_motor** at the assumed 400 kW rating (and at 300 kW). Raising the in-memory scan to the OEM menu upper bound **540 kW** removes the peak-motor violation and exposes an **SOC floor** instead. So CA heavy-load failure is **configuration-dependent** on the assumed power pick.
2. **Casablanca→Marrakech @ SOC 0.5:** continuous **SOC floor** (energy), independent of q∈{5,10}; Ball chargers do not restore serviceability on this path-union.
3. **Casablanca→Marrakech @ SOC 0.8:** continuous physics is OK, but primary **q=10 MRLS is INFEASIBLE** even with Ball → **discrete_grid_reject**. At **q=5** the same OD becomes **served** (even with no sites). Task 08’s H80 zero-coverage therefore partly reflects the committed q=10 grid, not only continuous physics.
4. **Marrakech→Agadir:** continuous **SOC floor** at both SOC levels; Ball does not help.
5. **Charging access alone is not the explanation** for H50/H80 zero coverage: whenever continuous already fails on peak/SOC, Ball remains INFEASIBLE; the one grid-reject case (H80 CM @ q=10) is also Ball-INFEASIBLE.

**Verdict for publication:** H50/H80 Volvo zero coverage is **supported as discrete-model infeasibility under the assumed 400 kW / assumed masses / DEM path-union / q=10 stack**, with identifiable contributors (peak motor, SOC floor, and at least one q-grid reject). It is **not** a field proof that Volvo cannot haul 15 t in Morocco, and parts of the result are **configuration- and grid-dependent**.

## Manufacturer-menu power sensitivity (diagnostic only)

In-memory override of continuous=peak=regen at OEM menu bounds 300 / 540 kW already documented in the Volvo YAML. **Committed vehicle defaults are unchanged.**

| Cell | OD | Power kW | Continuous class | Note |
| --- | --- | ---: | --- | --- |
| H50 | casa_agadir | 300.0 | peak_motor | in_memory_menu_bound_only |
| H50 | casa_agadir | 540.0 | soc_floor | in_memory_menu_bound_only |
| H50 | casa_marrakech | 300.0 | peak_motor | in_memory_menu_bound_only |
| H50 | casa_marrakech | 540.0 | soc_floor | in_memory_menu_bound_only |
| H50 | marrakech_agadir | 300.0 | soc_floor | in_memory_menu_bound_only |
| H50 | marrakech_agadir | 540.0 | soc_floor | in_memory_menu_bound_only |
| H80 | casa_agadir | 300.0 | peak_motor | in_memory_menu_bound_only |
| H80 | casa_agadir | 540.0 | soc_floor | in_memory_menu_bound_only |
| H80 | casa_marrakech | 300.0 | peak_motor | in_memory_menu_bound_only |
| H80 | casa_marrakech | 540.0 | continuous_ok | in_memory_menu_bound_only |
| H80 | marrakech_agadir | 300.0 | soc_floor | in_memory_menu_bound_only |
| H80 | marrakech_agadir | 540.0 | soc_floor | in_memory_menu_bound_only |

If 540 kW removes peak-motor failures while 300 kW worsens them, the H50/H80 zero-coverage result is **configuration-dependent** on the assumed power pick — still not a Morocco field conclusion.

## What we may / may not claim

| Claim | Status |
| --- | --- |
| Discrete MRLS + replay: Volvo 15 t H50/H80 unserved under Ball | Supported by Task 08 + this diagnosis |
| Cause class under assumed 400 kW / assumed masses / path-union | Supported by this report |
| Volvo cannot haul 15 t on Moroccan highways | **Unsupported** |
| Assumed 400 kW equals a specific OEM continuous/peak split | **Unsupported** (menu listed, split unpublished) |

Generated rows: `24`. CSV: `results/final_heavy_vehicle_feasibility_diagnosis.csv`.
