# Task 07B — Comparable routing baselines A–E

Same demand weight 5.5 freight definition (payload 5300 kg, SOC 0.5, cool, nominal thermal). Attribute gains separately: route freedom vs infrastructure vs vehicle vs refrigeration vs terrain vs q.

| ID | Meaning |
| --- | --- |
| A | Shortest-distance path, no chargers |
| B | Shortest-distance path, Settat+Benguerir |
| C | Fixed-route (shortest) energy-feasible MRLS + chargers |
| D | Multi-route MRLS, predefined installs |
| E | Joint B&B–MRLS (see placement robustness) |

Panel terrain used: **flat**.

| baseline | vehicle | od | install | status | obj | continuous_ok |
| --- | --- | --- | --- | --- | ---: | --- |
| A | eactros_600 | casa_agadir | none | INFEASIBLE | nan | False |
| A | eactros_600 | casa_marrakech | none | OPTIMAL | 23685.0 | True |
| A | eactros_600 | marrakech_agadir | none | INFEASIBLE | nan | False |
| A | volvo_475 | casa_agadir | none | INFEASIBLE | nan | False |
| A | volvo_475 | casa_marrakech | none | INFEASIBLE | nan | False |
| A | volvo_475 | marrakech_agadir | none | INFEASIBLE | nan | False |
| B | eactros_600 | casa_agadir | settat_benguerir | OPTIMAL | 51522.0 | True |
| B | eactros_600 | casa_marrakech | settat_benguerir | OPTIMAL | 23685.0 | True |
| B | eactros_600 | marrakech_agadir | settat_benguerir | INFEASIBLE | nan | False |
| B | volvo_475 | casa_agadir | settat_benguerir | OPTIMAL | 53002.0 | True |
| B | volvo_475 | casa_marrakech | settat_benguerir | INFEASIBLE | nan | False |
| B | volvo_475 | marrakech_agadir | settat_benguerir | INFEASIBLE | nan | False |
| C | eactros_600 | casa_agadir | settat_benguerir | OPTIMAL | 51522.0 | True |
| C | eactros_600 | casa_marrakech | settat_benguerir | OPTIMAL | 23685.0 | True |
| C | eactros_600 | marrakech_agadir | settat_benguerir | INFEASIBLE | nan | False |
| C | volvo_475 | casa_agadir | settat_benguerir | OPTIMAL | 53002.0 | True |
| C | volvo_475 | casa_marrakech | settat_benguerir | INFEASIBLE | nan | False |
| C | volvo_475 | marrakech_agadir | settat_benguerir | INFEASIBLE | nan | False |
| D_benguerir | eactros_600 | casa_agadir | benguerir_only | OPTIMAL | 52362.0 | True |
| D_benguerir | eactros_600 | casa_marrakech | benguerir_only | OPTIMAL | 27897.0 | True |
| D_benguerir | eactros_600 | marrakech_agadir | benguerir_only | INFEASIBLE | nan | False |
| D_benguerir | volvo_475 | casa_agadir | benguerir_only | INFEASIBLE | nan | False |
| D_benguerir | volvo_475 | casa_marrakech | benguerir_only | INFEASIBLE | nan | False |
| D_benguerir | volvo_475 | marrakech_agadir | benguerir_only | INFEASIBLE | nan | False |
| D_both | eactros_600 | casa_agadir | settat_benguerir | OPTIMAL | 52362.0 | True |
| D_both | eactros_600 | casa_marrakech | settat_benguerir | OPTIMAL | 27897.0 | True |
| D_both | eactros_600 | marrakech_agadir | settat_benguerir | INFEASIBLE | nan | False |
| D_both | volvo_475 | casa_agadir | settat_benguerir | OPTIMAL | 53842.0 | True |
| D_both | volvo_475 | casa_marrakech | settat_benguerir | OPTIMAL | 29157.0 | True |
| D_both | volvo_475 | marrakech_agadir | settat_benguerir | INFEASIBLE | nan | False |
| D_none | eactros_600 | casa_agadir | none | INFEASIBLE | nan | False |
| D_none | eactros_600 | casa_marrakech | none | INFEASIBLE | nan | False |
| D_none | eactros_600 | marrakech_agadir | none | INFEASIBLE | nan | False |
| D_none | volvo_475 | casa_agadir | none | INFEASIBLE | nan | False |
| D_none | volvo_475 | casa_marrakech | none | INFEASIBLE | nan | False |
| D_none | volvo_475 | marrakech_agadir | none | INFEASIBLE | nan | False |
| D_settat | eactros_600 | casa_agadir | settat_only | OPTIMAL | 52362.0 | True |
| D_settat | eactros_600 | casa_marrakech | settat_only | OPTIMAL | 27897.0 | True |
| D_settat | eactros_600 | marrakech_agadir | settat_only | INFEASIBLE | nan | False |
| D_settat | volvo_475 | casa_agadir | settat_only | INFEASIBLE | nan | False |
| D_settat | volvo_475 | casa_marrakech | settat_only | OPTIMAL | 29157.0 | True |
| D_settat | volvo_475 | marrakech_agadir | settat_only | INFEASIBLE | nan | False |

Never credit B&B for gains that come from extra chargers or extra paths alone — compare A/B/C/D before reading E.
