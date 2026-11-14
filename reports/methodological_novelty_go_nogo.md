# Methodological novelty — GO / NO-GO decision (PASS 1)

Reviewed HEAD: `c43bed9`  
Decision date: 2026-11-14  
Question: Is “B&B + MRLS on a Moroccan corridor” enough for a top-tier methods contribution? **No.** What, if anything, is falsifiably new?

---

## 1. Literature benchmark (must clear)

**Vidotte Plaza et al. (2026).** *The charger location problem with routing and driver working hours for long-haul electric heavy-duty trucks.* Transportation Research Part C, 186, 105598.  
DOI: [10.1016/j.trc.2026.105598](https://doi.org/10.1016/j.trc.2026.105598)

Already combines:

- charger location decisions,
- long-haul electric heavy-truck routing,
- driver hours-of-service scheduling,
- time-expanded network modeling.

**Therefore:** joint siting + routing + charging is **not** novel by itself. Claiming novelty for “we also use branch-and-bound with a label-setting router” would not survive peer review against this benchmark.

Related prior art families (not exhaustive): EV location-routing / charging-station location; resource-constrained shortest paths / EVSPP label algorithms; adaptive discretization / state-space refinement in dynamic programming; refrigerated transport energy models (e.g. Bank et al. 2025, DOI 10.1016/j.ijrefrig.2025.04.026 — physics, not siting).

---

## 2. What our repository uniquely demonstrates today

| Element | Present? | Novel as algorithm? | Novel as scientific evidence? |
| --- | --- | --- | --- |
| Finite-model B&B–MRLS with replay certification | Yes | Incremental engineering | Useful reproducibility |
| Same-graph multi-route nesting (07C) | Yes | Narrow methods detail | Important validity fix |
| DEM + refrigerated duty on Moroccan ADM candidates | Yes | Application packaging | Strong case-study value **if** freight direction is fixed |
| Directional topology-verified vs hypothetical sites | Yes | Domain modeling | Moroccan realism |
| SOC/payload sensitivity flipping site cardinality | Yes (Task 08) | Empirical finding | Publishable **conditional** result |
| q=10 false discrete infeasibility corrupting feasibility labels | Yes (H80 CM diagnosis) | **Methods-relevant symptom** | Motivates contribution candidate below |
| Proven continuous optimality certificates from adaptive q | **No** | Would be strong if proved | Not available |
| General B&B speedup | **No** (enum faster on small budgets) | Must not claim | Honest audit already written |

---

## 3. Candidate contribution (falsifiable)

### Working title

**Certification-aware adaptive battery-energy resolution for refrigerated eHDT infrastructure planning with operating-scenario recourse**  
— *diagnostic / refinement protocol*, not a continuous-optimality theorem.

### Motivation already in-repo (not tuned)

Volvo FH Electric, 15 t, SOC 80%, Casablanca→Marrakech:

| Discrete quantum | Continuous shortest | MRLS (Ball) | Class |
| --- | --- | --- | --- |
| q = 10 kWh | feasible | INFEASIBLE | `discrete_grid_reject` |
| q = 5 kWh | feasible | OPTIMAL (even with no sites) | served |

If a planner trusted q=10 alone, they could incorrectly conclude that infrastructure (or vehicle capability) fails, when the failure is **numerical**. That can corrupt **charger-placement** decisions if discrete infeasibility is treated as physical need for sites.

### What would be claimed (strict)

1. Separate **numerical discretization error** from true physical / operational uncertainty (SOC, payload, weather, refrigeration, motor assumption).
2. Provide a **certification-aware refinement rule**: a site-set decision is not allowed to rest on an unresolved or grid-rejected mission without a finer-q (or continuous) diagnostic.
3. Show, on Moroccan Case A/B portfolios, whether refinement **changes the optimal installed site set / min site count**, not merely a routing label.
4. Report compute cost honestly (extra MRLS calls / wall time).

### What would **not** be claimed unless proved later

- Continuous global optimality of the adaptive scheme.
- Dominance over Vidotte Plaza et al. on HOS-integrated siting.
- General asymptotic superiority of B&B vs enumeration.
- That adaptive q “solves” peak-motor or SOC-floor physical failures (it does not — see CA peak_motor / MA soc_floor).

### Existing software support

The current MRLS + B&B + continuous replay stack **can** support this as a **diagnostic/refinement wrapper** around `energy_quantum_kwh` without rebuilding solvers. A full certified adaptive state-space algorithm with proved bounds is **out of scope** unless a separate proof workstream succeeds.

---

## 4. GO / NO-GO ruling for PASS 2

### Ruling: **CONDITIONAL GO** for a diagnostic contribution; **NO-GO** for a theorem-level “certified adaptive optimizer” claim

| Path | Decision |
| --- | --- |
| Paper framed as Moroccan refrigerated eHDT case study + honest discretization caveats | Always available (fallback) |
| Methods claim: certification-aware q-refinement that changes infrastructure decisions | **CONDITIONAL GO** |
| Methods claim: continuous-optimal adaptive resolution algorithm | **NO-GO** until proof exists |

### PASS 2 falsification tests (must all be run if pursuing CONDITIONAL GO)

1. On **northbound Case A** (after freight correction) and southbound Case B: compare fixed q=10, fixed q=5, and refinement protocol.
2. Record whether **min sites / optimal site set** change under refinement.
3. Compare against continuous diagnostic (no-charge / with-charge) without using successful replay to “prove” physically failed missions.
4. If refinement **never** changes infrastructure decisions (only orphan routing labels), novelty for **infrastructure planning** fails → fall back to case-study framing; document NO-GO upgrade.
5. If refinement changes decisions, state the contribution as **diagnostic/refinement with certification hygiene**, cite Vidotte Plaza as complementary (HOS/time-expanded) rather than “beaten.”

### Explicit NO-GO triggers (abort methods claim)

- Inventing continuous certificates without proof.
- Marketing B&B speedups contradicted by cold-cache timings.
- Tuning q, power, or UA to restore a preferred one-vs-two narrative.
- Claiming Moroccan investment optimality from illustrative CAPEX.

---

## 5. Recommended paper architecture (if CONDITIONAL GO passes)

1. **Moroccan problem realism** — Case A northbound agricultural refrigerated freight; Case B southbound distribution; legal `gross_mass_within_limit_axle_unverified`; directional ADM candidates.
2. **Finite energy–time model** with refrigeration + DEM (assumptions graded).
3. **Method contribution** — certification-aware discrete-energy refinement preventing infrastructure decisions based on coarse-grid false infeasibility; operating-scenario recourse (SOC/payload/refrigeration).
4. **Results** — site-set sensitivity; agreement enum↔B&B; continuous/discrete separation table.
5. **Limitations** — no Tanger Med OD; missing reverse Amskroud; axle unverified; no operator GPS yet; economics class A/B/C.

If CONDITIONAL GO fails falsification tests: publish as a high-integrity Moroccan prospective case study with methodological caveats — still valuable, but **not** a methods breakthrough paper.

---

## 6. Acceptance (Gate 5)

| Requirement | Status |
| --- | --- |
| Specific falsifiable contribution stated | Yes — certification-aware q-refinement for infrastructure decisions |
| Or explicit novelty NO-GO | Partial — theorem-level adaptive certification is NO-GO; diagnostic path is CONDITIONAL GO |
| Comparison plan vs fixed q and continuous diagnostic | Specified for PASS 2 |
| No unproved continuous optimality | Affirmed |

**Do not start large methodological coding until this ruling is independently reviewed.**
