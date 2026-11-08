# Task 02 — Energy model validation report

**Date:** 2026-11-08  
**Scope:** Physics-based corridor energy for eActros 600 refrigerated combination on A3 Casablanca–Agadir baselines. No routing/charging optimization.

---

## 1. Mathematical verification (pytest)

Offline unit/integration tests cover:

- SI force signs; flat/zero-wind roll > 0; uphill vs downhill; payload monotonicity
- Headwind vs tailwind; \(C_{rr}>0\); regen peak and full-SOC caps
- Zero-length / zero-speed errors; SOC bounds
- Hot vs cool refrigeration power; **no double-counting** config A vs B (TRU never charged to tractor under B)
- Weather fixtures load; synthetic grade increases traction vs flat

Run: `pytest -q` (see CI/local log at commit time).

---

## 2. Data retrieval status

| Source | Status | Notes |
|---|---|---|
| Open-Meteo Historical | **OK** | Mid-month 2025 probe at Marrakech-mid → **hot = 2025-07-15**, **cool = 2025-01-15**. Cached under `data/raw/weather/` (gitignored); fixtures committed under `tests/fixtures/weather/`. |
| AWS COP-DEM GLO-30 | **OK** | Six corridor tiles downloaded; profiles `data/processed/energy/elevation_profile_*.json`, source `copdem_glo30`. Meta: `dem_sampling_meta.json`. z range ≈ 0–1246 m (DSM; z=0 may include nodata/coastal fill — not pavement). |
| GLO-90 fallback | Not needed | GLO-30 complete |
| Flat-road baseline | Always available | Labeled `terrain=flat` in pilot CSV |

Attribution: Copernicus DEM DOI `10.5270/ESA-c5d3d65`; Open-Meteo; Mercedes-Benz eActros 600 product sheet (battery/mass/power).

---

## 3. Pilot results (summary)

Matrix: 2 directions × 2 payloads × 2 weather days × 2 refrigeration × 2 terrain × 2 power sources = **64 rows** → `results/energy_pilot.csv`.

Cruise: **80 km/h** constant. Distance ≈ **417 km**.

Illustrative means (both directions averaged where noted):

| Scenario | Net tractor (order) | Feasible @ SOC≥10%? |
|---|---|---|
| Light 25 t, flat, cool, refrig off | ~487 kWh (~1.17 kWh/km) | Yes (SOC≈0.19) |
| Heavy 40 t, flat, cool, refrig off | ~620 kWh (~1.49 kWh/km) | **No** (SOC floor violated) |
| DEM vs flat (heavy) | DEM adds ~+24 kWh | Still infeasible when heavy |
| Refrig on, hot, config A | +~7.9 kWh TRU vs off | Config B: same tractor energy as off |

Config **B** leaves tractor SOC unchanged by TRU (verified in tests and CSV: `E_net_tractor` identical for B on/off).

Figures:

1. `reports/figures/energy_vs_payload_refrig.png` — net tractor vs payload × refrigeration (cool, flat, A)
2. `reports/figures/elevation_cumulative_energy.png` — Casa→Agadir elevation + cumulative energy (DEM vs flat)

---

## 4. Engineering plausibility (not experimental validation)

Mercedes-Benz marketing cites on the order of **~500 km** range for eActros 600 under a **~40 t** / mild (~20 °C) condition. At 600 kWh usable and SOC floor 10%, ~540 kWh is “available,” implying ~**1.08 kWh/km** if 500 km were achieved at that floor.

This pilot’s **heavy / flat / cool** net draw is **higher** (~1.45–1.55 kWh/km), so full Casa–Agadir is **energy-infeasible without en-route charging** under the **assumed** \(C_{rr}\), \(C_dA\), \(\eta\), aux, and 80 km/h cruise. Differences are expected: assumed aero/rolling coefficients, constant high cruise, DSM grades, wind on the cool day, and refrigeration approx. Treat as **plausibility check / sensitivity baseline**, not a claim that the truck cannot achieve published range under OEM test protocol.

Light (25 t) flat missions remain SOC-feasible in this pack without charging.

---

## 5. Parameter provenance table

| Parameter | Value (pilot) | Provenance |
|---|---|---|
| Installed / usable battery | 621 / 600 kWh | manufacturer |
| Continuous / peak drive | 400 / 600 kW | manufacturer |
| Unladen tractor | 11.7 t | manufacturer |
| GCM limit | 44 t | manufacturer |
| Pilot GCM 25 / 40 t | scenario | research |
| \(C_{rr}\), \(C_dA\) | 0.007, 6.5 m² | literature / assumed |
| \(\eta_\mathrm{prop}\), \(\eta_\mathrm{regen}\) | 0.90, 0.70 | assumed |
| \(P_\mathrm{aux}\) | 2.5 kW | assumed |
| SOC min | 0.10 | assumed operating floor |
| UA, COP table | 80 W/K, linear COP | assumed (not Bank calibration) |
| Trailer pack (B) | 30 kWh usable | assumed |
| Elevations | COP-DEM GLO-30 | reanalysis / open DEM (DSM) |
| \(T\), wind, pressure | Open-Meteo 2025 days | reanalysis API |
| Cruise 80 km/h, \(a=0\) | policy | research assumption |

---

## 6. Open issue preserved (Task 01C station access)

Task 01C candidate sites remain **provisional**:

- **5** provisional topological access matches
- **0** legally confirmed HGV-certified access
- Entrance and exit paths are **independent**; **no** continuous in-facility path proof
- **Not** optimization-ready for charger placement / EVRP

Task 02 does **not** redesign access classifiers and does **not** claim charger-feasible missions.

---

## 7. Empirical validation

**Skipped.** No measured e-truck energy dataset for this corridor was available.
