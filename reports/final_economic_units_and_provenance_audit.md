# Final economic units and provenance audit

## Objective formula (code)

Lexicographic placement objective ([`multiroute_placement_evaluation.py`](../src/morocco_etruck/optimization/multiroute_placement_evaluation.py)):

1. Maximize coverage \(\sum_m w_m\) over served missions.
2. Minimize secondary cost  
   \(\mathrm{CRF}\cdot\sum_s y_s\,\mathrm{CAPEX}_s + \sum_{m\ \mathrm{served}} w_m\cdot C_{\mathrm{var},m}\)  
   with \(C_{\mathrm{var},m}\) = MRLS trip objective (road ¢ + energy ¢) × `cents_to_currency` (0.01).

CRF uses \(r=0.08\), \(n=15\) yr ([`placement_problem.py`](../src/morocco_etruck/optimization/placement_problem.py)).

## Unit ledger

| Term | Declared unit in code | Time basis |
| --- | --- | --- |
| Site CAPEX | research currency units (illustrative 100) | one-time |
| CRF × CAPEX | currency / year | annual |
| Road / energy trip cost | currency per mission solve | per trip |
| Demand weight \(w\) | dimensionless illustrative weight (total 5.5) | **not** defined as trips/year |

**Conclusion:** annualized infrastructure and weight×trip operating cost are **not** demonstrated to share a common annual time basis. Monetary secondary objectives are **normalized illustrative research costs**, not Moroccan annual cash flows.

## Provenance corrections

| Item | Correct grade |
| --- | --- |
| eActros / Volvo usable kWh (as labeled) | Manufacturer-labeled YAML (Volvo MA usable note) |
| Tech GCW limits | Manufacturer |
| Volvo empty tractor curb (12 t) | **Assumed** |
| Refrigerated trailer empty (8 t, both OEMs) | **Assumed** |
| Empty combination | Derived tractor+trailer; **not** OEM-verified combo |
| Truck/trailer electrical compatibility | **Not demonstrated** |
| Manufacturer GCW vs Moroccan legal axle/GCW | **Not equivalent**; axle detail unavailable |
| Candidate charger sites | Hypothetical / not operating verified HGV chargers |
| Site CAPEX, uniform ¢/kWh, road 100 ¢/km | Illustrative |
| ONEE tariff / MAD construction quotes | **Not invented** — unavailable for these sites |

## Three outcome classes

### A. Discrete model feasibility and minimum sites

Coverage under MRLS + replay on the DEM path-union with fixed research physics. Includes Task 08 SOC/payload tables and the heavy-Volvo diagnosis. Secondary cost is **not required** for these claims.

### B. Optimization under illustrative costs

B0/B1/B2/Ball and CAPEX ratio (0.5×/1×/2×) rankings under equal illustrative CAPEX. Useful for combinatorial sensitivity only. When high CAPEX empties B1, that is a **budget arithmetic** result, not an investment forecast.

### C. Real-world Moroccan investment — not validated

Requires site-specific equipment/civil/grid quotes, O&M, observed annual trip frequency, HGV access certification, and legal axle/GCW compliance. **None of these are established in-repo.**

## CAPEX ratio reminder (Task 08)

Equal illustrative CAPEX scaled by 0.5 / 1 / 2 can change **which site set is budget-feasible** (e.g. 2× empties B1). That is still class **B**, not class **C**.
