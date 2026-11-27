# Volvo Marrakech→Agadir operational infeasibility

## Corrected interpretation

Primary / baseline ops solves return `status=INFEASIBLE` with **no action trace**.
In that state, `hos_ok` and `daily_driving_ok` are **not evaluated** — they must not
be reported as False evidence of a daily-driving (Art. 17) violation.

Previous campaign text that named **daily driving** as the binding mechanism was
incorrect: it read the early-return default, not an audited HOS computation.

## Energy-only audit

- Energy status: `OPTIMAL`
- Energy-trace drive duration: **265.62 min**
- Energy-trace road distance: **283.25 km**
- Would pass 9 h daily-driving screen on energy trace: `True`
- Traction/aux/refrig/regen/charge kWh: 341.941491042316/11.06732413255675/0.6472853751090527/49.15167286709257/0.0

## Controlled ablations (I2 Benguerir CA + Larache RT)

Independently tested: continuous-driving relaxation, daily-driving relaxation,
both, expanded rest nodes, shortened break requirement, and HOS-in-search off.

## Binding mechanism

Binding mechanism (ablation evidence): continuous-driving / qualifying-break eligibility under HOS-in-search — not the Art.17 daily-driving limit. Ops restored by: expand_rest_nodes, relax_continuous_and_daily, relax_continuous_driving. Relaxing daily driving alone did not restore serviceability. Expanding eligible rest nodes also restores ops, consistent with a break-location / continuous-driving interaction rather than a pure daily-driving exceedance.

Modeled policy uses the campaign's single-duty HOS screen; this is not a full
multi-day Art. 16 compliance certificate.
