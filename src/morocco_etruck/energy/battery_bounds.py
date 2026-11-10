"""Derive discrete tractor energy bounds from a vehicle pack (Task 06C)."""

from __future__ import annotations

import math

from morocco_etruck.energy.vehicle import VehicleParams


def floor_q(x: float, quantum: int) -> int:
    q = max(1, int(quantum))
    return int(math.floor(float(x) / q) * q)


def ceil_q(x: float, quantum: int) -> int:
    q = max(1, int(quantum))
    return int(math.ceil(float(x) / q) * q)


def derive_discrete_energy_bounds(
    vehicle: VehicleParams,
    *,
    energy_quantum_kwh: int,
    E_truck_init_kwh: float | None = None,
    soc_init: float | None = None,
) -> tuple[int, int, int, dict[str, str]]:
    """
    Return (E_min, E_init, E_cap) on the energy quantum grid.

    Never fabricates energy above usable capacity or below soc_min.
    Notes document conservative quantization when usable is not divisible by q.
    """
    q = max(1, int(energy_quantum_kwh))
    usable = float(vehicle.usable_kwh)
    notes: dict[str, str] = {
        "vehicle_id": vehicle.vehicle_id,
        "usable_kwh": str(usable),
        "quantum_kwh": str(q),
    }
    if usable <= 0:
        raise ValueError(f"usable_kwh must be > 0 for {vehicle.vehicle_id}")

    E_cap = floor_q(usable, q)
    if E_cap < usable - 1e-9:
        notes["capacity_quantize"] = (
            f"floor_q({usable})={E_cap} < usable; conservative discrete headroom loss"
        )
    E_min = ceil_q(float(vehicle.soc_min) * usable, q)
    if E_min > E_cap:
        raise ValueError(
            f"NUMERICAL_GRID_REJECT: E_min={E_min} > E_cap={E_cap} for {vehicle.vehicle_id}"
        )

    if E_truck_init_kwh is not None:
        init_raw = float(E_truck_init_kwh)
    elif soc_init is not None:
        init_raw = float(soc_init) * usable
    else:
        init_raw = float(vehicle.soc_initial) * usable

    if init_raw + 1e-9 < float(vehicle.soc_min) * usable:
        raise ValueError(
            f"INVALID_INPUT: init {init_raw} kWh below soc_min×usable "
            f"({vehicle.soc_min * usable}) for {vehicle.vehicle_id}"
        )
    if init_raw > usable + 1e-9:
        raise ValueError(
            f"INVALID_INPUT: init {init_raw} kWh > usable {usable} for {vehicle.vehicle_id}"
        )

    E_init = min(E_cap, floor_q(init_raw, q))
    if E_init < E_min:
        raise ValueError(
            f"NUMERICAL_GRID_REJECT: floored E_init={E_init} < E_min={E_min} "
            f"(declared init={init_raw}, quantum={q}); not increasing energy"
        )
    notes["E_truck_min"] = str(E_min)
    notes["E_truck_init"] = str(E_init)
    notes["E_truck_cap"] = str(E_cap)
    return E_min, E_init, E_cap, notes
