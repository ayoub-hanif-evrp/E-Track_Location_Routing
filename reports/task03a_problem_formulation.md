# Task 03A — Discrete multi-resource routing formulation

**Scope:** Lower-level multi-resource label-setting (MRLS) only. Active charging stations are **inputs**. No infrastructure placement, ALNS/GA/Gurobi/OR-Tools, or continuous charging optimality claims.

**Exactness:** Optimal for the **explicit finite discrete** problem on synthetic integer grids. Not exact for continuous charge amounts or continuous-time physics.

---

## 1. Decision variables

For a directed graph \(G=(V,A)\), origin \(o\), destination \(d\), active stations \(S\subseteq V\):

- Path as a sequence of DRIVE arcs (and optional WAIT/CHARGE actions at nodes).
- At each visit to \(s\in S\): discrete charge amount \(\Delta E \in \{0,1,2,\ldots\}\) (kWh quanta).
- Optional WAIT of \(k\in\{1,\ldots,W_{\max}\}\) time steps.

## 2. Objective (variable operating cost)

\[
\min J = \sum_{e\in\text{path}} c^{\mathrm{road}}_e + \sum_{\text{charges}} p_s\cdot E^{\mathrm{grid}}_{s}
\]

where \(E^{\mathrm{grid}}=\Delta E/\eta\) (plug energy). Infrastructure CapEx is **excluded**. Deadline and SOC floors are **constraints**.

## 3. Discrete resources

| Resource | Quantum | Symbol |
|---|---|---|
| Time | 5 min | \(t\in\mathbb{Z}_{\ge 0}\) |
| Tractor energy | 1 kWh | \(E^{\mathrm{tr}}\) |
| Trailer energy (config B) | 1 kWh | \(E^{\mathrm{tl}}\) |
| Cost | 1 cent | \(J\) |

Conversion: \(1\,\mathrm{kWh}=3.6\times 10^{6}\,\mathrm{J}\).

## 4. Label / state

\[
L=(v,\,t,\,E^{\mathrm{tr}},\,E^{\mathrm{tl}},\,J,\,\mathrm{pred},\,\mathrm{action})
\]

Feasibility after every transition: \(E^{\mathrm{tr}}\ge E^{\mathrm{tr}}_{\min}\), trailer floor if applicable, \(t\le T\), peak-motor OK on DRIVE, CHARGE only on active compatible stations.

## 5. Transitions

**DRIVE** \(u\to v\): apply arc table \((\Delta t,\Delta E^{\mathrm{tr}},\Delta E^{\mathrm{tl}},c^{\mathrm{road}},\mathrm{power\_ok})\).

**CHARGE** \(\Delta E\) at \(u\in S\): \(\Delta t=\lceil \Delta E/(P\eta)/\Delta t_{\mathrm{step}}\rceil\) steps; pay \(p\cdot\Delta E/\eta\); stationary aux (+ TRU) for \(\Delta t\). Trailer pack is **not** auto-recharged. **At most one CHARGE burst per node visit** (`can_charge` flag cleared after charging; restored on DRIVE arrival) to keep the discrete state space finite without consecutive re-charge cycles.

**WAIT** \(k\) steps: aux (+ TRU) only; \(k\ge 1\).

## 6. Dominance (conservative)

Same \((v,t)\): \(L\) dominates \(L'\) if \(J\le J'\), \(E^{\mathrm{tr}}\ge E^{\mathrm{tr}'}\), \(E^{\mathrm{tl}}\ge E^{\mathrm{tl}'}\) (when present), with ≥1 strict. **No** cross-time dominance (stationary TRU/aux).

Assumptions: deterministic arcs; non-negative electricity prices; more energy never hurts future cost/feasibility under this model.

## 7. Pseudocode

```
PQ ← {(0, L0 at origin)}
while PQ not empty:
  pop label L with least J (then t)
  if L.node = destination: return OPTIMAL reconstruction
  if dominated(L): continue
  for each successor action a in {DRIVE, CHARGE, WAIT}:
    L' ← transition(L, a)
    if infeasible(L'): continue
    if time/expansion limit: return LIMIT_REACHED
    if not dominated_by_store(L'): insert L'
return INFEASIBLE
```

Statuses: `OPTIMAL` | `INFEASIBLE` | `LIMIT_REACHED` (never confuse unfinished search with INFEASIBLE).

## 8. Worked example (Case A)

Graph: \(o \xrightarrow{e} d\) with \(\Delta t=2\), \(\Delta E^{\mathrm{tr}}=5\), \(c^{\mathrm{road}}=10\), power OK.  
\(E^{\mathrm{tr}}_0=100\), \(E^{\mathrm{tr}}_{\min}=10\), \(T=20\). No stations.

Only action: DRIVE → \(L_d=(d,2,95,\cdot,10)\). Optimal \(J^*=10\), path \(o\to d\), no charge.

## 9. Physics adapter

[`apply_drive`](src/morocco_etruck/energy/transitions.py) accepts incoming SOC (unlike `evaluate_route`, which resets to `soc_initial`). Synthetic benchmarks use **exact on-grid** arcs (no rounding). Continuous→grid (if used later) must be conservative and separately documented.

## 10. Complexity / limitations

State space grows with \(|V|\cdot T\cdot E_{\max}\cdot E_{\mathrm{trailer}}\). Dominance reduces labels but correctness requires the assumptions above. Not a claim of continuous global optimality.
