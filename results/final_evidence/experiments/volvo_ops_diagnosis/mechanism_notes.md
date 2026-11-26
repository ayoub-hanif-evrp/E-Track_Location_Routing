# Volvo Marrakech→Agadir operational infeasibility

Primary records: energy-only status OPTIMAL under I0/I1/I2 at 80% SOC,
but operational status INFEASIBLE with `hos_ok=False` and
`daily_driving_ok=False`.

Mechanism (evidence-backed): **daily driving limit** in the HOS-in-search
operational layer — not energy reachability, not Benguerir CA absence alone.
Infrastructure changes do not restore operational serviceability when the
binding constraint is continuous/daily driving compliance on this OD.

Modeled policy uses the campaign's single-duty HOS screen; this is not a full
multi-day Art. 16 compliance certificate.
