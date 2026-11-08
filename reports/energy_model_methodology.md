# Physics-based energy model methodology (Task 02)

**Scope:** Problem A corridor energy for a Mercedes-Benz eActros 600 refrigerated tractor–trailer on Casablanca–Agadir A3 baselines. **Out of scope:** ALNS/GA/Gurobi/OR-Tools, station placement, EVRP, redesign of Task 01C access matching.

**Units:** SI throughout (N, W, J, m, s, kg, K). Energies reported in kWh for readability (\(1\,\mathrm{kWh}=3.6\times10^{6}\,\mathrm{J}\)).

---

## 1. Vehicle and mission defaults

| Quantity | Value | Provenance |
|---|---|---|
| Installed battery | 621 kWh | manufacturer (product sheet model 983403) |
| Usable battery \(E_\mathrm{use}\) | 600 kWh | manufacturer |
| Continuous / peak drive | 400 / 600 kW | manufacturer |
| Unladen tractor | ≈ 11.7 t | manufacturer |
| Technically permissible GCM | 44 t | manufacturer |
| Pilot GCM light / heavy | 25 t / 40 t | research scenarios (40 t ~ maker range-test condition) |
| Cruise speed | 80 km/h = 22.222 m/s | research policy (OSM `maxspeed` **not** used) |
| Acceleration under cruise | \(a=0\) | research policy |

Mass for dynamics: scenario GCM \(m\) (kg). Trailer curb is an **assumed** split inside GCM when needed for documentation; longitudinal forces use total \(m\).

---

## 2. Longitudinal forces (N)

On a segment of length \(L\) (m), grade angle \(\theta\) (rad), speed \(v\) (m/s), air density \(\rho\) (kg/m³), relative air speed \(v_\mathrm{air}\) from wind projection along the travel heading:

\[
F_\mathrm{roll}=C_{rr}\,m\,g\cos\theta,\quad
F_\mathrm{aero}=\tfrac12\rho\,C_dA\,v_\mathrm{air}^2\,\mathrm{sign}(v_\mathrm{air}),\quad
F_\mathrm{grade}=m\,g\sin\theta,\quad
F_\mathrm{acc}=m\,a
\]

With cruise \(a=0\):

\[
F_\mathrm{trac}=F_\mathrm{roll}+F_\mathrm{aero}+F_\mathrm{grade}.
\]

**Coefficient provenance:** \(C_{rr}\), \(C_dA\) are **literature/assumed** (YAML sensitivity ranges). They are **not** Mercedes-Benz coast-down measurements.

---

## 3. Traction power and energy

Wheel power \(P_w=F_\mathrm{trac}\,v\) (W). Manufacturer continuous/peak ratings (400/600 kW) are **motor output** limits.

- If \(P_w>0\): required battery power \(P_\mathrm{batt}=P_w/\eta_\mathrm{prop}\) (**not** silently capped). Fixed-speed feasibility requires \(P_w\le P_\mathrm{peak,motor}\); continuous exceedances are flagged separately.
- If \(P_w<0\): \(P_\mathrm{batt}=\eta_\mathrm{regen}\,P_w\), capped by peak regen power and SOC headroom; rejected regen is tracked.

Efficiencies \(\eta_\mathrm{prop}\), \(\eta_\mathrm{regen}\) are **assumed**. Segment duration \(\mathrm{d}t=L/v\). Segment energy \(E=\int P\,\mathrm{d}t\) (J → kWh). Distances use WGS84 **geodesic** metres (Task 01 convention).

**Auxiliaries:** constant \(P_\mathrm{aux}\) (W), research parameter (YAML range 1–4 kW).

---

## 4. Refrigeration (engineering approximation)

Heat gain (W):

\[
\dot Q \approx UA\,(T_\mathrm{amb}-T_\mathrm{set})_+
\]

with optional door/infiltration term \(=0\) in the pilot. Electrical TRU power \(\dot Q/\mathrm{COP}(T_\mathrm{amb},T_\mathrm{set})\) with tabulated COP bounds (linear in \(\Delta T\), clipped). Integrate over trip duration.

**Config A:** TRU energy is deducted from the tractor usable battery.  
**Config B:** independent trailer pack (assumed usable capacity, e.g. 20–40 kWh); **tractor SOC is never charged by TRU under B**.

Inspired by cold-chain heat-load structure; **not** a calibrated reproduction of Bank et al. (2025).

---

## 5. SOC update

\[
\mathrm{SOC}_{k+1}=\mathrm{clip}\!\left(\mathrm{SOC}_k-\frac{\Delta E}{E_\mathrm{use}},\;\mathrm{SOC}_\min,\;\mathrm{SOC}_\max\right)
\]

Defaults: \(\mathrm{SOC}_0=1.0\), \(\mathrm{SOC}_\min=0.10\) (**assumed** operating floor, labeled). Feasibility is audited **segment-by-segment** (minimum SOC, first violation). Later regen cannot erase an earlier floor violation. Invalid DEM inputs yield **indeterminate** mission status rather than a boolean. See Task 02B: `reports/task02b_physics_audit.md`.

---

## 6. Terrain and weather

- **DEM:** AWS open COP-DEM GLO-30 Public (`s3://copernicus-dem-30m`, no account). Sample along baseline geometry every ~150 m; smooth grades (moving average). Fallback: GLO-90, then labeled **flat-road** baseline. DEM is a DSM (terrain/surface), not pavement. Attribution: Copernicus DEM DOI [10.5270/ESA-c5d3d65](https://doi.org/10.5270/ESA-c5d3d65).
- **Weather:** Open-Meteo Historical Weather API at Casablanca-end, Marrakech-mid, Agadir-end. Two fixed 2025 days (hot / cool) after retrieval. Cache under `data/raw/weather/` (gitignored); CI fixtures under `tests/fixtures/weather/`.

Wind projection: use mean hourly wind speed/direction at the nearest corridor point for the scenario day; project onto segment heading to form \(v_\mathrm{air}=v-v_\mathrm{wind,\parallel}\).

---

## 7. Evaluation API

```text
evaluate_route(edges, vehicle, weather, fridge_cfg, speed_policy) -> EnergyResult
```

Independent of charger/station logic. Pilot matrix: both directions × payload × weather × refrigeration × terrain × power source A/B. Output: `results/energy_pilot.csv`.

---

## 8. Validation tiers (honest naming)

1. **Mathematical verification** (pytest, offline).
2. **Engineering plausibility** vs MB ~500 km / 40 t / ~20 °C marketing order under analogous mild settings — **not** experimental validation.
3. **Empirical validation:** skipped (no measured e-truck dataset available).

---

## 9. Station-access open issue (preserved from Task 01C)

Task 01C candidate sites remain **provisional**: 5 topological access matches; **0** legally confirmed HGV; entrance/exit paths are independent; no continuous in-facility path proof. Not optimization-ready. Task 02 does **not** redesign access classifiers.
