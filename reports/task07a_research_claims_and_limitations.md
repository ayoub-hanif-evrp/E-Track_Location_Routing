# Task 07A — Research claims and limitations

## Claims supported (with qualifications)

1. **Demand design:** Primary cold-chain portfolio no longer double-counts ablation or hot twins. Total demand weight = 5.5.
2. **Equal-mass/payload vehicle routing (prior 06D, still valid):** Casa→Agadir full SOC no-charge remains eActros feasible / Volvo infeasible at equal 25 t and equal payload under the discrete research model.
3. **Infrastructure cardinality (revalidated on clean 07A portfolio):** Under illustrative weights, SOC 0.5, fixed payload 5300 kg, hypothetical 350 kW southbound sites, q=10 and q=5:
   - eActros reaches serviceable coverage **4.0** with **one** site (Settat **or** Benguerir — alternate optima).
   - Volvo 475/460 reaches coverage **2.0** with Settat alone and needs **Settat+Benguerir** for coverage **4.0**.
4. **Alternate optima** are reported explicitly; B&B/enumeration agree on objective.
5. **Refrigeration energy** is measured separately in continuous replay (~1.2 kWh drive TRU on Casa→Marrakech cool full-SOC none-charge cells); not inferred only from total cost.
6. Candidate sites are **`hypothetical_future_truck_site`** — future planning, not an operating 350 kW HGV network.

## Withdrawn / demoted

- Task 06D `refrigerated_06d` served 7.5/9.0 headline as a **defensible Moroccan coverage estimate** — **withdrawn** (ablation/hot inflation). Historical CSV retained; do not cite as primary.
- Naming Benguerir as the **unique** eActros one-site optimum — **withdrawn**; report the tie set.

## Limitations (do not paper over)

- Demand weights and ODs are illustrative, not observed Moroccan freight volumes.
- Config A TRU, Volvo curb/power/CdA assumptions; no measured trip validation.
- No verified 350 kW truck chargers, HGV legal access, or grid capacity at ADM sites.
- Marrakech→Agadir unserved at SOC 0.5 even with all candidates.
- Combining B&B with label-setting is **not** automatically novel (`reports/novelty_risks.md`).
- 8–12 site scalability deferred; three-site portfolio is a correctness benchmark.

## External evidence still needed

Real refrigerated journey logs; Volvo fleet energy/charge data; ADM/operator confirmation of truck access and electrical feasibility.
