# Task 07A — Placement robustness (clean cold-chain portfolio)

Artifact: `results/task07a_placement.csv` (60 rows)  
Demand total weight **5.5** (stable). Sites: `hypothetical_future_truck_site`.  
q=10 primary + ablation + hot; q=5 primary enroute. Objective agreement on all certified cells.

## Primary `cold_chain_baseline_07a` (SOC 0.5, fixed payload 5300 kg, cool, refrig ON)

### q=10 · enroute

| Vehicle | B1 | B2 / Ball | Max serviceable cov |
| --- | --- | --- | ---: |
| eActros 600 | **Settat or Benguerir** (tie), cov 4.0 | one-site tie, cov 4.0 | 4.0 |
| Volvo 475 / 460 | Settat only, cov **2.0** | **Settat+Benguerir**, cov **4.0** | 4.0 |

`all_optimal_site_sets` for eActros B1+: `y_benguerir_ca|y_settat_ca` (n=2). B&B returns Benguerir by deterministic tie-break; **not** unique.

Marrakech→Agadir (weight 1.5) remains `unserved_all_candidates` for all vehicles at SOC 0.5 → max coverage 4.0 of total 5.5. Unserved ≠ absent real demand.

### q=5 · enroute (50% SOC charging-constrained)

Same qualitative Volvo gap: Settat alone cov 2.0; Settat+Benguerir cov 4.0. eActros still reaches cov 4.0 with a one-site alternate-optima set. (eActros B0 shows cov 2.0 at q=5 vs 0.0 at q=10 — grid sensitivity on the no-install cell; does not remove the two-site Volvo gap.)

### Ablation OFF (matched weight 5.5)

Site pattern matches baseline for these cool flat cells (same B1/B2 structure). Refrigeration ON/OFF does not flip the infrastructure cardinality here; energy differences appear in the routing ablation CSV.

## Research baselines A–E (attribution note)

On this small portfolio, joint B&B–MRLS recovers the same exhaustive optima. Benefits of multi-route vs shortest, and of installing Settat/Benguerir, should not be attributed solely to “using B&B.” See `novelty_risks.md`.
