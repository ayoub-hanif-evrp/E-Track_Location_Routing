# Final methodology and baseline evaluation

**Status:** publication scaffolding (honest scope)  
**Review anchor:** repository integrity ledger and Task 07B--08 baseline  
**Date:** TBD_FROM_CSV (regenerate tables before citation)

---

## 1. What this work is

This repository supports a **Moroccan motorway corridor case study** on whether **charging-infrastructure placement decisions** remain stable when a finite battery-energy discretization, peak-power speed adaptation, DEM-assisted traction demand, and illustrative refrigerated auxiliary load are varied together. The primary scientific question is **decision reliability under numerical and physical uncertainty**, not a claim of a new joint siting-and-routing paradigm.

The flagship directional narrative is **northbound agricultural refrigerated freight** (Agadir$\rightarrow$Casablanca), motivated by external Moroccan export logistics context, with a firm-ripe tomato cold-chain proxy. Southbound portfolios remain **separate domestic-distribution scenarios** and must not be presented as representative of national refrigerated flows.

---

## 2. Methodological contribution (defensible)

| Element | Claim level | Notes |
| --- | --- | --- |
| Framework separating **discrete-grid rejection** from **physical infeasibility** | **Primary methods framing** | Documented via $q$-panels, continuous DRIVE/CHARGE/WAIT replay, and explicit status labels |
| **Conservative flooring** quantization policy retained | Engineering choice with quantified loss | Not marketed as novel continuous algorithm; see `quantization_audit.py` |
| **Certification-aware** B&B pruning fix (budget vs routing resolved) | Correctness patch on synthetic + Moroccan enum checks | `reports/bb_relaxed_bound_certification.md` |
| Same-graph **multi-route nesting** (`allowed_arc_ids`) | Validity fix for baseline comparisons | Prevents cross-graph confounding |
| Continuous replay as **diagnostic**, not optimality certificate | Explicit limitation | Label: **SIMULATION_REPLAY_VALIDATED** |

**Not claimed:** adaptive $q$ refinement with proved continuous global optimality; general superiority of branch-and-bound over enumeration; novelty of multi-resource label setting (MRLS) for state-of-charge routing; novelty of joint location and routing relative to Vidotte Plaza et al.\ (2026, DOI [10.1016/j.trc.2026.105598](https://doi.org/10.1016/j.trc.2026.105598)).

---

## 3. Solver stack (descriptive)

1. **Upper level:** exhaustive enumeration or branch-and-bound over binary site-install decisions under a site budget, with coverage and normalized illustrative cost as objectives (coverage primary).
2. **Lower level:** finite-horizon **MRLS** on a directed path-union decision graph with DRIVE, CHARGE, and WAIT resources, optional multi-route selection, and installation-conditioned charger availability.
3. **Post hoc:** **continuous replay** of discrete solutions on the same geometry and DEM macros to detect trace breaks and quantization-induced optimism/pessimism.

B\&B is **not** positioned as a generally faster solver. Task 08 synthetic eight-site benchmarks show **instance-dependent** wall times: enumeration can beat B\&B on some budget classes after the relaxed-bound fix; the inverse holds on others. Report both; do not cherry-pick.

---

## 4. Baseline ladder (fair comparison intent)

Baselines follow the Task 07B--07C manifest (`reports/task07b_07a_baseline_manifest.md`, `reports/task07b_routing_baselines.md`):

| ID | Baseline | Role |
| --- | --- | --- |
| A | Shortest path, no en-route charging | Feasibility floor |
| B | Shortest path, fixed hypothetical installs | Routing-only with given infra |
| C | Fixed shortest, energy-feasible MRLS + chargers | Discrete routing without path choice |
| D | Multi-route MRLS with predefined installs | Path flexibility without siting |
| E | Joint B\&B--MRLS (enum cross-check) | Full finite model under stated budget |

Matched comparisons require **nested path unions**, identical vehicle YAML, and aligned charger power assumptions. Primary numeric outcomes: **TBD_FROM_CSV** (`results/task07c_matched_routing_baselines.csv`, `results/task07b_routing_baselines.csv`).

---

## 5. Known numerical instability exemplars (publishable symptoms)

- **$q=10$ false infeasibility** on served missions that become OPTIMAL at $q\in\{5,2,1\}$ on the **same physical graph** (canonical `max_alts=4` northbound panel; southbound H80 counterexample in convergence CSV).
- **Installation stability on fine grid:** for served northbound Agadir$\rightarrow$Casablanca eActros tomato runs, Ball optimum site set remains `{y_benguerir_ac}` for $q\in\{5,2,1\}$ with the **same 25-arc DRIVE sequence** (`audit_ok=True` in `results/final_action_rounding_audit.csv`) --- **not** a claim that Benguerir is universally optimal across vehicles, directions, or portfolios.
- **Action-exact rounding audit (verified, commit pending):** authoritative replay distance **429.15 km** (COMPLETE, **SIMULATION_REPLAY_VALIDATED**); discrete charge labels **175 / 110 / 94 kWh** at $q\in\{5,2,1\}$; action-exact floor loss **94.45 / 30.11 / 14.11 kWh**. The $q=5\rightarrow1$ charge drop ($\approx$81 kWh) matches floor-loss drop ($\approx$80.3 kWh) --- grade **B+C** (discretization), not route change. Prior path-node cumulatives **42/14/7 kWh** are **SUPERSEDED**. Discrete charge totals remain **non-converged** as physical kWh estimates; microsegment $\min$ SOC (e.g.\ $\approx 0.235$ at $q=5$) supersedes path-node-only readings.

---

## 6. Physical uncertainty layers (non-numerical)

| Layer | Treatment | Evidence grade |
| --- | --- | --- |
| Peak-power motor limit + adaptive cruise | Speed caps from traction power | Manufacturer-labeled tractor + assumed trailer mass |
| DEM macros | COP-DEM GLO-30 along arcs | Open official raster; not field-grade grade measurement |
| Refrigerated auxiliary | UA ladder YAMLs | Inspired by Bank et al.\ (2025); **not** Moroccan TRU calibration |
| Hypothetical HGV chargers at ADM topology | Directional carriageway snaps | **Not** operating verified truck power at sites |
| Volvo continuous vs peak kW | Often **assumed** split | Unpublished OEM detail |

---

## 7. Reproducibility hooks

```bash
pytest -q tests/unit/test_quantization_error_and_charge.py tests/unit/test_branch_and_bound.py
python scripts/run_moroccan_energy_grid_convergence.py
python scripts/run_physical_trace_reconciliation.py
```

Regenerate all manuscript numbers from committed configs before submission. Crosswalk: `paper/claims_to_results_crosswalk.csv`.

---

## 8. Recommended paper positioning

- **Contribution:** certification-aware **reliability diagnostics** for infrastructure decisions under discrete energy representation and Moroccan corridor physics assumptions.
- **Contrast with Vidotte Plaza et al.\ (2026):** complementary --- they integrate HOS and time-expanded siting-routing at network scale; we stress **when finite discretization corrupts feasibility labels** on a DEM-refrigerated Moroccan pilot.
- **Contrast with Bank et al.\ (2025):** we borrow the **need for honest thermal uncertainty**, not their calibrated trailer twin.