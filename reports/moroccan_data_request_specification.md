# Moroccan data-request specification (PASS 1)

Status: **request-ready external collection sheet**  
Reviewed HEAD: `c43bed9`  
Date: 2026-11-14  

**Important:** This document does **not** imply that SOTRAFRIQUE, ADM, ONEE, Volvo Trucks Morocco, or any other party has already shared data with this project.

Purpose: enable privacy-preserving empirical validation of the prospective refrigerated eHDT placement/routing study after PASS 1 scientific-integrity audits.

---

## 1. Refrigerated freight operator (e.g. SOTRAFRIQUE or peer)

Public context already known: temperature-controlled fleet, Agadir–Tanger footprint, Tanger Med operations desk ([sotrafrique.com/fr/moyen](https://sotrafrique.com/fr/moyen)).

### Request

If available, **10–30 anonymized trips** (or trip segments) with:

| Field | Detail | Required? |
| --- | --- | --- |
| OD and direction | e.g. Agadir→Casablanca / Casablanca→Agadir; approximate terminals OK | Yes |
| Route representation | Timestamped GPS **or** aggregated ADM/road sections | Yes (one form) |
| Cargo category | Produce / citrus / dairy / mixed chilled — **category**, not customer SKU | Yes |
| Approximate payload | Tonnes or load factor band | Preferred |
| Trailer type | Refrigerated semi-trailer class | Preferred |
| Setpoint | °C | Preferred |
| Recorded cargo temperature | Time series or min/max/mean | Preferred |
| Ambient temperature | If recorded | Optional |
| Driving / stop durations | Hours | Preferred |
| Departure / arrival times | Local timestamps | Preferred |
| Refrigeration energy or fuel use | kWh or diesel-equivalent for TRU | Optional |
| Charging / fuel stops | Location class only (depot / motorway / port) | Optional |

### Explicitly do **not** request

- Vehicle identification numbers (VIN)
- Driver personal identifiers
- Customer names / invoice identities
- Commercially sensitive shipment values or contracts
- Exact GPS of private customer docks if aggregation is available

### Privacy / ethics

Anonymize trip IDs; aggregate where needed; store under a data-use agreement; publish only derived statistics unless written consent allows otherwise.

---

## 2. ADM / motorway / site partners

For each candidate service area under study (Settat, Benguerir, Amskroud — **both carriageway directions** where applicable):

| Field | Detail |
| --- | --- |
| Official ADM site identity | Name / code |
| Carriageway direction | e.g. Casablanca→Agadir vs Agadir→Casablanca |
| HGV access and geometry | Entrance/exit suitability for articulated trucks; turning constraints |
| Existing EV charging | Connector type, rated kW, operator, truck vs car suitability |
| Available electrical capacity | kVA / kW headroom if known |
| Grid connection feasibility | Indicative only — not a binding quote |
| Unknowns | Mark **UNKNOWN** — do not invent |

**Special note:** reverse-direction Amskroud remains unresolved in-repo. Request confirmation whether a northbound truck-accessible installation point exists; if not, keep `amskroud_ac = UNAVAILABLE`.

---

## 3. Vehicle manufacturer / Moroccan representation (Volvo FH Electric focus)

Cross-check against [volvotrucks.ma FH Electric](https://www.volvotrucks.ma/fr-ma/trucks/electric/volvo-fh-electric.html).

| Field | Why needed |
| --- | --- |
| Exact continuous vs peak motor ratings for ordered configurations | Repo currently assumes 400/400 from the 300–540 menu |
| Actual tractor curb mass (configuration-specific) | Repo uses assumed 12 t |
| Battery usable / charge-acceptance curve (CCS taper) | Beyond headline 350 kW / 20–80% time |
| ePTO electrical interface documentation for refrigerated trailers | Config A compatibility evidence |
| Any Morocco-specific homologation notes for GCW / axle packages | Separate manufacturer GCW from Decree 2-10-421 PTRA |

Comparator eActros 600: only request fields still assumed (trailer interface, regen, acceptance curve) if pursuing a matched dual-OEM empirical section.

---

## 4. Utility / tariff clarification (ONEE or site host)

Use official pages as starting points (e.g. ONEE professional/MT tariff family). Request clarification of **applicable class** for a motorway HGV charger host:

- MAD/kWh by time band (if MT bi-horaire / vert / général applies)
- Power subscription (MAD/kW·year) if applicable
- Whether ANRE network-use charges (TURD, etc.) apply to the host model under study
- Applicability limits (not every charger host is an ONEE MT industrial customer)

Do **not** treat press secondary numbers as verified contracts without confirmation.

---

## 5. How responses will be used in the research

| If data arrive | Research use |
| --- | --- |
| Operator trips | Recalibrate Case A/B demand motivation; validate setpoints/durations; never claim full national coverage |
| ADM site facts | Upgrade evidence grades from hypothetical → verified where proved; keep unknowns explicit |
| OEM electrical/mass facts | Replace assumed power/mass grades; re-run **targeted** sensitivities only |
| Tariff class confirmation | Enable economics class **C** sensitivity with sourced units — still not an investment forecast without CAPEX quotes |

If data do **not** arrive: PASS 2 proceeds with graded assumptions already documented in the PASS 1 audits; publication must keep external validation **pending**.

---

## 6. Contact package checklist

- [ ] One-page project summary (non-confidential)
- [ ] This specification attached
- [ ] Data-use / anonymization statement
- [ ] List of candidate sites and ODs under study
- [ ] Explicit statement: no obligation to share; partial answers welcome
