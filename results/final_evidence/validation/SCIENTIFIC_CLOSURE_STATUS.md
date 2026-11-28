# Scientific closure status (final gates)

Baseline experimental depth: `4af9259e66b8db5537ca676ae7ab7012c81efd87`.  
Closure freeze: `84911fa83aa2bd7800e1402c98ab313544ef5116`.  
No manuscript writing; no geo/algorithm expansion.

| Gate | Status | Authoritative evidence |
|---|---|---|
| P0 10 t Casa–Agadir conflict | **RESOLVED** | Speed-policy patch mismatch; patched OPTIMAL matches P6 (`payload_conflict_p0/`) |
| P1 time discretization | **CLOSED** | 224+ screen; Volvo MA INF@5 / OPT@2,1 all I; Casa–Tangier wait 35→34 (mostly physical HOS) |
| P2 constant vs taper charging | **CLOSED** | 3 missions; Volvo discrete 45 vs 55 min; continuous offline table; R-Fig12 |
| P3 geometry / DEM | **CLOSED** | 45/45 itineraries; 0 missing geom; steep 23%/2.61 m documented |
| P4 Settat–Benguerir paired | **CLOSED** | Coverage ≠ efficiency; paired ties; SOC preference reverse @ ts5 |
| P5 release integrity | **PASSED** | LF writers; remanifest 328; read-only verify 0 failures; CI `release-manifest-verify` success on Ubuntu |
| P6 figures/tables package | **CLOSED** | Regenerated from authoritative CSVs (R-Fig1/3/5/12, R-T05/14/23/24) |

Executable validation: **ALL_PASSED** (36 checks).  
Manifest verify (local + CI Linux): **PASSED**.

Epistemic rule: do not force favorable results; label ts5 vs refined ts separately.
