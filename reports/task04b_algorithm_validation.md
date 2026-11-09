# Task 04B — Algorithm validation

Artifacts: `results/branch_bound_comparison.csv` (32 Morocco scenarios + 2 synthetic budgets), regenerated Task 04A CSVs (`results/location_enumeration.csv`, `results/location_optimal_solutions.csv`), unit tests under `tests/unit/test_branch_and_bound.py`, `test_placement_bounds.py`, `test_placement_certification.py`.

## Stage 1 — Certification / structural vs Task 04A

- Full-profile terrain fingerprint (`04b.1`): interior elevation mutation changes hash and drive-table fingerprint (unit test).
- Global optimality: enumeration/B&B emit `optimality_status`; unresolved competitors block `CERTIFIED_OPTIMAL`. Regenerated optima CSV: **32/32 `CERTIFIED_OPTIMAL`**.
- Serviceability probe under full direction-compatible installs. **Serviceable denominator** = missions with class `serviceable` only (not merely non-`peak_motor`). Structural reporting = `peak_motor` only.
- Taxonomy on the pilot portfolio: six missions `serviceable`, one `peak_motor` (`M_struct_dem_AC`). No `unserved_all_candidates` / `limit_reached` / `replay_invalid` on this instance.
- Objectives/coverage under the stricter labels match the prior 04A optima (same numeric coverage and secondary costs).

## Morocco pilot — 32-scenario match

All **32 / 32** demand × capex × price × {B0,B1,B2,Ball} B&B runs vs **regenerated** enumeration:

- `bb_status = enum_status = CERTIFIED_OPTIMAL`
- Coverage and secondary cost match within strict tolerances
- Structural ids: `M_struct_dem_AC` on every row

### Exact site set vs equal alternate optima

Lex optima are unique on coverage+secondary cost, but **not always unique on the site set**. When `sites_equal=False` and `alternate_optima=True`, B&B and enumeration return different installs with identical coverage and secondary cost (both certified).

Typical alternate pair under uniform prices at B2/Ball:

| Source | Sites | Coverage | Secondary |
|---|---|---:|---:|
| Enumeration (tie-break via subset scan order) | `y_benguerir_ca`, `y_settat_ac` | 9.0 | 183.3659… |
| B&B (DFS install-first order) | `y_benguerir_ca`, `y_benguerir_ac` | 9.0 | 183.3659… |

Both are optimal under the lex objective. The comparison CSV flags these with `alternate_optima=True`; `match=True` still holds because objectives agree.

Representative search stats (default / equal / uniform):

| Budget | Nodes visited | Coverage prunes | Budget prunes | Runtime (warm memo) |
|---|---:|---:|---:|---:|
| B0 | 11 | 0 | 5 | ~3 s |
| B1 | 25 | 1 | 9 | ~2 s |
| B2 | 31 | 4 | 8 | ~1 s |
| Ball | 35 | 6 | 0 | ~0–1 s |

Secondary pruning is rare on this five-site instance (variable-cost gaps are small relative to the CAPEX component of the secondary LB at coverage ties).

**Timing note:** Fair comparison vs full 32-subset enumeration should include shared DRIVE-table prep and MRLS memo fill. After one-time mission prep per demand scenario, B&B wall times above are dominated by MRLS calls on distinct active sets (≤32). No asymptotic speed claim beyond these measured numbers.

## Hand cases (unit tests)

- Single-site optimum; two sites jointly required; budget cut; equal coverage / lower OPEX
- Coverage prune; secondary LB prune path; `node_limit` ⇒ `LIMIT_REACHED` (not certified)
- Injected uncertified leaf ⇒ `INCUMBENT_UNPROVED` (cannot false-prove)
- Serviceable denominator excludes non-`serviceable` taxonomy classes

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
