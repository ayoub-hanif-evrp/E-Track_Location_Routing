# Task 06D — Fair vehicle comparison (corrected GCM / payload / SOC)

Artifacts: `results/task06d_vehicle_comparison.csv` (396 rows)  
Monetary: solver cents; `road_cost_per_km=100` ¢/km.  
GCM integrity: **0** contaminated light/heavy rows; `cfg.gcm_kg` never mutated.

## Designs

| Design | Meaning |
| --- | --- |
| `fixed_gcm` | Same total mass 25 t / 40 t (payload differs by curb) |
| `fixed_payload` | Same cargo 5 300 / 20 000 kg → Volvo GCM = eActros GCM + 300 kg |
| `equal_soc_*` | Same departure SOC (primary dispatch reading) |
| `equal_kwh_200` | Same absolute kWh (diagnostic only) |

Volvo 400 kW continuous=peak=regen and 12 t curb remain **assumed**; do not attribute all differences to battery alone.

## Headline answers (q=10, en-route, continuous replay OK on all OPTIMAL)

### 1–2. Mission feasibility and charging

**Casa→Agadir, equal SOC 100%, fixed GCM 25 t, no en-route charge**

| Vehicle | GCM | Status |
| --- | ---: | --- |
| eActros 600 (`E_cap=600`) | 25 000 | **OPTIMAL** |
| Volvo 475 / 460 (`E_cap=470/460`) | 25 000 | **INFEASIBLE** |

Same pattern under **fixed payload 5 300 kg** (Volvo at 25 300 kg).  
→ The withdrawn 06C unequal-mass headline **reappears under equal mass / equal payload**. Battery usable capacity (and related discrete cap), not the GCM leak alone, drives no-charge Casa→Agadir failure for Volvo at full SOC.

**Casa→Agadir, equal SOC 50%:** all three trucks **INFEASIBLE** without chargers; all three **OPTIMAL** with `all_compatible` (Volvo objectives higher).

**Casa→Marrakech refrigerated (Config A assumed), equal SOC 100%, chargers available:** all three **OPTIMAL** at identical road-dominated objective in this cell (0 en-route charge kWh recorded).

**Marrakech→Agadir** at low/mid SOC remains largely unserved even with all compatible sites (direction/site coverage limit — unresolved for infrastructure interpretation).

### 3. Energy acquired

At SOC 50% Casa→Agadir with chargers, discrete charge energy and objectives differ by vehicle (eActros obj 52362 ¢ vs Volvo 53842 ¢ in the equal-SOC light fixed-GCM cell). Full charge logs are in `charges_json`.

### 4–6. Robustness

- **460 vs 475:** identical serviceability pattern on shared cells in this matrix (quantum flooring).
- **q=5** sensitivity (fixed_gcm light, equal_soc_1.0, enroute): no qualitative flip on Casa→Marrakech; Casa→Agadir no-charge remains vehicle-capacity sensitive.
- **Heavy 40 t / payload_heavy:** Casa→Marrakech still serviceable at full SOC for all three; Casa→Agadir no-charge still fails for Volvo where tested.
- Motor-power menu sensitivity not exhaustively re-run in 06D (bounded); 400 kW pack remains assumed_variant_pick.

## What changed vs invalidated Task 06C

| Claim | 06C (invalid) | 06D (corrected) |
| --- | --- | --- |
| Volvo fails Casa→Agadir no-charge vs eActros success | Contaminated (Volvo at 40 t) | **Holds at equal 25 t and equal payload** |
| Light-labeled rows | 126/144 wrong mass | 0 wrong mass |

## Uncertainties

Assumed curb/CdA/η/power split; Config A TRU; hypothetical 350 kW ADM chargers; illustrative tariffs; no measured trip validation.
