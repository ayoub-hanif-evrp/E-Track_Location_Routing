# Single-duty HOS policy (Path A)

## Scope

Conservative **single duty period** screen for Moroccan professional-driver
working-time rules (décret 2-10-314 family, as commonly summarized):

| Resource | Rule in search + audit | Overnight Art.16 |
|----------|------------------------|------------------|
| Continuous driving | ≤ 4.5 h then ≥ 45 min qualifying break | n/a |
| Qualifying break | Consecutive **CHARGE + WAIT** at the same rest node accumulate | n/a |
| Daily driving | ≤ 9 h (Art.17) hard resource | **no reset** |
| Daily rest ≥ 12 h / 24 h (Art.16) | Not implemented; elapsed-duty screen uses **journey ≥ 24 h** (`daily_rest_horizon_min=1440`) consistent with the Art.16 24 h period — not a 12 h journey cutoff | Missions requiring overnight rest → `MULTI_DAY_OUT_OF_SCOPE` |

## Charging-break eligibility

Charging time counts toward a qualifying break only when the driver can take an
uninterrupted stationary break at a suitable stop (ADM/service-area rest node).
Search and schedule audit both aggregate consecutive CHARGE+WAIT blocks
(unit-tested 20 min + 25 min case).

## Served counts

`operationally_served` requires OPTIMAL ops solve + physical/discrete replay +
schedule audit + daily driving OK + `duty_scope != MULTI_DAY_OUT_OF_SCOPE`.
`LIMIT_REACHED` is never counted as served and is never equated to INFEASIBLE.
