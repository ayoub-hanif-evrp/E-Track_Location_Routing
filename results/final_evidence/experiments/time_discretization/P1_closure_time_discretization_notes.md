# P1 — Time-discretization closure (224+ panel)

## Baseline preserved

Authoritative headline coverage remains the **5-minute** HOS-in-search panel
(`R-T02_infrastructure_coverage.csv` / `primary_i0_i3_summary.csv`).
Do **not** mix refined `ts2`/`ts1` counts into that table without an explicit label.

## Screen extension

`affected_case_inventory_224plus.csv` screens continuous-driving **segments between
qualifying breaks**, not only total mission drive:

- Primary I0–I3 panel segments
- Volvo Settat–Benguerir 56-cell comparison segments
- Relevant payload / robustness rows where traces exist

## Matched refined reevaluation (`R-T14c_refined_time_matched_reevals.csv`)

Protocol: same vehicle, OD, SOC, infrastructure, payload, speed patch, q=2;
only `time_step_min` ∈ {5, 2, 1} changes (deadline wall-clock held at 20 h).

### Volvo Marrakech→Agadir @ 80% — all I0–I3

| ts (min) | Physical drive (min) | Discrete drive (typ.) | Ops status |
|---:|---:|---:|---|
| 5 | 265.62 | 285 | INFEASIBLE (all I0–I3) |
| 2 | 265.62 | 270 | OPTIMAL (all I0–I3) |
| 1 | 265.62 | 268 | OPTIMAL (all I0–I3) |

**Interpretation (verified numerical):** exclusion at ts=5 is **ceil-inflation** under
HOS continuous-driving limits, not a physical exceedance of 4.5 h driving.

### eActros Casablanca→Tangier — I2 / I3, both SOC scenarios

Where OPTIMAL at ts=5:

- Wait **35 min** + charge **10 min** ⇒ **45 min** qualifying stationary block.
- At ts=2: wait **34 min** + charge **10 min** (still ≈45 min break).
- Physical drive ≈266.15 min < 270.

**Interpretation:** the waiting period is **predominantly a physical HOS break**
requirement (complete 45 min with partial charge), not a pure discretization artifact.
Finer grids shave ~1 min of wait; they do **not** eliminate waiting.

At ts=1 some cells return `LIMIT_REACHED` (expansion/time budget), which is **not**
equivalent to energy/HOS infeasibility — do not merge with `INFEASIBLE`.

### Settat–Benguerir

The 56-cell Volvo coverage preference at **ts=5** is unchanged by this screen
(see `P4_paired_efficiency_notes.md`). Refined-ts flips on **other** cells must stay
labeled separately.

## Reporting rule

| Artifact | Time policy |
|---|---|
| `R-T02` / R-Figure 1 | Baseline **ts=5 only** |
| `R-T14c` / this note | Matched refined panel; every row declares `time_step_min` |
