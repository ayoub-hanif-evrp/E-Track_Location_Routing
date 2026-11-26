# Infeasible-mission topology focus (Task 7.2)

Source: `results/paper_campaign/od_dem_site_audit.csv` rebuilt into
`od_candidate_accessibility_long.csv` / `infeasible_mission_topology_focus.csv`.

## Verified route-union accessibility

| OD | Directional stations on union | Notes |
|----|------------------------------|-------|
| `marrakech_agadir` | `amskroud_ca` | Benguerir/Settat **not** on this OD union |
| `agadir_casa` | `benguerir_ac`, `settat_ac` | Southbound CA sites **not** on northbound union |
| `casa_agadir` | `settat_ca`, `benguerir_ca`, `amskroud_ca` | Matched I1/I2 use Benguerir CA |

## Interpretation (pending operational solves)

- Remaining I2 infeasibles historically: `marrakech_agadir`, `agadir_casa`.
- Amskroud CA is topologically available on Marrakech→Agadir; failure under I2
  (Benguerir+Larache) is therefore **not** explained by missing Amskroud on the
  union — I2 simply does not install Amskroud.
- Agadir→Casablanca has AC-direction Benguerir/Settat on the union; I1/I2 install
  Benguerir **CA** (opposite carriageway), so directional mismatch is a primary
  hypothesis for Agadir→Casa remaining infeasible under I2.
- Direction-blind counterfactual matrices are labeled **non-executable**.

Targeted remedy evaluations (existing candidates / operating changes only) follow
in `experiments/infeasible_diagnosis/` after primary comparison completes.
