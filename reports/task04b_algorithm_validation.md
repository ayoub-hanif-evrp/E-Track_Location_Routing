# Task 04B — Algorithm validation

Artifacts: `results/branch_bound_comparison.csv` (32 Morocco scenarios + 2 synthetic budgets), unit tests under `tests/unit/test_branch_and_bound.py`, `test_placement_bounds.py`, `test_placement_certification.py`.

## Stage 1 — Certification / structural vs Task 04A

- Full-profile terrain fingerprint (`04b.1`): interior elevation mutation changes hash and drive-table fingerprint (unit test).
- Global optimality: enumeration/B&B emit `optimality_status`; unresolved competitors block `CERTIFIED_OPTIMAL`.
- Serviceability probe under full direction-compatible installs: structural reporting = `peak_motor` only.
- **`M_struct_dem_AC` remains `peak_motor`** (unchanged vs Task 04A structural set). Objectives/subsets for the 32 scenarios match the Task 04A optima CSV under the stricter labels.

## Morocco pilot — 32-scenario match

All **32 / 32** demand × capex × price × {B0,B1,B2,Ball} B&B runs:

- `optimality_status = CERTIFIED_OPTIMAL`
- Coverage, secondary cost, and selected site set match Task 04A enumeration (strict tolerances)
- Structural ids: `M_struct_dem_AC` on every row

Representative search stats (default / equal / uniform):

| Budget | Nodes visited | Coverage prunes | Runtime (warm memo) |
|---|---:|---:|---:|
| B0 | 11 | 0 | ~3–4 s |
| B1 | 25 | 1 | ~2 s |
| B2 | 31 | 4 | ~1 s |
| Ball | 35 | 6 | ~0–1 s |

Coverage pruning appears once an incumbent is known; budget pruning fires when committed CAPEX exceeds the budget. Secondary pruning is rare on this five-site instance because variable-cost gaps are small relative to the CAPEX LB gap at coverage ties.

**Timing note:** Fair comparison vs full 32-subset enumeration should include shared DRIVE-table prep and MRLS memo fill. After one-time mission prep per demand scenario, B&B wall times above are dominated by MRLS calls on distinct active sets (≤32). No asymptotic speed claim beyond these measured numbers.

## Hand cases (unit tests)

- Single-site optimum; two sites jointly required; budget cut; equal coverage / lower OPEX
- Coverage prune; secondary LB prune path; `node_limit` ⇒ `LIMIT_REACHED` (not certified)
- Injected uncertified leaf ⇒ `INCUMBENT_UNPROVED` (cannot false-prove)

## Synthetic pruning demo (12 sites)

Config: `configs/optimization/branch_bound_benchmarks.yaml` — **synthetic**, not Moroccan traffic. Twelve independent O–Si–D missions; each needs its own station. Exhaustive reference still feasible (`2^12 = 4096`).

| Budget | Status | Match enum | Proved prunes | Nodes visited | B&B runtime |
|---|---|---|---:|---:|---:|
| B3 (CAPEX ≤ 300) | CERTIFIED_OPTIMAL | yes | **516** | 1271 | ~2 s |
| Ball | CERTIFIED_OPTIMAL | yes | 11 | 25 | ~0.1 s |

B3 demonstrates substantial **proved** coverage/budget pruning without losing the optimum (three cheapest sites). Ball installs all twelve sites for full coverage; the exclude branches prune quickly once a high-coverage incumbent exists.

## Honesty limits

- Fixed directed paths; no alternate corridors; no charger capacity/queues.
- Illustrative costs/weights; not market prices or certified HGV access.
- Novelty is not claimed without literature comparison (out of 04B scope).
