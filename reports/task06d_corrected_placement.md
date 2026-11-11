# Task 06D — Corrected placement (immutable GCM, enum + B&B)

> **Task 07A note:** The `refrigerated_06d` portfolio mixed ablation-OFF and hot-weather rows into demand (total weight 9.0). That coverage headline is **not** a primary scientific claim. Use `cold_chain_baseline_07a` (weight 5.5) in `reports/task07a_placement_robustness.md` / `results/task07a_placement.csv`. Legacy `default` portfolio below remains a historical diagnostic.

Artifact: `results/task06d_vehicle_placement.csv` (48 rows)  
q=10; `road_cost_per_km=100` ¢/km; unresolved_weight=0 on reported rows.

## A. Legacy `default` demand (revalidated under immutable GCM)

Equal absolute kWh inits (200/300) — diagnostic relative to equal-SOC refrigerated portfolio.

| Vehicle | B1 | B2 / Ball |
| --- | --- | --- |
| eActros | Settat, cov **5.0** | Settat, cov 5.0 |
| Volvo 475 / 460 | Settat, cov **3.0** | Settat+Benguerir, cov **5.0** |

Enum ≡ B&B site sets on all default rows (`enum_agreement=True`).  
→ The 06C placement hypothesis **survives GCM repair** for this legacy demand: Volvo needs two sites where eActros needs one to reach weight 5.

## B. Refrigerated `refrigerated_06d` (primary cold-chain reading)

Equal departure SOC 0.5; four refrigerated missions + one ablation; light GCM 25 t.

| Vehicle | B1 | B2 / Ball |
| --- | --- | --- |
| eActros | **Benguerir** (cov 7.5)* | Benguerir (cov 7.5)* |
| Volvo 475 / 460 | Settat (cov **4.0**) | Settat+Benguerir (cov **7.5**) |

\* **Alternate optima:** exhaustive enumeration finds Settat and Benguerir both achieve cov 7.5 at **identical** secondary cost for eActros B1. B&B returns Benguerir; enum’s lexicographic pick may return Settat. CSV `enum_agreement=False` flags site-set inequality under a cost tie — **not** an optimality certification failure (`CERTIFIED_OPTIMAL`, unresolved_weight=0).

### Does Volvo require more installed locations than eActros on equal freight missions?

**Yes, under both portfolios in this checkpoint:**

1. Legacy default: eActros covers full serviceable weight with Settat alone; Volvo needs Settat+Benguerir.
2. Refrigerated equal-SOC: Volvo Settat-only covers 4.0; needs two sites for 7.5. eActros reaches 7.5 with a single site (Settat **or** Benguerir).

Marrakech→Agadir at SOC 0.5 remains unserved for all vehicles even with all candidates — infrastructure conclusions must not pretend that OD is covered.

## Certification / replay

- `portfolio_optimality_status` now downgrades on `replay_invalid` / prep failures as well as `limit_reached`.
- Continuous replay required for served missions in evaluation path (unchanged).
- Full demand vs serviceable vs unresolved weights retained separately.

## Remaining uncertainties

Illustrative CAPEX/budgets; hypothetical chargers; assumed vehicle physics; q=10 only for placement (q=5 placement sensitivity not fully re-run in 06D); alternate optima under cost ties.
