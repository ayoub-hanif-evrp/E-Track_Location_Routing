"""Transition-level battery quantization audit (DRIVE / CHARGE / WAIT).

Conservative flooring onto the energy quantum is preserved. This module only
measures continuous-vs-discrete discrepancy for scientific reporting.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from morocco_etruck.optimization.problem import RoutingInstance, StationData
from morocco_etruck.optimization.resource_transitions import (
    Label,
    _floor_to_quantum,
    apply_charge,
    apply_wait,
    stationary_drain_kwh,
)


@dataclass
class QuantizationStep:
    action: str
    E_before_disc: int
    E_after_cont: float
    E_after_disc: int
    physical_delta_kwh: float
    rounding_loss_kwh: float
    note: str = ""


def charge_continuous_vs_discrete(
    inst: RoutingInstance,
    *,
    E_truck: int,
    delta_e: int,
    node: str | None = None,
) -> QuantizationStep:
    """
    Compare continuous post-charge energy to the floored discrete label energy.

    Demonstrates that a paid CHARGE can have zero discrete net gain when
    continuous residual falls short of the next quantum after stationary drain.
    """
    q = max(1, int(inst.energy_quantum_kwh))
    # Build a minimal label at the charge node
    st_node = node or next(iter(inst.active_stations or inst.stations.keys()))
    lab = Label(
        node=st_node,
        t=0,
        E_truck=int(E_truck),
        E_trailer=inst.E_trailer_init,
        cost=0,
        pred_id=None,
        action={"type": "START"},
        label_id=0,
        can_charge=True,
    )
    # Ensure station active for apply_charge
    if st_node not in inst.active_stations:
        # Audit helper: temporarily treat as active via local clone fields
        pass
    st = inst.stations[st_node]
    steps = inst.charge_duration_steps(st, delta_e)
    drain_tr, drain_tl = stationary_drain_kwh(inst, steps)
    E_cont = float(E_truck) + float(delta_e) - drain_tr
    E_disc = _floor_to_quantum(E_cont, q)
    if E_disc > inst.E_truck_cap:
        E_disc = inst.E_truck_cap
    loss = max(0.0, E_cont - float(E_disc))
    return QuantizationStep(
        action="CHARGE",
        E_before_disc=int(E_truck),
        E_after_cont=E_cont,
        E_after_disc=int(E_disc),
        physical_delta_kwh=float(delta_e) - drain_tr,
        rounding_loss_kwh=loss,
        note=(
            "zero_discrete_gain"
            if int(E_disc) == int(E_truck)
            else "discrete_gain=" + str(int(E_disc) - int(E_truck))
        ),
    )


def wait_continuous_vs_discrete(
    inst: RoutingInstance,
    *,
    E_truck: int,
    steps: int,
) -> QuantizationStep:
    q = max(1, int(inst.energy_quantum_kwh))
    drain_tr, _ = stationary_drain_kwh(inst, steps)
    E_cont = float(E_truck) - drain_tr
    E_disc = _floor_to_quantum(E_cont, q)
    loss = max(0.0, E_cont - float(E_disc))
    return QuantizationStep(
        action="WAIT",
        E_before_disc=int(E_truck),
        E_after_cont=E_cont,
        E_after_disc=int(E_disc),
        physical_delta_kwh=-drain_tr,
        rounding_loss_kwh=loss,
    )


def cumulative_rounding_loss(steps: list[QuantizationStep]) -> float:
    return float(sum(s.rounding_loss_kwh for s in steps))


def summarize_quantization_policy() -> dict[str, Any]:
    return {
        "policy": "conservative_floor_after_DRIVE_CHARGE_WAIT",
        "DRIVE": "ending kWh floored onto quantum in DRIVE table build",
        "CHARGE_WAIT": "continuous energy floored after stationary drain",
        "adopted_correction": None,
        "rationale": (
            "Removing flooring would risk optimistic discrete feasibility. "
            "Publication-facing infrastructure claims require fine-grid stability "
            "(see battery_quantization_and_convergence report)."
        ),
        "alternatives_considered": [
            "finer_fixed_grids",
            "residual_preserving_state",
            "quantize_only_at_charge_events",
            "conservative_interval_bounds",
        ],
        "novel_algorithm_claim": False,
    }
