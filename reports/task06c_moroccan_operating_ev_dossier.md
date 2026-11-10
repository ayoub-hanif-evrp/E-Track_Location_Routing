# Task 06C — Real Moroccan electric refrigerated vehicle dossier

**Role:** observed Moroccan cold-chain electrification evidence.  
**Not** a highway tractor–semitrailer physics pack. **No runnable YAML in 06C.**

Access date: 2026-11-10

## Deployment claim (supported)

Petit Forestier Morocco put into circulation the first fully electric refrigerated heavy vehicle in Morocco, used in logistics rounds by **Centrale Danone Maroc**, after SIAM demonstration. Urban / peri-urban duty.

Sources:

- https://www.petitforestier.com/fr-ma/posts/270_petit-forestier-met-en-circulation-le-premier-poids-lourd-frigorifique-100-electrique-au-maroc
- https://h24info.ma/paroles-dexpertss/paroles-dexperts-de-faical-tadlaoui-petit-forestier-electrise-le-transport-frigorifique-au-maroc/

## Published technical figures (H24 interview / PF communication)

| Item | Published | Evidence class | Notes |
| --- | --- | --- | --- |
| Vehicle class | 7.5 t | confirmed (press) | Not 40 t articulated tractor |
| Battery | 2× Li-ion; **107 kWh** total installed | confirmed (press) | Usable energy **unresolved** |
| Range with refrigeration | ~**120 km** | confirmed (press claim) | Not a Task-02B validated figure |
| Typical customer day | ~50–60 km/day | confirmed (interview) | Urban/peri-urban |
| DC charge | **90 kW**; full charge &lt; 2 h (claim) | confirmed (press) | Curve unresolved |
| Powertrain / TRU | motor + fridge group 100% electric; TRU from vehicle batteries | confirmed (press) | Exact chassis/OEM **unresolved** |
| Operator | Centrale Danone Maroc | confirmed | |
| Lessor | Petit Forestier Maroc | confirmed | |

## Explicitly unresolved (do not invent)

- Exact chassis brand/model designation and VIN-free datasheet
- Usable battery energy vs installed 107 kWh
- Unladen mass, payload, axle layout
- Continuous/peak motor ratings
- Measured kWh/km with/without cold
- TRU electrical load vs ambient/setpoint
- GPS route geometry and ambient/cargo temperature logs
- Charge session power-vs-SOC records

## Data request list (Petit Forestier / Centrale Danone)

1. Exact vehicle model designation and technical sheet (no VIN required).
2. Battery usable energy and SOC operating window.
3. Unladen mass and rated payload.
4. Measured energy use (kWh/km) with refrigeration on/off.
5. TRU electrical power vs ambient and setpoint.
6. Representative GPS distance/duration for Danone rounds.
7. Ambient and cargo temperature time series.
8. Charging records (kW, kWh, duration, connector).
9. Duty-cycle distribution (stops, idle with cold on).

## Separation from highway research

| Highway B&B–MRLS corridor study | This dossier |
| --- | --- |
| Prospective Volvo FH / eActros tractor–semitrailer | 7.5 t urban EV |
| Casa–Marrakech–Agadir path unions | Urban/peri-urban Danone distribution |
| 25–40 t GCM research scenarios | ~7.5 t class |

**Do not** run this vehicle on 40 t motorway missions. If sufficient evidence arrives later, plan a **separate** urban-distribution dataset and experiment.
