# Task 07C — Evidence and novelty matrix

## Vehicles (frozen)

| Role | Spec | Provenance grade |
| --- | --- | --- |
| Primary prospective highway tractor | Volvo FH Electric 475 kWh usable (`volvo_fh_electric_4x2_540kwh.yaml`) | Manufacturer verified (Volvo Trucks Morocco FH Electric documentation / brochure specs) |
| Battery sensitivity | Volvo FH Electric 460 kWh usable variant | Manufacturer documented specification sensitivity |
| Comparator | Mercedes-Benz eActros 600 (600 kWh usable) | Manufacturer verified |
| Moroccan e-refrigerated deployment (dossier only) | Petit Forestier / Centrale Danone context | Official deployment case — **not** used as 40 t highway OD tractor in this matrix |

Do **not** substitute vans or 7.5 t distribution trucks into 40 t highway scenarios.

## Infrastructure and demand provenance

| Parameter | Value in freeze | Grade | Notes |
| --- | --- | --- | --- |
| Candidate sites Settat / Benguerir / Amskroud | Directional ADM service-area topology | Official infrastructure identity + OSM topology | **Not** certified HGV access; **not** operating 350 kW truck chargers |
| Charger power 150 / 350 kW | Hypothetical truck-compatible power | Engineering assumption | Volvo FH Electric docs mention up to 350 kW charging for the generation; ADM Programme AZUR / 2025 annual report describe EV charging for cars at service areas — not HGV 350 kW at these sites |
| Payload 5300 kg | Fixed cargo comparison design | Engineering assumption | Not observed fleet payload |
| Demand weights (total 5.5) | `cold_chain_baseline_07a/07b` | Engineering assumption / illustrative | Not observed Moroccan refrigerated volumes |
| Refrigeration UA 50/80/120 W/K | Documented YAML sensitivity | Engineering assumption | Inspired by cold-chain literature (e.g. Bank et al. 2025) — **not** calibrated to Moroccan TRU logs |
| Infiltration 500 W scenario | Explicit assumed duty | Unverified / unavailable | Labeled separately from calibrated params |
| DEM terrain | COP-DEM GLO-30 macros | Official open data | Task 05B complete for CM/CA/MA |
| Road speeds | Research cruise / OSM maxspeed policy | Engineering assumption | Not observed HGV speeds |
| Electricity tariff | Uniform research ¢/kWh | Engineering assumption | Not a Moroccan industrial tariff quote |
| Deadlines 8/10/12/20 h | Illustrative feasibility windows | Engineering assumption | Not observed contracts |

## Literature bars (novelty positioning)

| Source | Role for this study |
| --- | --- |
| Plaza et al. (2026) — charger location with routing and driver HOS for long-haul e-trucks | Prior art on joint siting+routing; our novelty is **not** “B&B+MRLS exists” |
| Bank et al. (2025) — refrigerated trailer thermal/power model with test-drive data | Thermal modeling bar; we use transparent UA ranges, not a calibrated TRU twin |
| Cheng et al. (2026) — temperature-aware e-truck charging infrastructure planning | Related infrastructure+temperature literature |

**Testable contribution:** how vehicle battery configuration, cold-chain energy demand, DEM terrain, and direction-specific motorway candidates jointly affect the **minimum hypothetical network** needed to serve a defined Moroccan refrigerated-freight portfolio — under fair nested baselines and stated uncertainty grades.

## Moroccan operational leads (external evidence, not invented)

| Source | What it supports | What it does **not** validate |
| --- | --- | --- |
| Volvo Trucks Morocco FH Electric pages | Prospective refrigerated tractor + up to 350 kW charging for that generation | Exact trailer integration or Moroccan deployment |
| ADM annual report 2025 / Programme AZUR | EV charging presence on the motorway network | Truck-compatible 350 kW at Settat/Benguerir/Amskroud |
| SOTRAFRIQUE public refrigerated fleet / GPS / temperature recorders | Candidate for requesting anonymized ops data | Any numbers used in this freeze |
| Petit Forestier Moroccan e-refrigerated deployment | Confirmed distribution-scale case (dossier) | Highway 40 t OD placement claims |

## Study framing (honest)

This freeze is an **evidence-grounded prospective optimization study**. It is **not** a field-validated Moroccan deployment recommendation.
