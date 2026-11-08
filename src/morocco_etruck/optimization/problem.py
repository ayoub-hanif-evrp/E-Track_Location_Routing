"""Discrete routing instance definitions for Task 03A MRLS."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

PowerSource = Literal["A", "B"]


@dataclass(frozen=True)
class ArcData:
    """Precomputed directed arc attributes on the integer grid (exact for synthetic cases)."""

    u: str
    v: str
    dt_steps: int
    dE_truck_kwh: int  # consumption ≥0; regen encoded as negative when present
    dE_trailer_kwh: int
    road_cost: int
    power_ok: bool = True


@dataclass(frozen=True)
class StationData:
    node: str
    power_kw: float
    eta: float  # charger efficiency (0–1]
    price_cents_per_grid_kwh: int  # cost per kWh drawn from grid
    compatible: bool = True


@dataclass
class RoutingInstance:
    """Finite discrete multi-resource routing problem."""

    name: str
    nodes: list[str]
    arcs: list[ArcData]
    origin: str
    destination: str
    deadline_steps: int
    E_truck_cap: int
    E_truck_min: int
    E_truck_init: int
    E_trailer_cap: int | None
    E_trailer_min: int | None
    E_trailer_init: int | None
    stations: dict[str, StationData]
    active_stations: set[str]
    power_source: PowerSource
    refrigeration_on: bool
    # Stationary consumption per time step while CHARGE or WAIT
    aux_kwh_per_step: int = 0
    tru_kwh_per_step: int = 0
    wait_max_steps: int = 6
    time_step_min: int = 5
    energy_quantum_kwh: int = 1
    notes: str = ""
    expected: dict[str, Any] = field(default_factory=dict)

    def outgoing(self, node: str) -> list[ArcData]:
        return [a for a in self.arcs if a.u == node]

    def charge_duration_steps(self, station: StationData, delta_e_batt_kwh: int) -> int:
        """Time steps to deliver delta_e_batt_kwh into the battery at station power×η."""
        if delta_e_batt_kwh <= 0:
            return 0
        if station.eta <= 0 or station.power_kw <= 0:
            raise ValueError("invalid station power/eta")
        # Energy into battery per time step = power_kw * eta * (time_step_min/60)
        per_step = station.power_kw * station.eta * (self.time_step_min / 60.0)
        import math

        return max(1, int(math.ceil(delta_e_batt_kwh / per_step)))

    def grid_kwh_for_batt(self, station: StationData, delta_e_batt_kwh: int) -> int:
        """Grid energy (kWh quanta, ceil) for battery gain delta_e_batt_kwh."""
        import math

        if delta_e_batt_kwh <= 0:
            return 0
        return int(math.ceil(delta_e_batt_kwh / station.eta))
