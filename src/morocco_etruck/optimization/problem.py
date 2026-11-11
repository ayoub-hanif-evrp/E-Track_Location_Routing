"""Discrete routing instance definitions for Task 03A/03B MRLS."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Literal

PowerSource = Literal["A", "B"]
ObjectiveMode = Literal["enroute_incremental_cost", "energy_replenishment_cost"]


@dataclass(frozen=True)
class DriveTableEntry:
    """State-dependent DRIVE outcome for one start energy quantum (Morocco macros)."""

    feasible: bool
    dt_steps: int = 0
    E_end_truck: int = 0
    E_end_trailer: int | None = None
    reason: str | None = None


@dataclass(frozen=True)
class ArcData:
    """
    Directed arc on the integer grid.

    Synthetic cases use fixed dE_*/dt_steps.
    Morocco macros set drive_table and ignore fixed dE for energy (dt_steps unused).
    Parallel macros that share endpoints are distinguished by arc_id.
    """

    u: str
    v: str
    dt_steps: int
    dE_truck_kwh: int  # consumption ≥0; regen encoded as negative when present
    dE_trailer_kwh: int
    road_cost: int
    power_ok: bool = True
    # key: (E_truck_start, E_trailer_start) — trailer None for config A
    drive_table: dict[tuple[int, int | None], DriveTableEntry] | None = None
    arc_id: str | None = None


@dataclass(frozen=True)
class StationData:
    node: str
    power_kw: float
    eta: float  # charger efficiency (0–1]
    price_cents_per_grid_kwh: int  # cost per kWh drawn from grid
    compatible: bool = True
    # Provenance / honesty fields (optional)
    official_name: str = ""
    hypothetical_access: bool = False
    hgv_status: str = "unknown"
    osm_id: str = ""
    snap_distance_m: float = 0.0


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
    # Legacy integer kWh/step drains (synthetics). Prefer aux_w / tru_mean_w for Morocco.
    aux_kwh_per_step: int = 0
    tru_kwh_per_step: int = 0
    # Continuous stationary loads (W). When >0, CHARGE/WAIT use action-level Wh accounting
    # then floor onto energy_quantum_kwh (never per-step ceil of sub-kWh loads).
    aux_w: float = 0.0
    tru_mean_w: float = 0.0
    wait_max_steps: int = 6
    time_step_min: int = 5
    energy_quantum_kwh: int = 1
    # Operating-cost mode (Task 06B). Legacy default preserves Task 03–06A J.
    objective_mode: ObjectiveMode = "enroute_incremental_cost"
    # Terminal replenishment (used only when objective_mode=energy_replenishment_cost).
    # None ⇒ E_truck_cap / uniform research tariff defaults applied by helpers.
    terminal_target_truck_kwh: int | None = None
    terminal_target_trailer_kwh: int | None = None
    terminal_price_cents_per_grid_kwh: int | None = None
    terminal_eta: float | None = None
    notes: str = ""
    expected: dict[str, Any] = field(default_factory=dict)
    # Task 07C: None = all arcs allowed. When set, DRIVE successors are masked
    # on this same physical graph (no rebuild). Charging still uses active_stations.
    allowed_arc_ids: frozenset[str] | None = None

    def outgoing(self, node: str) -> list[ArcData]:
        arcs = [a for a in self.arcs if a.u == node]
        if self.allowed_arc_ids is None:
            return arcs
        allowed = self.allowed_arc_ids
        out: list[ArcData] = []
        for a in arcs:
            # Synthetics without arc_id remain visible; Morocco macros always have ids.
            if a.arc_id is None or str(a.arc_id) == "":
                out.append(a)
            elif str(a.arc_id) in allowed:
                out.append(a)
        return out

    def charge_duration_steps(self, station: StationData, delta_e_batt_kwh: int) -> int:
        """Time steps to deliver delta_e_batt_kwh into the battery at station power×η."""
        if delta_e_batt_kwh <= 0:
            return 0
        if station.eta <= 0 or station.power_kw <= 0:
            raise ValueError("invalid station power/eta")
        per_step = station.power_kw * station.eta * (self.time_step_min / 60.0)
        return max(1, int(math.ceil(delta_e_batt_kwh / per_step)))

    def grid_kwh_for_batt(self, station: StationData, delta_e_batt_kwh: int) -> int:
        """Grid energy (kWh quanta, ceil) for battery gain delta_e_batt_kwh."""
        if delta_e_batt_kwh <= 0:
            return 0
        return int(math.ceil(delta_e_batt_kwh / station.eta))


class InstanceValidationError(ValueError):
    """Unsupported or inconsistent routing instance."""


def terminal_replenishment_cents(
    inst: RoutingInstance,
    E_truck: int,
    E_trailer: int | None,
) -> int:
    """
    Nonnegative terminal shortfall cost (cents).

    ``enroute_incremental_cost`` → 0 (preloaded battery treated as sunk).
    ``energy_replenishment_cost`` → price × ceil(shortfall / η) for tractor
    (and trailer when config-B fields are present). Does not re-price energy
    already purchased en route.
    """
    if getattr(inst, "objective_mode", "enroute_incremental_cost") != "energy_replenishment_cost":
        return 0
    price = inst.terminal_price_cents_per_grid_kwh
    if price is None:
        # Prefer any active station price; else first station; else research default 20.
        prices = [
            int(st.price_cents_per_grid_kwh)
            for sid, st in inst.stations.items()
            if sid in inst.active_stations
        ]
        if not prices:
            prices = [int(st.price_cents_per_grid_kwh) for st in inst.stations.values()]
        price = prices[0] if prices else 20
    eta = float(inst.terminal_eta) if inst.terminal_eta is not None else 0.95
    if eta <= 0.0 or eta > 1.0:
        raise InstanceValidationError("terminal_eta must be in (0, 1]")
    if int(price) < 0:
        raise InstanceValidationError("terminal_price_cents_per_grid_kwh must be >= 0")

    target_tr = (
        int(inst.terminal_target_truck_kwh)
        if inst.terminal_target_truck_kwh is not None
        else int(inst.E_truck_cap)
    )
    short_tr = max(0, target_tr - int(E_truck))
    grid_tr = int(math.ceil(short_tr / eta)) if short_tr > 0 else 0
    cost = int(price) * grid_tr

    if inst.E_trailer_cap is not None and E_trailer is not None:
        target_tl = (
            int(inst.terminal_target_trailer_kwh)
            if inst.terminal_target_trailer_kwh is not None
            else int(inst.E_trailer_cap)
        )
        short_tl = max(0, target_tl - int(E_trailer))
        grid_tl = int(math.ceil(short_tl / eta)) if short_tl > 0 else 0
        cost += int(price) * grid_tl
    return cost


def total_objective_cents(
    inst: RoutingInstance,
    enroute_cost: int,
    E_truck: int,
    E_trailer: int | None,
) -> int:
    """En-route label cost plus terminal replenishment (0 in legacy mode)."""
    return int(enroute_cost) + terminal_replenishment_cents(inst, E_truck, E_trailer)


def validate_routing_instance(inst: RoutingInstance) -> None:
    """
    Reject unsupported instances.

    Nonnegative operating costs are required for cost-priority MRLS optimality.
    """
    node_set = set(inst.nodes)
    if inst.origin not in node_set:
        raise InstanceValidationError(f"origin {inst.origin!r} not in nodes")
    if inst.destination not in node_set:
        raise InstanceValidationError(f"destination {inst.destination!r} not in nodes")
    if inst.deadline_steps < 0:
        raise InstanceValidationError("deadline_steps must be >= 0")
    if inst.wait_max_steps < 0:
        raise InstanceValidationError("wait_max_steps must be >= 0")
    if inst.energy_quantum_kwh <= 0 or inst.time_step_min <= 0:
        raise InstanceValidationError("energy_quantum_kwh and time_step_min must be > 0")
    if not (inst.E_truck_min <= inst.E_truck_init <= inst.E_truck_cap):
        raise InstanceValidationError("truck energy init must satisfy min <= init <= cap")
    if inst.E_truck_min < 0 or inst.E_truck_cap < 0:
        raise InstanceValidationError("truck capacities must be non-negative")
    q = int(inst.energy_quantum_kwh)
    if inst.E_truck_init % q != 0 or inst.E_truck_min % q != 0 or inst.E_truck_cap % q != 0:
        raise InstanceValidationError("truck energy bounds must lie on energy_quantum_kwh grid")
    if inst.aux_w < 0 or inst.tru_mean_w < 0:
        raise InstanceValidationError("aux_w and tru_mean_w must be non-negative")
    mode = getattr(inst, "objective_mode", "enroute_incremental_cost")
    if mode not in ("enroute_incremental_cost", "energy_replenishment_cost"):
        raise InstanceValidationError(f"unsupported objective_mode: {mode!r}")
    if inst.terminal_eta is not None and not (0.0 < float(inst.terminal_eta) <= 1.0):
        raise InstanceValidationError("terminal_eta must be in (0, 1]")
    if inst.terminal_price_cents_per_grid_kwh is not None and int(inst.terminal_price_cents_per_grid_kwh) < 0:
        raise InstanceValidationError("terminal_price_cents_per_grid_kwh must be >= 0")

    if inst.power_source == "B" and inst.refrigeration_on:
        if inst.E_trailer_cap is None or inst.E_trailer_min is None or inst.E_trailer_init is None:
            raise InstanceValidationError("config B + refrigeration requires trailer fields")
        if not (inst.E_trailer_min <= inst.E_trailer_init <= inst.E_trailer_cap):
            raise InstanceValidationError("trailer energy init must satisfy min <= init <= cap")
        if (
            inst.E_trailer_init % q != 0
            or inst.E_trailer_min % q != 0
            or inst.E_trailer_cap % q != 0
        ):
            raise InstanceValidationError("trailer energy bounds must lie on energy_quantum_kwh grid")

    for arc in inst.arcs:
        if arc.u not in node_set or arc.v not in node_set:
            raise InstanceValidationError(f"arc {arc.u}->{arc.v} references unknown nodes")
        if arc.drive_table is None and arc.dt_steps <= 0:
            raise InstanceValidationError(f"arc {arc.u}->{arc.v} has non-positive dt_steps")
        if arc.road_cost < 0:
            raise InstanceValidationError(
                f"arc {arc.u}->{arc.v} has negative road_cost (unsupported for optimality)"
            )

    for sid, st in inst.stations.items():
        if sid not in node_set or st.node not in node_set:
            raise InstanceValidationError(f"station {sid!r} not in nodes")
        if st.power_kw <= 0:
            raise InstanceValidationError(f"station {sid}: power_kw must be > 0")
        if not (0.0 < st.eta <= 1.0):
            raise InstanceValidationError(f"station {sid}: eta must be in (0, 1]")
        if st.price_cents_per_grid_kwh < 0:
            raise InstanceValidationError(
                f"station {sid}: negative electricity price unsupported for optimality"
            )

    for a in inst.active_stations:
        if a not in inst.stations:
            raise InstanceValidationError(f"active station {a!r} missing from stations dict")
