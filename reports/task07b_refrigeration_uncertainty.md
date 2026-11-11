# Task 07B — Refrigeration / thermal-load uncertainty

Documented UA / infiltration ranges only (`configs/energy/refrigeration_approx.yaml` + Task 07B ladder YAMLs). No invented TRU calibration. Infiltration 500 W is an **assumed** scenario.

## Energy breakdown (Casa→Agadir, chargers on, OPTIMAL cells)

| Vehicle | Terrain | Thermal | E_trac | E_refrig | E_regen | refrig/trac % | obj |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: |
| eactros_600 | dem | thermal_high | 590.9013626959703 | 3.878756698039648 | 40.999660062281215 | 0.66 | 53202.0 |
| eactros_600 | dem | thermal_infiltration_assumed | 590.9013626959703 | 4.050870166312568 | 40.999660062281215 | 0.69 | 53202.0 |
| eactros_600 | dem | thermal_low | 590.9013626959703 | 1.6161486241831864 | 40.999660062281215 | 0.27 | 53202.0 |
| eactros_600 | dem | thermal_nominal | 590.9013626959703 | 2.5858377986931007 | 40.999660062281215 | 0.44 | 53202.0 |
| eactros_600 | dem | thermal_off | 590.9013626959703 | 0.0 | 40.999660062281215 | 0.00 | 53202.0 |
| eactros_600 | dem | thermal_summer | 575.1129344725588 | 15.03364681685902 | 45.26128987243287 | 2.61 | 53002.0 |
| eactros_600 | flat | thermal_high | 525.7593079168229 | 3.830623579235967 | 0.0 | 0.73 | 52362.0 |
| eactros_600 | flat | thermal_infiltration_assumed | 525.7593079168229 | 4.001035401467037 | 0.0 | 0.76 | 52362.0 |
| eactros_600 | flat | thermal_low | 525.7593079168229 | 1.5960931580149855 | 0.0 | 0.30 | 52362.0 |
| eactros_600 | flat | thermal_nominal | 525.7593079168229 | 2.55374905282398 | 0.0 | 0.49 | 52362.0 |
| eactros_600 | flat | thermal_off | 525.7593079168229 | 0.0 | 0.0 | 0.00 | 52362.0 |
| eactros_600 | flat | thermal_summer | 503.2063879312656 | 14.864916964079116 | 0.0 | 2.95 | 52362.0 |
| volvo_475 | dem | thermal_high | 570.9222486834583 | 4.596026343562407 | 53.08930409643451 | 0.81 | 55553.0 |
| volvo_475 | dem | thermal_infiltration_assumed | 570.9222486834583 | 4.781272915928383 | 53.08930409643451 | 0.84 | 55553.0 |
| volvo_475 | dem | thermal_low | 570.9222486834583 | 1.9150109764843368 | 53.08930409643451 | 0.34 | 55553.0 |
| volvo_475 | dem | thermal_nominal | 570.9222486834583 | 3.0640175623749384 | 53.08930409643451 | 0.54 | 55553.0 |
| volvo_475 | dem | thermal_off | 570.9222486834583 | 0.0 | 53.08930409643451 | 0.00 | 55553.0 |
| volvo_475 | dem | thermal_summer | 561.227122312557 | 17.77987175066888 | 56.71614071241016 | 3.17 | 55553.0 |
| volvo_475 | flat | thermal_high | 528.5917162985385 | 3.92688981684333 | 0.0 | 0.74 | 53842.0 |
| volvo_475 | flat | thermal_infiltration_assumed | 528.5917162985385 | 4.1007049311580985 | 0.0 | 0.78 | 53842.0 |
| volvo_475 | flat | thermal_low | 528.5917162985385 | 1.636204090351387 | 0.0 | 0.31 | 53842.0 |
| volvo_475 | flat | thermal_nominal | 528.5917162985385 | 2.6179265445622217 | 0.0 | 0.50 | 53842.0 |
| volvo_475 | flat | thermal_off | 528.5917162985385 | 0.0 | 0.0 | 0.00 | 53842.0 |
| volvo_475 | flat | thermal_summer | 506.0387963129809 | 15.20237666963892 | 0.0 | 3.00 | 53842.0 |

## Refrigeration ON vs OFF (matched ablation)

| Vehicle | Thermal | obj | E_refrig | status |
| --- | --- | ---: | ---: | --- |
| eactros_600 | thermal_nominal | 52362.0 | 2.55374905282398 | OPTIMAL |
| eactros_600 | thermal_off | 52362.0 | 0.0 | OPTIMAL |
| volvo_475 | thermal_nominal | 53842.0 | 2.6179265445622217 | OPTIMAL |
| volvo_475 | thermal_off | 53842.0 | 0.0 | OPTIMAL |

## Interpretation

Across OPTIMAL CA cells above, refrigeration is **0.00–3.17%** of traction energy. If effects stay near ~1% of traction, q=10 may mask objective/charge differences — see discretization diagnostics at q=5.

Do **not** inflate TRU merely to force infrastructure change. Placement claim revalidation is in `task07b_infrastructure_robustness.md`.
