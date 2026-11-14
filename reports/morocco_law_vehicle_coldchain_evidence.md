# Moroccan law, vehicle, and cold-chain evidence matrix (PASS 1)

Reviewed HEAD: `c43bed9`  
Legal source accessed: 2026-11-14  
Primary legal text: [Décret n° 2-10-421 (texte consolidé SGG)](https://www.sgg.gov.ma/Portals/1/textesconsolides/2_10_421.pdf) — application of Law 52-05 on vehicles.  
Secondary reading aids: MarocTL summaries of Arts. 3–5 (not a substitute for the decree).

---

## 1. Legal heavy combination (4×2 tractor + 3-axle semi-trailer)

### Gross combination mass (PTRA / poids total roulant)

Under Decree **2-10-421 Article 3**, for articulated vehicles with five or six axles:

- Motor vehicle with **2 axles** + semi-trailer with **3 axles**: **40 000 kg**
- Motor vehicle with **3 axles** + semi-trailer with **2 or 3 axles**: **40 000 kg**
- Combined-transport 40-ft container exceptions: **44 000 kg** (specific configurations)

**Modeled research configuration** (repo): 4×2 tractor + refrigerated semi-trailer treated as three-axle combination → falls under the **40 t** five-axle articulated provision **if** the trailer is indeed three-axle. Trailer axle count is **not instrumented** in YAML geometry — only curb mass assumptions exist.

### Axle limits (Article 4 — summary for audit)

From the decree text / consolidated reading aids:

| Component | Limit (decree) | Repo status |
| --- | ---: | --- |
| Simple non-driven axle | 10 t | **Not checked** (no axle-load model) |
| Drive axle (relevant articulated configs) | up to **11.5 t** (Art. 4 drive-axle table for listed combinations) | **Not checked** |
| Tandem / tri-axle groups | Decree tables (spacing-dependent) | **Not checked** |
| Driven-axle share of GCM | ≥ 25% of combination mass (Art. 5 vicinity) | **Not checked** |

### Dimensions (Article 5 vicinity)

Maximum width generally **2.55 m**; articulated length limits apply (standard EU-like 16.5 m articulated envelope in Moroccan practice summaries). Repo does **not** encode vehicle envelope checks on OSM.

### Manufacturer GCW vs Moroccan legal PTRA

| Vehicle | Tech GCW (YAML) | GCM @ 15 t cargo (assumed empty+payload) | Moroccan 40 t articulated screen |
| --- | ---: | ---: | --- |
| Volvo FH Electric 4×2 | 65 t manufacturer | ~35 t | Gross mass **≤ 40 t** if axle config matches Art. 3 |
| eActros 600 | 44 t manufacturer | ~34.7 t | Same gross-mass screen |

**Critical honesty rule (already in Task 08; reinforced here):**

> A GCM of ~35 t under manufacturer GCW does **not** prove axle compliance.  
> Correct metadata label: `gross_mass_within_limit_axle_unverified` — **not** `legally_certified`.

Driver hours-of-service (Moroccan Code de la route / labour rules) are **not modeled**. Foreign HOS rules must not be silently imported; if used for sensitivity, label the foreign source.

**Amendments:** secondary Arabic portal notes later complements (e.g. references to Decree 2.24.393). PASS 2 must re-check the latest consolidated SGG PDF before any “legal compliance” wording. This PASS 1 audit does **not** claim a full amendment search is closed.

---

## 2. Vehicle evidence matrix (prospective highway pack)

### Volvo FH Electric 4×2 — Moroccan manufacturer page

Source: [volvotrucks.ma — FH Electric](https://www.volvotrucks.ma/fr-ma/trucks/electric/volvo-fh-electric.html) (accessed 2026-11-14).  
YAML: `configs/vehicles/volvo_fh_electric_4x2_540kwh.yaml` (+ usable460 sensitivity).

| Parameter | Value in repo | Provenance |
| --- | --- | --- |
| Installed energy | up to 540 kWh | Manufacturer page |
| Usable energy | 475 kWh (MA page); 460 kWh global sensitivity | Manufacturer-labeled conflict — **do not merge** |
| CCS charge | up to 350 kW; ~65 min 20→80% claim | Manufacturer-advertised |
| Performance menu | 300 / 350 / 400 / 470 / 540 kW | Manufacturer list — **no continuous vs peak split published** |
| Repo continuous/peak | 400 / 400 kW | **`assumed_variant_pick`** |
| PTR / GCW | up to 65 t | Manufacturer |
| Axles offered | 4×2, 6×2, 6×4 (tractor) | Manufacturer |
| ePTO | Advertised (incl. fridge applications in marketing) | Menu/marketing — **≠** proven TRU pairing |
| Tractor curb mass | 12 000 kg | **Assumed** |
| Trailer curb | 8 000 kg | **Assumed** |
| CdA / η / aux / soc_min | research pack | **Assumed** |
| Config A (TRU on tractor battery) | default | **Declared research assumption** / unresolved compatibility |

**Do not mix** FH Electric with FH Aero Electric Extended Range / MCS / FE Electric (repo already states this).

### Mercedes-Benz eActros 600 comparator

YAML: `configs/vehicles/eactros_600.yaml`.

| Parameter | Grade |
| --- | --- |
| 621 / 600 kWh; cont 400 / peak 600 kW; tractor 11.7 t; GCW 44 t | Manufacturer-labeled |
| Trailer 8 t; aero/aux; Config A | Assumed / declared |

### Heavy-load Task 08 interpretation (must not overclaim)

From [`reports/final_heavy_vehicle_feasibility_diagnosis.md`](final_heavy_vehicle_feasibility_diagnosis.md):

- Volvo 15 t H50/H80 Ball = 0/5.5 under assumed 400 kW + q=10 DEM path-union.
- Causes are **mixed**: peak_motor (CA), soc_floor (MA / CM@50%), **discrete_grid_reject** (CM@80% q=10 → served at q=5).
- Configuration-dependent on assumed power pick.

**Forbidden claim:** “Volvo cannot transport 15 t in Morocco.”  
**Allowed claim:** discrete-model infeasibility under the assumed stack; parts are grid- and configuration-dependent.

---

## 3. Refrigerated cold-chain evidence

### Current repo practice

| Item | Current value | Grade |
| --- | --- | --- |
| Setpoint | +2 °C for essentially all refrigerated missions | **Assumed example** — not product-specific |
| UA | 80 W/K nominal | Assumed |
| COP table | Engineering table | Assumed |
| Infiltration / door openings | 0 W nominal | Assumed / optimistic |
| Config A vs B | A default; B independent trailer pack (30 kWh assumed) | Declared assumptions |
| Bank et al. (2025) TRU model | Inspiration only (DOI 10.1016/j.ijrefrig.2025.04.026) | Not calibrated twin |

### PASS 2 requirement (Gate 3 acceptance)

Define **at least one explicit cargo category** with a source-supported temperature band, for example:

| Case | Commodity category | Indicative setpoint band | Source class |
| --- | --- | --- | --- |
| A northbound | Fresh produce / citrus–primeurs | chilled above freezing (category band; cite FAO/ATP-class guidance or Moroccan operator practice if obtained) | Category-level; **not** SKU-validated |
| B southbound | Separate chilled category (e.g. dairy / prepared foods) | Distinct band — **do not** copy Case A blindly | To be sourced or labeled assumed |

Include refrigeration during **driving, charging, and stopping**. Keep Config A labeled as electrical-integration assumption until compatibility evidence exists. Never inflate UA/infiltration merely to enlarge charger need.

---

## 4. Infrastructure and economic evidence (Gate 4 snapshot)

### Candidate stations

| Site key | ADM identity | Direction | Topology | Operating 350 kW HGV charger? |
| --- | --- | --- | --- | --- |
| `settat_ca` / `settat_ac` | Settat service area (ADM directory) | CA / AC | Matchable on OD union when present | **No proof** — hypothetical deployment power |
| `benguerir_ca` / `benguerir_ac` | Benguerir | CA / AC | Matchable | **No proof** |
| `amskroud_ca` | Amskroud | CA only | Matchable southbound | **No proof** |
| `amskroud_ac` | — | AC | **UNKNOWN / missing** | Must not fabricate |

Grid connection capacity, civil CAPEX, O&M: **UNKNOWN** (do not invent MAD quotes).

### ONEE / electricity economics

Official professional/MT pages exist (e.g. [ONEE tarifs professionnels](https://www.one.org.ma/fr/pages/interne.asp?esp=1&id1=2&id2=35&t2=1); MT billing elements include kWh price, tariff option, subscribed/called power, power factor, metering fees).

Published secondary discussion of MT time-of-use bands exists in press; ANRE network-use tariffs (TURD) are a **different** charge class and must not be confused with energy retail.

**Repo today:** uniform research ¢/kWh + illustrative CAPEX=100.  
**Correct classes (retain):**

- **A** — min sites for discrete feasibility  
- **B** — normalized illustrative cost optimization  
- **C** — Moroccan economic sensitivity with explicit sourcing and applicability limits — **not** an investment forecast  

Never mix annualized CAPEX with dimensionless `w × trip cost` and call it Moroccan annual cost ([`final_economic_units_and_provenance_audit.md`](final_economic_units_and_provenance_audit.md)).

---

## 5. Acceptance status (Gates 2–4 for PASS 1)

| Gate | Status |
| --- | --- |
| Legal 40 t articulated screen identified | **Done** (Art. 3) |
| Axle geometry / kingpin / distribution | **Unresolved** → `gross_mass_within_limit_axle_unverified` |
| Vehicle provenance matrix | **Done** (this file + Task 06C) |
| Product-specific cold chain | **Not yet** — required in PASS 2 scenario metadata |
| No invented charger power / CAPEX / volumes as verified | **Affirmed** |

**PASS 2 may begin only after independent review.**
