# Northbound revalidated feasibility (after speed/grade correction)

## Scope

- Primary: Agadir→Casablanca, firm-ripe tomato refrigeration, 5.3 t, SOC 0.8.
- Vehicles: Volvo FH Electric 475 kWh usable; eActros 600.
- Chargers: settat_ac, benguerir_ac only (no fabricated sites).
- q=10; path-union max_alts 2 and 4 where scheduled.

## Findings

- **A_fixed**: served 0/8 mission cases.
- **C_peak_adapt**: served 1/8 mission cases.
- **D_cont_adapt**: served 1/8 mission cases.
- **C_peak_adapt_floor60**: served 1/8 mission cases.

### Vehicle-specific outcome after peak-adapt

- **Volvo FH Electric (475 kWh usable, 400 kW peak=cont):** remains unserved for all tested install/alts/speed policies. Continuous probes clear peak-motor rejects, then hit `tractor_soc_floor` before candidate chargers; discrete MRLS cannot reach settat_ac/benguerir_ac with residual energy. **Not** a claim that Volvo cannot operate in Morocco — only that this DSM-grade + mass + charger-set model remains energy-limited.
- **eActros 600 (600 kWh usable, 600 kW peak / 400 kW continuous):** with `adapt_speed_to_peak_power` (and also continuous-adapt / floor-60 variants), **max_alts=2 + both candidates**, mission becomes OPTIMAL, discrete and continuous replay OK, charging ~240 kWh at `benguerir_ac`.
- Placement (eActros, peak-adapt, alts=2): B0 coverage 0; Ball coverage 1.0; optimal site set `{y_benguerir_ac}`; B&B ↔ enumeration agree (CERTIFIED_OPTIMAL).
- **max_alts=4 path-union:** eActros Ball cases revert to INFEASIBLE under the same speed policy — path-union expansion is material; do not claim robustness over larger alternative sets without re-certification.

### Limiting-cause classification

| Candidate cause | Volvo A80 | eActros A80 (alts=2) |
| --- | --- | --- |
| Fixed-speed peak motor | Dominant pre-correction | Dominant pre-correction |
| Peak-adapt gradeability | Cleared | Cleared |
| Battery range / SOC before chargers | **Still binding** | Relieved with benguerir charge |
| Station placement {settat,benguerir} | Unreachable ⇒ coverage 0 | Selects benguerir |
| Path-union 2 vs 4 | Still IF | Feasible only at alts=2 in this run |
| Fabricated early chargers | Not used | Not used |
| DSM grade / mass uncertainty | Material | Material |

Served rows in CSV: 3 (vehicles=['eactros_600']).

## Table excerpt

```
          policy_tag     vehicle  max_alts installed_mode mission_status  served     reason  adapt_flag_on_ctx  place_Ball_bb_coverage place_Ball_bb_enum_agree
             A_fixed   volvo_475         2           none     INFEASIBLE   False INFEASIBLE              False                     NaN                      NaN
             A_fixed   volvo_475         2           both     INFEASIBLE   False INFEASIBLE              False                     0.0                     True
             A_fixed   volvo_475         4           none     INFEASIBLE   False INFEASIBLE              False                     NaN                      NaN
             A_fixed   volvo_475         4           both     INFEASIBLE   False INFEASIBLE              False                     NaN                      NaN
        C_peak_adapt   volvo_475         2           none     INFEASIBLE   False INFEASIBLE               True                     NaN                      NaN
        C_peak_adapt   volvo_475         2           both     INFEASIBLE   False INFEASIBLE               True                     0.0                     True
        C_peak_adapt   volvo_475         4           none     INFEASIBLE   False INFEASIBLE               True                     NaN                      NaN
        C_peak_adapt   volvo_475         4           both     INFEASIBLE   False INFEASIBLE               True                     NaN                      NaN
        D_cont_adapt   volvo_475         2           none     INFEASIBLE   False INFEASIBLE               True                     NaN                      NaN
        D_cont_adapt   volvo_475         2           both     INFEASIBLE   False INFEASIBLE               True                     NaN                      NaN
        D_cont_adapt   volvo_475         4           none     INFEASIBLE   False INFEASIBLE               True                     NaN                      NaN
        D_cont_adapt   volvo_475         4           both     INFEASIBLE   False INFEASIBLE               True                     NaN                      NaN
C_peak_adapt_floor60   volvo_475         2           none     INFEASIBLE   False INFEASIBLE               True                     NaN                      NaN
C_peak_adapt_floor60   volvo_475         2           both     INFEASIBLE   False INFEASIBLE               True                     NaN                      NaN
C_peak_adapt_floor60   volvo_475         4           none     INFEASIBLE   False INFEASIBLE               True                     NaN                      NaN
C_peak_adapt_floor60   volvo_475         4           both     INFEASIBLE   False INFEASIBLE               True                     NaN                      NaN
             A_fixed eactros_600         2           none     INFEASIBLE   False INFEASIBLE              False                     NaN                      NaN
             A_fixed eactros_600         2           both     INFEASIBLE   False INFEASIBLE              False                     0.0                     True
             A_fixed eactros_600         4           none     INFEASIBLE   False INFEASIBLE              False                     NaN                      NaN
             A_fixed eactros_600         4           both     INFEASIBLE   False INFEASIBLE              False                     NaN                      NaN
        C_peak_adapt eactros_600         2           none     INFEASIBLE   False INFEASIBLE               True                     NaN                      NaN
        C_peak_adapt eactros_600         2           both        OPTIMAL    True        NaN               True                     1.0                     True
        C_peak_adapt eactros_600         4           none     INFEASIBLE   False INFEASIBLE               True                     NaN                      NaN
        C_peak_adapt eactros_600         4           both     INFEASIBLE   False INFEASIBLE               True                     NaN                      NaN
        D_cont_adapt eactros_600         2           none     INFEASIBLE   False INFEASIBLE               True                     NaN                      NaN
        D_cont_adapt eactros_600         2           both        OPTIMAL    True        NaN               True                     NaN                      NaN
        D_cont_adapt eactros_600         4           none     INFEASIBLE   False INFEASIBLE               True                     NaN                      NaN
        D_cont_adapt eactros_600         4           both     INFEASIBLE   False INFEASIBLE               True                     NaN                      NaN
C_peak_adapt_floor60 eactros_600         2           none     INFEASIBLE   False INFEASIBLE               True                     NaN                      NaN
C_peak_adapt_floor60 eactros_600         2           both        OPTIMAL    True        NaN               True                     NaN                      NaN
C_peak_adapt_floor60 eactros_600         4           none     INFEASIBLE   False INFEASIBLE               True                     NaN                      NaN
C_peak_adapt_floor60 eactros_600         4           both     INFEASIBLE   False INFEASIBLE               True                     NaN                      NaN
```

## Reproduction

```bash
python scripts/run_northbound_revalidated_feasibility.py
# optional smoke:
python scripts/run_northbound_revalidated_feasibility.py --quick
```

CSV: `results/northbound_revalidated_placement.csv`
