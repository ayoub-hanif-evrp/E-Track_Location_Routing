"""DRIVE / CHARGE / WAIT transitions on discrete labels."""

from __future__ import annotations

import math
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


def _uses_watt_stationary(inst: RoutingInstance) -> bool:
    return float(inst.aux_w) > 0.0 or float(inst.tru_mean_w) > 0.0


def _floor_to_quantum(kwh: float, quantum: int) -> int:
    """Conservative remaining energy: never round up onto the discrete lattice."""
    q = max(1, int(quantum))
    return int(math.floor(kwh / q) * q)


def stationary_drain_kwh(inst: RoutingInstance, steps: int) -> tuple[float, float]:
    """
    Continuous (or legacy integer) stationary drains over a full CHARGE/WAIT action.

    Morocco: aux_w / tru_mean_w integrated over the whole duration (no per-step ceil).
    Synthetics: aux_kwh_per_step * steps (+ TRU) when watts are unset.
    """
    if steps < 0:
        raise ValueError("steps must be >= 0")
    if _uses_watt_stationary(inst):
        dt_h = steps * inst.time_step_min / 60.0
        aux = float(inst.aux_w) * dt_h / 1000.0
        tru = 0.0
        if inst.refrigeration_on:
            tru = float(inst.tru_mean_w) * dt_h / 1000.0
        if inst.power_source == "A":
            return aux + tru, 0.0
        return aux, tru
    aux = float(inst.aux_kwh_per_step * steps)
    tru = float(inst.tru_kwh_per_step * steps) if inst.refrigeration_on else 0.0
    if inst.power_source == "A":
        return aux + tru, 0.0
    return aux, tru


def _snap_energies_after_stationary(
    inst: RoutingInstance,
    E_truck_cont: float,
    E_trailer_cont: float | None,
) -> tuple[int, int | None, str | None]:
    """Floor continuous energies onto the quantum grid and check SOC floors."""
    q = max(1, int(inst.energy_quantum_kwh))
    if _uses_watt_stationary(inst):
        E_tr = _floor_to_quantum(E_truck_cont, q)
        E_tl = None if E_trailer_cont is None else _floor_to_quantum(E_trailer_cont, q)
    else:
        # Legacy integer path: already integer kWh; keep exact synthetics.
        E_tr = int(E_truck_cont)
        E_tl = None if E_trailer_cont is None else int(E_trailer_cont)
    if E_tr > inst.E_truck_cap:
        E_tr = inst.E_truck_cap
    if E_tl is not None and inst.E_trailer_cap is not None and E_tl > inst.E_trailer_cap:
        E_tl = inst.E_trailer_cap
    reason = _check_floors(inst, E_tr, E_tl)
    return E_tr, E_tl, reason


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
        q = max(1, int(inst.energy_quantum_kwh))
        if lab.E_truck % q != 0 or (lab.E_trailer is not None and lab.E_trailer % q != 0):
            return TransitionResult(False, reason="off_grid_energy_before_drive")
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
        action = {
            "type": "DRIVE",
            "u": arc.u,
            "v": arc.v,
            "road_cost": arc.road_cost,
            "dt_steps": entry.dt_steps,
            "table": True,
        }
        if arc.arc_id is not None:
            action["arc_id"] = arc.arc_id
        return TransitionResult(
            True,
            Label(
                node=arc.v,
                t=t2,
                E_truck=entry.E_end_truck,
                E_trailer=entry.E_end_trailer,
                cost=lab.cost + arc.road_cost,
                pred_id=lab.label_id,
                action=action,
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
    action = {
        "type": "DRIVE",
        "u": arc.u,
        "v": arc.v,
        "road_cost": arc.road_cost,
        "dt_steps": arc.dt_steps,
        "dE_truck_kwh": arc.dE_truck_kwh,
    }
    if arc.arc_id is not None:
        action["arc_id"] = arc.arc_id
    return TransitionResult(
        True,
        Label(
            node=arc.v,
            t=t2,
            E_truck=E_tr,
            E_trailer=E_tl,
            cost=cost2,
            pred_id=lab.label_id,
            action=action,
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
    drain_tr, drain_tl = stationary_drain_kwh(inst, steps)
    E_tr_cont = float(lab.E_truck) + float(delta_e) - drain_tr
    E_tl_cont: float | None
    if lab.E_trailer is None:
        E_tl_cont = None
    else:
        E_tl_cont = float(lab.E_trailer) - drain_tl
    E_tr, E_tl, reason = _snap_energies_after_stationary(inst, E_tr_cont, E_tl_cont)
    if reason:
        return TransitionResult(False, reason=reason)
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
                "drain_truck_kwh": round(drain_tr, 6),
                "drain_trailer_kwh": round(drain_tl, 6),
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
    drain_tr, drain_tl = stationary_drain_kwh(inst, k_steps)
    E_tr_cont = float(lab.E_truck) - drain_tr
    E_tl_cont: float | None
    if lab.E_trailer is None:
        E_tl_cont = None
    else:
        E_tl_cont = float(lab.E_trailer) - drain_tl
    E_tr, E_tl, reason = _snap_energies_after_stationary(inst, E_tr_cont, E_tl_cont)
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
            action={
                "type": "WAIT",
                "steps": k_steps,
                "drain_truck_kwh": round(drain_tr, 6),
                "drain_trailer_kwh": round(drain_tl, 6),
            },
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
