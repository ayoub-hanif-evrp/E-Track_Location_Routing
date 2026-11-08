# Task 02 / 02B — Energy model validation report

**Scope:** Physics-based corridor energy for eActros 600 refrigerated combination on A3 Casablanca–Agadir baselines. No routing/charging optimization.

Task **02B** corrected DEM sampling, power feasibility, path-wise SOC, geodesic distances, GCM terminology, and wind aggregation. Detailed audit: `reports/task02b_physics_audit.md`, DEM: `reports/task02b_dem_diagnostics.md`.

---

## 1. Mathematical verification (pytest)

Offline unit/integration + adversarial tests cover DEM grade artifacts, missing pixels, peak-power flags without silent energy clipping, mid-trip SOC floors, regen at full SOC, GCM bounds, geodesic distance consistency, circular wind means, and indeterminate DEM missions.

Run: `pytest -q`.

---

## 2. Data retrieval status

| Source | Status | Notes |
|---|---|---|
| Open-Meteo Historical | **OK** | Hot=2025-07-15, cool=2025-01-15; vector-mean wind |
| AWS COP-DEM GLO-30 | **OK after 02B fix** | Bounds-aware sampling; quality=`valid` both directions |
| Flat-road baseline | Always available | `terrain=flat` |

---

## 3. Pilot results (Task 02B)

64 scenarios → `results/energy_pilot.csv`. Distance matches Task 01 geodesic (**417.000 / 417.113 km**).

New fields: `power_feasible_bool`, `soc_feasible_bool`, `trailer_soc_feasible_bool`, `terrain_quality_status`, `minimum_soc`, `first_violation_distance_km`, `first_violation_reason`, `mission_feasible_bool`, `mission_status`, `gcm_label`, `cargo_payload_kg`.

Qualitative: light GCM flat missions remain energy-feasible; heavy GCM corridor missions violate SOC floor without charging; some DEM+heavy segments are peak-motor infeasible at fixed 80 km/h.

---

## 4. Engineering plausibility (not experimental validation)

Unchanged honesty: assumed aero/rolling coefficients are not OEM coast-down data; no calibration to force published ~500 km range.

---

## 5. Parameter provenance

See methodology report and vehicle/refrigeration YAML `provenance` fields. Task 01C access matches remain provisional (5 topological / 0 HGV-certified; no continuous facility path).

---

## 6. Empirical validation

**Skipped** — no measured e-truck dataset available.
