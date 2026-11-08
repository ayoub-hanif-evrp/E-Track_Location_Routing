# Task 04A — Charging-grid correction

## Problem

Task 03B Moroccan instances set

`aux_kwh_per_step = ceil(P_aux × Δt / 3.6e6)`.

With `P_aux = 2.5 kW` and `Δt = 5 min`, the physical load is `2.5 × 5/60 = 0.2083 kWh`, but the discrete model charged **1 kWh per step** (~12 kW). Refrigeration used the same per-step ceil.

After CHARGE with battery gain `ΔE` on the quantum lattice, stationary drain could leave

`E' = E + ΔE − steps × 1`

off the 5 kWh lattice (e.g. `ΔE=5`, `steps=1` → `E'=E+4`). State-dependent DRIVE tables are keyed only by quantum multiples, so the next DRIVE returned `drive_table_missing` (seen widely in full-charge heuristics).

## Correction

1. Store continuous loads `aux_w` and `tru_mean_w` on `RoutingInstance`.
2. Integrate drains over the **entire** CHARGE/WAIT duration (action-level Wh accounting).
3. Snap remaining energy with **floor onto the energy quantum** (never round remaining energy up).
4. Synthetic instances with watts unset keep integer `aux_kwh_per_step × steps` (A–J unchanged).

### Justification

Per-step `ceil` compounds: for `x ∈ (0,1)`, `ceil(x)·n ≫ ceil(n x)`. Action-level accumulation recovers the physical integral; flooring onto the quantum yields `E'_disc ≤ E_cont`, consistent with DRIVE-table conservatism (floor end energy, ceil time). Every accepted label satisfies `E % q = 0`.

### Hand example

`2.5 kW × 25 min = 1.0417 kWh` aux over 5 steps. Old model: 5 kWh. New model: 1.0417 kWh then floor net SOC onto the lattice.

## Continuous replay

Continuous replay uses the same Task 02B `apply_drive` kernel as table preprocessing and the same charger `P×η`, aux/TRU, and duration definitions as discrete CHARGE. It is a **numerical reconstruction**, not independent empirical validation against measured truck trips.

## Cache fingerprints

DRIVE-table cache files store a SHA-256 fingerprint over vehicle/fridge YAML, weather, terrain, macro edge sequence, GCM, grid settings, and `DRIVE_TABLE_CACHE_VERSION`. Stale fingerprints force rebuild.
