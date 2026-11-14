# Moroccan realism and freight-direction audit (PASS 1)

Reviewed HEAD: `c43bed9`  
Access date for external pages: 2026-11-14  
Scope: scientific integrity only — **no PASS 2 scenario rewiring in this document.**

---

## Executive finding

Task 07/08 primary placement portfolios are **southbound-only** (Casablanca→Marrakech / Casablanca→Agadir / Marrakech→Agadir). That corridor is geographically real, but it is **not** a representative model of Moroccan refrigerated export logistics.

Authoritative Moroccan sources motivate a **primary northbound agricultural refrigerated** use case (Souss-Massa / Agadir toward Casablanca and northern export gateways). Southbound movement should be retained only as a **separate domestic distribution** case with its own commodity justification — not as “Moroccan cold chain overall.”

The repository already contains reverse OD road alternatives and opposite-direction Settat/Benguerir candidates. **Northbound experiments do not require a nationwide graph rebuild.** Critical gaps remain (DEM coverage for reverse ODs; missing reverse Amskroud; no commodity-specific demand matrix).

---

## 1. What Task 07/08 currently models

| Mission | OD | Weight | Direction |
| --- | --- | ---: | --- |
| `M_casa_marrakech` | `casa_marrakech` | 2.0 | southbound |
| `M_casa_agadir` | `casa_agadir` | 2.0 | southbound |
| `M_marrakech_agadir` | `marrakech_agadir` | 1.5 | southbound |

Sources: [`configs/optimization/multiroute_placement_07a.yaml`](../configs/optimization/multiroute_placement_07a.yaml), [`multiroute_placement_08.yaml`](../configs/optimization/multiroute_placement_08.yaml), [`reports/task07a_demand_portfolio_audit.md`](task07a_demand_portfolio_audit.md).

Candidate sites in those portfolios are **only** `y_settat_ca`, `y_benguerir_ca`, `y_amskroud_ca` (`direction: casablanca_to_agadir`).

Demand weights are explicitly **illustrative**, not observed annual Moroccan volumes.

---

## 2. External motivation for northbound refrigerated freight

### Tanger Med Port Authority (Souss-Massa exporters)

Primary source: [Tanger Med — rencontre avec les exportateurs Souss-Massa](https://www.tangermedport.com/fr/le-port-tanger-med-organise-une-rencontre-avec-les-exportateurs-de-la-region-souss-massa/) (published 2023-01-02; event Oct 2022).

Documented points used here:

- Tanger Med organizes exporter engagement **in Agadir** for the Souss-Massa region.
- Souss-Massa is described as a leading Moroccan export region for **primeurs** and **agrumes** (page states >85% of primeur exports and ~65% of citrus exports associated with this region via Tanger Med).
- Port services include a dedicated export platform and a **refrigerated logistics unit**, with RoRo/maritime connectivity.

**Implication for this repository:** northbound refrigerated agricultural freight from Souss-Massa toward Casablanca (and onward toward northern export gateways) has a clear Moroccan logistics rationale.  
**Hard stop for this checkpoint:** do **not** expand the physical OD graph to Tanger Med. Tanger Med motivates the **purpose**; the present verified network ends at Casablanca ([directive Gate 1.4](.)).

### SOTRAFRIQUE (Moroccan refrigerated operator)

Primary source: [SOTRAFRIQUE — Moyens](https://sotrafrique.com/fr/moyen).

Documented points:

- Temperature-controlled transport; refrigerated semi-trailers with GPS and temperature recorders.
- Fleet includes Volvo/Scania tractors and ~30 fridge semi-trailers; larger subcontractor pool.
- Administrative footprint **Agadir–Tanger**; bureau at **Tanger Med** for port operations.

**Implication:** a real Moroccan refrigerated operator already links southern production geography with northern port logistics. This supports Case A motivation; it does **not** provide trip counts or OD GPS for this repo.

### ADM service areas

Directory: [ADM — gares de péage et aires de services](https://www.adm.co.ma/fr/gares-de-peage-et-aires-de-services).  
Repo audits: [`reports/task05c_station_attachment_audit.md`](task05c_station_attachment_audit.md), [`reports/task07a_moroccan_site_evidence.md`](task07a_moroccan_site_evidence.md), [`reports/site_access_audit.csv`](site_access_audit.csv).

---

## 3. Two SEPARATE logistics cases (proposed for PASS 2; not yet implemented)

### Case A — Primary: northbound agricultural refrigerated freight

| Field | Proposed definition | Evidence grade |
| --- | --- | --- |
| Purpose | Outbound refrigerated agricultural produce from Souss-Massa toward Casablanca / northern export chain | Sourced motivation (Tanger Med; SOTRAFRIQUE footprint) |
| Primary OD | `agadir_casa` | Road data **exists** (`path_alternatives.csv`, decision graph) |
| Corridor node | Marrakech may appear on path alternatives; **do not** add `agadir_marrakech` as a second independent shipment of the same load | Anti double-count rule |
| Commodity category | Fresh produce / citrus–primeurs cold chain (category-level; not SKU-level) | Sourced category; **not** measured shipment mix |
| Cargo setpoint | Product-specific (see law/cold-chain audit) — **not** universal +2 °C | To be graded in PASS 2 |
| Candidate chargers | `settat_ac`, `benguerir_ac` only | Topology present; planning class remains hypothetical truck power |
| Reverse Amskroud | **Unavailable** — do not fabricate `amskroud_ac` | Explicit repo gap |
| Annual trips | **Unknown** — illustrative weights only | Must not invent |

### Case B — Secondary: southbound refrigerated distribution

| Field | Proposed definition | Evidence grade |
| --- | --- | --- |
| Purpose | Domestic refrigerated distribution / inbound supply toward southern markets (e.g. urban/retail replenishment) | Plausible but **weaker** sourced export rationale than Case A |
| ODs | Existing `casa_marrakech`, `casa_agadir` (and optionally `marrakech_agadir` only if justified as a **distinct** distribution leg — not a silent re-label of Case A) | Existing Task 07/08 |
| Commodity | Separate category from export produce (e.g. dairy / prepared chilled goods) — to be declared, not assumed identical to Case A | Currently underspecified |
| Chargers | `settat_ca`, `benguerir_ca`, `amskroud_ca` | Topology matchable; **not** verified 350 kW HGV chargers |

**Do not delete** historical southbound Task 07/08 results. **Do** stop presenting them as representative of Moroccan cold-chain logistics overall. Mark them as Case B / historical southbound portfolio.

---

## 4. Repository readiness for northbound Case A (without rebuild)

| Asset | Status |
| --- | --- |
| OD `agadir_casa` path alternatives (4) | Present |
| OD terminals / anchors | Present |
| `settat_ac`, `benguerir_ac` charger specs | Present in `multiroute_pilot.yaml` |
| Reverse Amskroud | **Missing** — correctly unresolved |
| DEM elevation macros for reverse ODs | **Gap** — `dem_sampling_meta.json` currently covers southbound pilot ODs only |
| Task 07/08 demand + placement configs | Southbound only — need new demand block in PASS 2 |
| Commodity / setpoint differentiation | Missing |
| Observed trip frequencies | Missing |

**PASS 2 prerequisite:** before claiming DEM northbound results, either (i) generate/verify DEM macros for `agadir_casa` (and any used reverse ODs), or (ii) run flat-terrain diagnostics labeled as such — never silently reuse southbound DEM tables.

---

## 5. Invalidated / overscoped claims (direction)

| Claim | Status after this audit |
| --- | --- |
| “Task 07/08 portfolio represents Moroccan refrigerated freight” | **Too broad** — it represents a southbound research portfolio |
| “One-site vs two-site is the Moroccan cold-chain answer” | Already conditional after Task 08 SOC/payload; further conditional on **direction** |
| Northbound requires rebuilding the whole project | **False** — reverse paths and Settat/Benguerir AC exist |
| Reverse Amskroud can be assumed symmetric | **False** — must remain UNKNOWN / unavailable |

---

## 6. PASS 1 acceptance checklist (Gate 1)

| Requirement | PASS 1 status |
| --- | --- |
| Two separate cases A/B motivated | Defined above |
| Every mission tied to a logistics activity category | Framework defined; PASS 2 must instantiate metadata |
| Reuse existing reverse OD data | Confirmed available |
| No Tanger Med OD expansion | Affirmed |
| No double-counting Agadir→Marrakech as extra demand for same shipment | Rule stated |
| No invented annual frequencies / no claim that all cold chain is northbound | Affirmed |

**PASS 2 may begin only after independent review of this audit.**
