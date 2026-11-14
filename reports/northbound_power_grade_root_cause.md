# Northbound power / grade / speed root cause

## Verdict

PASS 2’s all-zero Agadir→Casablanca coverage was **not** primarily an optimizer failure. Under fixed road-class cruise speeds, DEM-derived grades create `peak_motor_power_exceeded` rejects. Power-feasible speed reduction clears those motor rejects, but the mission remains **energy-infeasible before the two hypothetical chargers** (settat_ac, benguerir_ac) can be reached.

**Do not** interpret the current simulator as proving a Volvo FH Electric cannot operate in Morocco. COPDEM GLO-30 is a DSM; grades are not surveyed pavement.

## Priority 1 — Exact motor-power failures (fixed cruise)

- OD: `agadir_casa`; payload 5300.0 kg; GCM/mass 25300.0 kg.
- Micros inspected: 9085; fixed peak fails: 53.
- Failing macros only: `223f62c7e05b2e88, 22679b463c79d522`.
- Short extreme DEM spike candidates (L≤80 m & |grade|≥8%): 23.
- After peak-feasible speed search: adapt_peak_ok=9085/9085; still infeasible at 1 km/h floor: 0.
- Segments whose peak-feasible speed is below motorway normal min 60 km/h: 969 (operational flag; not asserted legal).

Worst fixed-cruise segments (Volvo) request ~650–690 kW wheel power at 80 km/h on ~9–11% DEM grades over tens of metres — consistent with mg·sinθ·v gravity power at 25.3 t, and far above the 400 kW research peak rating.

### DEM provenance

- Source: Copernicus GLO-30 via project COP-DEM sampling (`data/processed/multiroute/elevation/`, `dem_sampling_meta.json`).
- Product class: **digital surface model** (buildings/vegetation/infrastructure possible), **not** a surveyed road-centerline pavement grade.
- Macro metadata reports max sampled |grade| above 10% on some northbound macros; short spikes are audited in the CSV (`is_short_dem_spike_candidate`).
- **No arbitrary DEM smoothing** was applied.

## Priority 2 — Decree 2-10-420 (speed)

Official consolidated reference used for research interpretation: Moroccan Decree **2-10-420**, Articles 17–18 (distinct from 2-10-421 weights/dimensions):

- Goods vehicles >19 t: motorway **maximum 80 km/h**.
- Outside urban areas (non-motorway provisions): generally **70 km/h**.
- Article 18: normal motorway **minimum 60 km/h**; unusually slow motorway operation requires careful legal/safety treatment — modeled as an explicit class `below_motorway_normal_min_60`, not as automatic legality.

Scenario comparison encoded in diagnostics:

| Tag | Policy |
| --- | --- |
| A | Fixed road-class cruise (status quo) |
| B | Legal-cap only (defaults already ≈ legal caps) |
| C | Peak-power-feasible speed ≤ commanded cruise |
| D | Continuous-power-feasible speed (eActros peak≠cont) |

## Priority 3 — Physical correction adopted

Opt-in flags on `speed_policy` (fingerprint-invalidating for DRIVE caches):

- `adapt_speed_to_peak_power`
- `adapt_speed_to_continuous_power`
- `min_adapt_speed_mps`

Implemented in `apply_drive` / `simulate_drive_from_soc` / DRIVE build / continuous replay. **OEM power ratings are not retuned.** Peak is never treated as unlimited duration when continuous adaptation is enabled. Instantaneous speed changes between micros omit accel/decel energy — documented limitation, not a fully validated cycle.

## Reproduction

```bash
python scripts/run_northbound_power_speed_diagnostics.py
python scripts/run_northbound_revalidated_feasibility.py
```

Artifacts: `results/northbound_power_speed_diagnostics.csv`, `results/northbound_power_speed_diagnostics_summary.json`.

## Example failing micros (Volvo fixed cruise)

```
macro=22679b463c79d522 L=29.5m dz=3.34 grade=0.1132 v=80 P=692kW v*= 47.7km/h spike=True
macro=22679b463c79d522 L=80.0m dz=9.06 grade=0.1132 v=80 P=692kW v*= 47.8km/h spike=False
macro=22679b463c79d522 L=40.5m dz=4.51 grade=0.1114 v=80 P=682kW v*= 48.4km/h spike=True
macro=22679b463c79d522 L=13.9m dz=1.47 grade=0.1062 v=80 P=653kW v*= 50.6km/h spike=True
macro=22679b463c79d522 L=20.2m dz=2.14 grade=0.1062 v=80 P=653kW v*= 50.6km/h spike=True
macro=22679b463c79d522 L=24.9m dz=2.65 grade=0.1062 v=80 P=653kW v*= 50.6km/h spike=True
macro=22679b463c79d522 L=40.9m dz=4.35 grade=0.1062 v=80 P=653kW v*= 50.6km/h spike=True
macro=22679b463c79d522 L=33.6m dz=3.56 grade=0.1062 v=80 P=652kW v*= 50.6km/h spike=True
```
