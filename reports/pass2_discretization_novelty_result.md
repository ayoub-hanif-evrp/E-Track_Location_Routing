# PASS 2B — Discretization novelty result

## Prior art (brief)

- Vidotte Plaza et al. (2026) TR-C 105598: charger location + routing + HOS.
- Layered SoC / discretized battery-energy graphs (e.g. 2024 Networks-type EVSPP).
- Two-stage stochastic charging location-routing (e.g. 2026 Applied Energy family).

Therefore: retrying MRLS at q=5 after q=10 fails is **not** by itself a top-tier new optimization method. This PASS tests only a **diagnostic wrapper** that asks whether infrastructure decisions depend on coarse-grid false infeasibility.

## Protocol

A. Fixed q=10  B. Fixed q=5  C. Refine Ball evaluation to q=5 iff q=10 Ball is INFEASIBLE.

No continuous-optimality certificate is claimed.

## Results

| Scenario | Method | Ball status | Served | Min sites (Ball) | Best sites | False-neg? |
| --- | --- | --- | --- | ---: | --- | --- |
| northbound_A80_tomato | fixed_q10 | INFEASIBLE | False | 0 | NONE | nan |
| northbound_A80_tomato | fixed_q5 | INFEASIBLE | False | 0 | NONE | nan |
| northbound_A80_tomato | targeted_refinement | INFEASIBLE | False | 0 | NONE | False |
| southbound_H80_task08_portfolio | fixed_q10 | INFEASIBLE | False | 0 | NONE | nan |
| southbound_H80_task08_portfolio | fixed_q5 | OPTIMAL | True | 0 | NONE | nan |
| southbound_H80_task08_portfolio | targeted_refinement | OPTIMAL | True | 0 | NONE | True |

## Infrastructure decision changes (q=10 vs q=5)

- **northbound_A80_tomato**: decision_changed=False — both grids remain coverage 0 (physical/model peak-motor limited; refinement does not help).
- **southbound_H80_task08_portfolio**: decision_changed=True — Ball **serviceable coverage** jumps from **0.0 (q=10)** to **2.0 (q=5)** with **zero installed sites**. Min site count stays 0, but the planner’s feasibility/coverage conclusion changes: coarse grid falsely suggests the portfolio is unserved even with all candidates, while fine grid serves weight 2.0 with no new charger.

## Novelty GO / NO-GO (PASS 2B)

**CONDITIONAL_DIAGNOSTIC_ONLY** — evidence that coarse-grid false infeasibility can corrupt **coverage / serviceability** conclusions used in infrastructure planning hygiene.

**Not established:** a new top-tier adaptive optimization algorithm; continuous global optimality; superiority vs Vidotte Plaza et al. (2026) or layered-SoC / stochastic LRP literature.

**Manuscript implication:** treat certification-aware q-diagnostics as a **methods hygiene contribution** nested inside a Moroccan case study — or omit a standalone methods claim if reviewers demand theorem-level novelty.

`novelty_decision: CONDITIONAL_DIAGNOSTIC_ONLY`


## Reproduction

```bash
python scripts/run_pass2b_discretization_refinement.py
```

CSV: `results/pass2_refinement_comparison.csv`
