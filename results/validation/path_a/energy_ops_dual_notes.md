# Energy vs ops dual (Path A Gate 0.3)

`evaluate_mission_operational(..., include_energy_only=True)` runs a true
`hos_in_search=False` solve for energy coverage, then a separate HOS-on solve
for `operationally_served`.

Authoritative cells with energy ≠ ops: **2**

- B1 B_baseline_none: energy=10/14 ops=9/14
- B2 B_baseline_none: energy=10/14 ops=9/14

Toy unit proof that energy-only can succeed when HOS blocks:
`tests/unit/test_hos_in_search.py::test_energy_only_can_succeed_when_hos_blocks`.

Table: `results/validation/path_a/energy_ops_dual_check.csv`
