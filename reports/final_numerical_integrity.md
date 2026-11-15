# Final numerical integrity

## A1. Action-exact rounding audit

`drive_path_floor_loss` (path-node walk) is **SUPERSEDED**. Authoritative audit: `audit_solved_actions_exact` on the exact ordered DRIVE/CHARGE/WAIT list with exact `arc_id` resolution.

| q | OPTIMAL | DRIVE actions | Floor loss kWh | Cap trunc | Zero-net charges | Audit OK |
| --- | --- | ---: | ---: | ---: | ---: | --- |
| 5 | OPTIMAL | 25 | 94.45378870300519 | 0.0 | 0 | True |
| 2 | OPTIMAL | 25 | 30.111524470292444 | 0.0 | 0 | True |
| 1 | OPTIMAL | 25 | 14.111524470292935 | 0.0 | 0 | True |

## A2. Microsegment minimum SOC

Published `auth_min_soc` is the minimum over every DRIVE microsegment, CHARGE and WAIT endpoints (not macro ends alone).

| q | Min SOC | At action | Distance m | Arrival SOC |
| --- | ---: | --- | ---: | ---: |
| 5 | 0.23520050539025267 | DRIVE_MICRO:c04b2d73938a2ddb | 281863.40939955413 | 0.2574229811716773 |
| 2 | 0.15018587411715528 | DRIVE_MICRO:2a5a3a9310417960 | 429153.1630234299 | 0.15018587411715528 |
| 1 | 0.12351920745048853 | DRIVE_MICRO:2a5a3a9310417960 | 429153.1630234299 | 0.12351920745048853 |

## Reproduction

```bash
python scripts/run_final_numerical_integrity.py
pytest -q tests/unit/test_action_rounding_and_min_soc.py
```

Vehicle sha16=f703c0c4ede002cd
