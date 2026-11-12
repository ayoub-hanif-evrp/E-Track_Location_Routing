# Task 08 — SOC and payload robustness

Challenge: does eActros one-site vs Volvo two-site survive SOC 0.8/1.0 and 15 t cargo?

## Placement coverage (B1 / B2)

| Cell | SOC | Payload | Vehicle | B1 cov | B1 sites | B2 sites | agree |
| --- | ---: | ---: | --- | ---: | --- | --- | --- |
| S50 | 0.5 | 5300.0 | eactros_600 | 4.0 | y_benguerir_ca | y_benguerir_ca | True |
| S50 | 0.5 | 5300.0 | volvo_475 | 2.0 | y_settat_ca | y_benguerir_ca,y_settat_ca | True |
| S80 | 0.8 | 5300.0 | eactros_600 | 5.5 | y_benguerir_ca | y_benguerir_ca | True |
| S80 | 0.8 | 5300.0 | volvo_475 | 4.0 | y_benguerir_ca | y_benguerir_ca | True |
| S100 | 1.0 | 5300.0 | eactros_600 | 5.5 | y_benguerir_ca | y_benguerir_ca | True |
| S100 | 1.0 | 5300.0 | volvo_475 | 5.5 | y_benguerir_ca | y_benguerir_ca | True |
| H50 | 0.5 | 15000.0 | eactros_600 | 2.0 | y_settat_ca | y_benguerir_ca,y_settat_ca | True |
| H50 | 0.5 | 15000.0 | volvo_475 | 0.0 | nan | nan | True |
| H80 | 0.8 | 15000.0 | eactros_600 | 4.0 | y_benguerir_ca | y_benguerir_ca | True |
| H80 | 0.8 | 15000.0 | volvo_475 | 0.0 | nan | nan | True |

## Claim survival verdict

**Does not universally survive.** Changed cells:
- S80: eActros B1=5.5 B2=5.5; Volvo B1=4.0 B2=4.0
- S100: eActros B1=5.5 B2=5.5; Volvo B1=5.5 B2=5.5
- H50: eActros B1=2.0 B2=4.0; Volvo B1=0.0 B2=0.0
- H80: eActros B1=4.0 B2=4.0; Volvo B1=0.0 B2=0.0
Do not retune SOC/payload to restore the previous headline.

## Matched routing nesting classes

| Cell | Vehicle | OD | B | C | nesting_class |
| --- | --- | --- | --- | --- | --- |
| S50 | eactros_600 | casa_marrakech | INFEASIBLE | OPTIMAL | feasibility_gain_restricted_IF |
| S50 | eactros_600 | casa_agadir | OPTIMAL | OPTIMAL | positive_feasible_restricted |
| S50 | volvo_475 | casa_marrakech | INFEASIBLE | OPTIMAL | feasibility_gain_restricted_IF |
| S50 | volvo_475 | casa_agadir | INFEASIBLE | OPTIMAL | feasibility_gain_restricted_IF |
| S80 | eactros_600 | casa_marrakech | OPTIMAL | OPTIMAL | positive_feasible_restricted |
| S80 | eactros_600 | casa_agadir | OPTIMAL | OPTIMAL | positive_feasible_restricted |
| S80 | volvo_475 | casa_marrakech | OPTIMAL | OPTIMAL | positive_feasible_restricted |
| S80 | volvo_475 | casa_agadir | INFEASIBLE | OPTIMAL | feasibility_gain_restricted_IF |
| S100 | eactros_600 | casa_marrakech | OPTIMAL | OPTIMAL | positive_feasible_restricted |
| S100 | eactros_600 | casa_agadir | OPTIMAL | OPTIMAL | positive_feasible_restricted |
| S100 | volvo_475 | casa_marrakech | OPTIMAL | OPTIMAL | positive_feasible_restricted |
| S100 | volvo_475 | casa_agadir | INFEASIBLE | OPTIMAL | feasibility_gain_restricted_IF |
| H50 | eactros_600 | casa_marrakech | INFEASIBLE | OPTIMAL | feasibility_gain_restricted_IF |
| H50 | eactros_600 | casa_agadir | INFEASIBLE | OPTIMAL | feasibility_gain_restricted_IF |
| H50 | volvo_475 | casa_marrakech | INFEASIBLE | INFEASIBLE | vacuous_both_IF |
| H50 | volvo_475 | casa_agadir | INFEASIBLE | INFEASIBLE | vacuous_both_IF |
