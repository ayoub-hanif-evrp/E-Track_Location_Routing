# Task 02B — Physics audit

Reviewed baseline commit: `9902937`. This checkpoint corrects energy evaluation so it can serve as a trustworthy resource-consumption oracle. **No** routing/charging optimization was implemented.

---

## 1. Confirmed modeling defects (Task 02)

| ID | Defect | Effect |
|---|---|---|
| A | Out-of-bounds DEM samples accepted as 0 m | ~158% fake grades; DEM vs flat energy untrustworthy |
| B | Silent `min(P_batt, peak)` while holding 80 km/h | Under-reported traction energy; false power feasibility |
| C | SOC clipped; feasibility mainly from final SOC / total energy | Mid-trip SOC floor violations could be hidden by later regen |
| D | Haversine edge lengths ≠ Task 01 geodesic | ~+0.53 km distance bias in pilot CSV |
| E | Labels “payload” for 25/40 t | Those values are **GCM**, not cargo payload |
| F | Arithmetic mean of wind direction | Incorrect near 0°/360° wrap |

---

## 2. Corrected equations and assumptions

### Longitudinal forces (unchanged form)

\[
F_\mathrm{roll}=C_{rr}mg\cos\theta,\quad
F_\mathrm{aero}=\tfrac12\rho C_dA v_\mathrm{air}^2\mathrm{sign}(v_\mathrm{air}),\quad
F_\mathrm{grade}=mg\sin\theta,\quad
a=0 \Rightarrow F_\mathrm{trac}=F_\mathrm{roll}+F_\mathrm{aero}+F_\mathrm{grade}
\]

### Motor vs battery power (corrected)

Manufacturer **400 kW continuous / 600 kW peak** are treated as **motor output** (wheel-side capability), not battery DC limits (no invented DC charge/discharge C-rates).

- Required wheel power: \(P_w=F_\mathrm{trac}\,v\)
- Peak feasibility at fixed cruise: \(P_w \le P_\mathrm{peak,motor}\)
- Continuous exceedance is flagged separately (soft / informational)
- Battery discharge power for energy accounting: \(P_\mathrm{batt}=P_w/\eta_\mathrm{prop}\) (**not** silently capped to 600 kW)
- If \(P_w>P_\mathrm{peak}\): segment is **power-infeasible** under the 80 km/h policy; energy still reports the **required** draw at that speed

Regen: \(P_\mathrm{batt}=\eta_\mathrm{regen}P_w\) with peak-regen and SOC-headroom caps (physical). Rejected regen is tracked.

### SOC feasibility (corrected)

Segment-by-segment:

- SOC before/after each segment (raw trajectory before display clipping)
- `minimum_soc`, `minimum_trailer_soc`
- `first_violation_distance_km` / `first_violation_reason`
- Later downhill regen **cannot** clear an earlier SOC-floor violation
- Display clipping to \([0,1]\) is numerical only and does not restore feasibility

`mission_feasible_bool` requires power ∧ tractor SOC ∧ trailer SOC (when applicable) **throughout**.  
If terrain quality is `invalid` / `missing_data` for a DEM scenario → `mission_feasible=None` (**indeterminate**), not a boolean.

### Distance convention (corrected)

All energy edges, elevation profiles, and reported distances use **WGS84 geodesic** metres (`morocco_etruck.road_network.geodesic_length_m`), matching Task 01 baselines (417.000 / 417.113 km).

### GCM vs cargo payload (corrected)

Scenario labels: `gcm_light_25t` / `gcm_heavy_40t`.  
`cargo_payload_kg = GCM − (unladen tractor + assumed trailer curb)`.  
GCM must satisfy empty ≤ GCM ≤ 44 t.

### Wind (corrected)

Daily wind uses **vector-component** aggregation of hourly FROM-directions. Remaining limitation: still a **daily mean**, not a time-resolved wind field along the trip.

---

## 3. DEM diagnostic outcomes

See `reports/task02b_dem_diagnostics.md`. Bounds-aware sampling restored continuous profiles; both directions pass quality gates (`valid`). Task 02 before/after figure committed.

---

## 4. Differences vs Task 02 pilot results

| Aspect | Task 02 | Task 02B |
|---|---|---|
| Distance Casa→Agadir | ~417.53 km | **417.000 km** (= baseline) |
| DEM quality | Invalid zeros/cliff | **valid** (max grade ~14%) |
| DEM − flat energy (heavy, mean order) | ~+25 kWh (untrustworthy) | ~+36 kWh (grade-informed; still research-assumed CdA/Crr) |
| Power feasibility | Always “OK” via silent clip | **8** scenarios power-infeasible (DEM + heavy climbs at 80 km/h) |
| SOC feasibility | Final/total oriented | Path-wise; mid-trip floor enforced |
| Feasibility fields | single bool | `power_feasible_bool`, `soc_feasible_bool`, `trailer_soc_feasible_bool`, `terrain_quality_status`, `minimum_soc`, `first_violation_*`, `mission_status` |

Illustrative feasibility (pilot matrix):

- **Flat + light GCM:** generally feasible (SOC & power)
- **Heavy GCM:** SOC-infeasible on full corridor without charging (unchanged qualitative conclusion; now with first-violation provenance)
- **DEM + heavy:** also **peak-motor** infeasible on some climbs at fixed 80 km/h

CSV: `results/energy_pilot.csv` (64 rows retained; DEM valid so not dropped).

---

## 5. Validation tiers (unchanged honesty)

1. **Mathematical verification:** pytest adversarial suite (66 tests at commit time).
2. **Engineering plausibility:** still not OEM-calibrated; no tuning to force ~500 km marketing range.
3. **Empirical validation:** still absent (no measured e-truck dataset).

---

## 6. Remaining blockers / limitations

- Assumed \(C_{rr}\), \(C_dA\), efficiencies, UA/COP, aux load.
- Fixed 80 km/h policy (no speed adaptation when power-infeasible).
- DSM ≠ pavement; daily-mean weather.
- Task 01C station access remains provisional (unchanged).

**STOP after Task 02B** — do not start Task 03 until researcher review.
