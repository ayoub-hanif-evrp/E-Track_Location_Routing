# PAPER_RESULTS_SPRINT_01b

Git SHA (base): `ce956e601eb11ab6fa2175266acf1f3846d40a90` (sprint edits uncommitted)  
Closes the prioritized gaps from sprint 01. **Not** publication-ready.

## 1. Reserve-SOC policy (northbound Agadir→Casablanca, SOC₀=0.8)

Policy scenarios only — **not** manufacturer warranty or legal requirements. Each reserve rebuilds the vehicle `soc_min` so discrete labels and continuous microsegment floors match.

| Reserve | none | Benguerir | Settat | both | Ball optimal sets |
|---:|---|---|---|---|---|
| 10% | unserved | **served** (min SOC ≈0.235) | unserved | served | `y_benguerir_ac` |
| 15% | unserved | unserved | unserved | unserved | `NONE` (coverage 0) |
| 20% | unserved | unserved | unserved | unserved | `NONE` (coverage 0) |

**Result:** under this refrigerated northbound proxy, raising the operating reserve from 10% to 15% eliminates serviceability even with both candidate sites. That is a strong robustness / margin finding (H4), not a claim that 15% is legally required.

Artifact: `results/paper_results_reserve_soc.csv`

## 2. Baseline C — fixed shortest + deterministic min-charge

Added as `baseline_id=C` in `results/paper_results_matched_baselines.csv`.

| Family | Finding |
|---|---|
| H1 southbound (Casa→Marrakech / Agadir, chargers on) | C **INFEASIBLE** whenever B (MRLS fixed) is infeasible — det min-charge cannot rescue the shortest mask |
| Northbound SOC 0.8 / 1.0 | C **OPTIMAL** with Benguerir or both; **INFEASIBLE** with no sites |

So the A–E set is now populated as: A/B fixed-mask methods, **C** det min-charge, **D** multi-route, **E** joint enum (+ greedy B1).

## 3. H1 failure diagnosis (genuine route-flexibility mechanism)

Same physical graph + `allowed_arc_ids`. Detour vs shortest CSV length:

| OD | Truck | q | Fixed-fail class | Gain mechanism | Detour |
|---|---|---:|---|---|---:|
| casa_marrakech | eactros / volvo | 5,2 | **no_charger_on_shortest** | multi reaches off-shortest chargers (charges at `settat_ca`) | ≈1.088 |
| casa_agadir | volvo | 5,2 | energy_before_reaching_charger | **route_choice_different_roads** (chargers exist on shortest, but path still fails; multi uses non-shortest arcs) | ≈1.034 |

**Interpretation:** Casa→Marrakech H1 is primarily a **charger-access / path-alignment** effect: the verified shortest distance path does not visit the active station nodes, so fixed-mask routing cannot charge; multi-route detours (~8.8%) to reach Settat. Casa→Agadir H1 is a **road-choice / energy** effect with ~3.4% detour even though chargers lie on the shortest topology.

Artifact: `results/paper_results_h1_failure_diagnosis.csv`

## 4. Metric hygiene — enum ↔ B&B + input hashes

| Demand | Budget | Enum pick | B&B pick | Agree | All equivalent optima |
|---|---|---|---|---|---|
| SOC0.8 | B1 / Ball | Benguerir | Benguerir | True | `{Benguerir}` |
| SOC1.0 | B1 / Ball | Settat | Benguerir | False* | `{Benguerir, Settat}` |

\*Disagreement is only on which equivalent optimum is returned as the incumbent; both methods certify coverage 1.0 and both sites appear in `all_optimal_site_sets`. Input SHA16s recorded for vehicle / fridge / placement config.

Artifact: `results/paper_results_metric_hygiene.csv`

## Updated hypothesis notes

- **H1:** mechanism now evidenced (charger access vs road choice), not only feasibility flip.
- **H4:** reserve 10%→15% is a hard feasibility cliff on the primary northbound cell.
- **H2:** SOC1.0 enum/B&B incumbent difference illustrates multiple optima; greedy/enum agreement remains limited to this 2-site universe.

## Reproduction

```bash
python scripts/run_paper_results_sprint_01b.py --phase all
# or: reserve | h1 | northbound_c | hygiene | report
```

## Artifacts

- `results/paper_results_reserve_soc.csv`
- `results/paper_results_h1_failure_diagnosis.csv`
- `results/paper_results_metric_hygiene.csv`
- `results/paper_results_matched_baselines.csv` (includes baseline C)
- `reports/PAPER_RESULTS_SPRINT_01b.md`
