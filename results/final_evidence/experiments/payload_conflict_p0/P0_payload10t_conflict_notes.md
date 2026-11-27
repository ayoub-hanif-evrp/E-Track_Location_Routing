# P0 — Payload 10 t conflict reconciliation

## Mission
eActros 600 · Casa–Agadir · 10 000 kg · 50% SOC · Benguerir CA · q=2 kWh

## Observed disagreement
- Historical P6: status=OPTIMAL, ops=True, drive=339.72 min, charge=75.0, min_soc=0.1143
- Journal P4: status=INFEASIBLE, energy=OPTIMAL, ops=False

## Controlled re-runs (current code)
- **With** `_patch_realistic_speed_policy` (adapt_peak=True): status=OPTIMAL ops=True drive=339.7168811843433 disc5≈370.0 adapt_peak=True
- **Without** speed patch: status=INFEASIBLE energy=OPTIMAL ops=False drive=None disc5≈nan adapt_peak=False

## Verdict
DISCREPANCY RESOLVED: different **effective speed-policy preparation**. Primary/P6 protocol applies `_patch_realistic_speed_policy` (adapt_speed_to_peak_power=True with min adapt floor). Journal P4 `_eval_row` omitted this patch, yielding energy-feasible but operationally infeasible HOS outcomes under slower/unadapted climb speeds and/or different drive-time discretization. **Authoritative result for Path A:** P6 / speed-patched OPTIMAL (drive≈339.72 min, charge=75.0 min, min_soc≈0.1143). Journal heavier-payload INFEASIBLE rows that omitted the patch are **not** scientifically comparable and must be regenerated or labeled invalid.

## Scientific rule
Do not prefer the higher-feasibility number. Use the **matched primary protocol** (realistic speed patch + tomato fridge + cool weather + q=2) for payload frontiers.
