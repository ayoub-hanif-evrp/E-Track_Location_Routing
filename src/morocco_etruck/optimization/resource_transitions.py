"""DRIVE / CHARGE / WAIT transitions on discrete labels."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from morocco_etruck.optimization.problem import ArcData, RoutingInstance, StationData

ActionType = Literal["DRIVE", "CHARGE", "WAIT", "START"]


@dataclass(frozen=True)
class Label:
    node: str
    t: int
    E_truck: int
    E_trailer: int | None
    cost: int
    pred_id: int | None
    action: dict[str, Any]
    label_id: int
    # Prevent consecutive re-charging explosions: one CHARGE burst per visit.
    can_charge: bool = True


@dataclass
class TransitionResult:
    ok: bool
    label: Label | None = None
    reason: str | None = None


def _stationary_drain(inst: RoutingInstance, steps: int) -> tuple[int, int]:
    """Return (truck_drain, trailer_drain) kWh over stationary steps."""
    aux = inst.aux_kwh_per_step * steps
    tru = inst.tru_kwh_per_step * steps if inst.refrigeration_on else 0
    if inst.power_source == "A":
        return aux + tru, 0
    return aux, tru


def _check_floors(
    inst: RoutingInstance,
    E_truck: int,
    E_trailer: int | None,
) -> str | None:
    if E_truck < inst.E_truck_min:
        return "tractor_soc_floor"
    if inst.power_source == "B" and inst.refrigeration_on and E_trailer is not None:
        assert inst.E_trailer_min is not None
        if E_trailer < inst.E_trailer_min:
            return "trailer_soc_floor"
    return None


def apply_drive(inst: RoutingInstance, lab: Label, arc: ArcData, new_id: int) -> TransitionResult:
    if arc.u != lab.node:
        return TransitionResult(False, reason="drive_not_from_label_node")

    # Morocco / physics macros: state-dependent table
    if arc.drive_table is not None:
        key = (lab.E_truck, lab.E_trailer)
        entry = arc.drive_table.get(key)
        if entry is None or not entry.feasible:
            return TransitionResult(
                False,
                reason=(entry.reason if entry else "drive_table_missing"),
            )
        t2 = lab.t + entry.dt_steps
        if t2 > inst.deadline_steps:
            return TransitionResult(False, reason="deadline")
        reason = _check_floors(inst, entry.E_end_truck, entry.E_end_trailer)
        if reason:
            return TransitionResult(False, reason=reason)
        return TransitionResult(
            True,
            Label(
                node=arc.v,
                t=t2,
                E_truck=entry.E_end_truck,
                E_trailer=entry.E_end_trailer,
                cost=lab.cost + arc.road_cost,
                pred_id=lab.label_id,
                action={
                    "type": "DRIVE",
                    "u": arc.u,
                    "v": arc.v,
                    "road_cost": arc.road_cost,
                    "dt_steps": entry.dt_steps,
                    "table": True,
                },
                label_id=new_id,
                can_charge=True,
            ),
        )

    if not arc.power_ok:
        return TransitionResult(False, reason="peak_motor_power_exceeded")
    t2 = lab.t + arc.dt_steps
    if t2 > inst.deadline_steps:
        return TransitionResult(False, reason="deadline")
    # dE_*_kwh > 0 means consumption; negative means regen into the pack
    E_tr = lab.E_truck - arc.dE_truck_kwh
    if E_tr > inst.E_truck_cap:
        E_tr = inst.E_truck_cap
    E_tl = lab.E_trailer
    if E_tl is not None:
        E_tl = E_tl - arc.dE_trailer_kwh
        if inst.E_trailer_cap is not None and E_tl > inst.E_trailer_cap:
            E_tl = inst.E_trailer_cap
    reason = _check_floors(inst, E_tr, E_tl)
    if reason:
        return TransitionResult(False, reason=reason)
    cost2 = lab.cost + arc.road_cost
    return TransitionResult(
        True,
        Label(
            node=arc.v,
            t=t2,
            E_truck=E_tr,
            E_trailer=E_tl,
            cost=cost2,
            pred_id=lab.label_id,
            action={"type": "DRIVE", "u": arc.u, "v": arc.v, "road_cost": arc.road_cost},
            label_id=new_id,
            can_charge=True,
        ),
    )


def apply_charge(
    inst: RoutingInstance,
    lab: Label,
    delta_e: int,
    new_id: int,
) -> TransitionResult:
    if delta_e <= 0:
        return TransitionResult(False, reason="zero_charge")
    if not lab.can_charge:
        return TransitionResult(False, reason="already_charged_here")
    if lab.node not in inst.active_stations:
        return TransitionResult(False, reason="station_inactive")
    st = inst.stations.get(lab.node)
    if st is None or not st.compatible:
        return TransitionResult(False, reason="incompatible_charger")
    headroom = inst.E_truck_cap - lab.E_truck
    if delta_e > headroom:
        return TransitionResult(False, reason="no_headroom")
    steps = inst.charge_duration_steps(st, delta_e)
    t2 = lab.t + steps
    if t2 > inst.deadline_steps:
        return TransitionResult(False, reason="deadline")
    drain_tr, drain_tl = _stationary_drain(inst, steps)
    E_tr = lab.E_truck + delta_e - drain_tr
    E_tl = lab.E_trailer
    if E_tl is not None:
        E_tl = E_tl - drain_tl
    reason = _check_floors(inst, E_tr, E_tl)
    if reason:
        return TransitionResult(False, reason=reason)
    if E_tr > inst.E_truck_cap:
        E_tr = inst.E_truck_cap
    grid = inst.grid_kwh_for_batt(st, delta_e)
    cost2 = lab.cost + st.price_cents_per_grid_kwh * grid
    return TransitionResult(
        True,
        Label(
            node=lab.node,
            t=t2,
            E_truck=E_tr,
            E_trailer=E_tl,
            cost=cost2,
            pred_id=lab.label_id,
            action={
                "type": "CHARGE",
                "node": lab.node,
                "delta_e_kwh": delta_e,
                "grid_kwh": grid,
                "steps": steps,
            },
            label_id=new_id,
            can_charge=False,
        ),
    )


def apply_wait(inst: RoutingInstance, lab: Label, k_steps: int, new_id: int) -> TransitionResult:
    if k_steps < 1:
        return TransitionResult(False, reason="zero_wait")
    if k_steps > inst.wait_max_steps:
        return TransitionResult(False, reason="wait_cap")
    t2 = lab.t + k_steps
    if t2 > inst.deadline_steps:
        return TransitionResult(False, reason="deadline")
    drain_tr, drain_tl = _stationary_drain(inst, k_steps)
    E_tr = lab.E_truck - drain_tr
    E_tl = lab.E_trailer
    if E_tl is not None:
        E_tl = E_tl - drain_tl
    reason = _check_floors(inst, E_tr, E_tl)
    if reason:
        return TransitionResult(False, reason=reason)
    return TransitionResult(
        True,
        Label(
            node=lab.node,
            t=t2,
            E_truck=E_tr,
            E_trailer=E_tl,
            cost=lab.cost,
            pred_id=lab.label_id,
            action={"type": "WAIT", "steps": k_steps},
            label_id=new_id,
            can_charge=lab.can_charge,
        ),
    )


def expand_actions(inst: RoutingInstance, lab: Label, id_start: int) -> list[TransitionResult]:
    """Generate all successor transitions from a label."""
    out: list[TransitionResult] = []
    nid = id_start
    for arc in inst.outgoing(lab.node):
        r = apply_drive(inst, lab, arc, nid)
        out.append(r)
        nid += 1
    if lab.node in inst.active_stations:
        st = inst.stations[lab.node]
        headroom = inst.E_truck_cap - lab.E_truck
        q = max(1, int(inst.energy_quantum_kwh))
        for de in range(q, headroom + 1, q):
            r = apply_charge(inst, lab, de, nid)
            out.append(r)
            nid += 1
        _ = st
    for k in range(1, inst.wait_max_steps + 1):
        r = apply_wait(inst, lab, k, nid)
        out.append(r)
        nid += 1
    return out
