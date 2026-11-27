# Moroccan HOS policy screen (Path A) — source documentation

## Legal source

- Bulletin officiel No. 5878 bis (30 septembre 2010), Décret n° 2-10-314.
- https://www.sgg.gov.ma/BO/bo_fr/2010/bo_5878-bis_fr.pdf
- Section: « Dispositions relatives aux durées de conduite et de repos ».
- Check subsequent amendments before regulatory citation in a paper.

## Key articles (extracted wording, OCR-normalized)

**Art. 17** — Daily driving duration is the total cumulative effective driving between two mandatory rests over a 24-hour period counted from start of duty. (Campaign model uses a **9 h** daily-driving screen as the commonly applied Art. 17 limit.)

**Art. 18** — After **four and a half hours** of driving, the driver must take an **uninterrupted pause of at least forty-five minutes**, unless taking a rest. During the pause the driver may not drive or perform other tasks.

**Art. 19** — The Art. 18 pause may be replaced by pauses of **at least fifteen minutes each**, interleaved in or immediately after the driving period so that Art. 18 is respected.

**Art. 16 (daily rest)** — Daily rest of **at least 12 hours** (crew rules also reference 12 h within 30 h). Path A does **not** implement overnight daily-rest reset.

## Modeled policy vs law

| Rule | Law | Path A model |
|---|---|---|
| Continuous driving | 4.5 h then ≥45 min pause | Same limit; search uses discrete steps |
| Qualifying break | 45 min uninterrupted **or** split ≥15 min parts | **Conservative uninterrupted 45 min only** |
| Daily driving | Art. 17 cumulative daily | ≤ 9 h screen |
| Daily rest | ≥ 12 h | Out of scope / coarse gate — not a compliance proof |
| Charging as break | Pause requires relief from other work | Stationary CHARGE/WAIT at eligible nodes |

## Numerical interaction (P0 finding)

Drive arcs enter HOS via `ceil(dt_phys / time_step)` (`arc_preprocessing._ceil_time_steps`).
Limit defaults to `round(270 / time_step_min)` steps.

**Volvo Marrakech→Agadir @80% I2 (energy-optimal itinerary):**

| time_step_min | Physical drive (min) | Discrete ceil sum (min) | Ops served |
|---:|---:|---:|:---:|
| 5 | 265.62 | **285** | No |
| 2 | 265.62 | 270 | Yes |
| 1 | 265.62 | 268 | Yes |

Mechanism: **temporal ceil inflation**, not physical continuous-driving exceedance and not Art. 17 daily driving.
