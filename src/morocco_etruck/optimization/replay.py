"""Replay discrete solutions action-by-action for reconstruction checks."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from morocco_etruck.optimization.problem import ArcData, RoutingInstance, total_objective_cents
from morocco_etruck.optimization.resource_transitions import (
    Label,
    apply_charge,
    apply_drive,
    apply_wait,
)


@dataclass
class ReplayReport:
    ok: bool
    final_cost: int | None
    final_t: int | None
    final_E_truck: int | None
    final_E_trailer: int | None
    path_nodes: list[str]
    reason: str | None = None


def resolve_drive_arc(
    inst: RoutingInstance,
    *,
    u: str,
    v: str,
    arc_id: str | None,
    road_cost: int | None = None,
    dt_steps: int | None = None,
    dE_truck_kwh: int | None = None,
) -> tuple[ArcData | None, str | None]:
    """
    Resolve the exact DRIVE arc for replay.

    Prefer unique ``arc_id``. Without ``arc_id``, allow a unique ``u→v`` arc, or a
    unique fingerprint match on (road_cost, dt_steps, dE_truck_kwh) for legacy
    synthetics. Never silently pick the first of several parallels.
    """
    outgoing = list(inst.outgoing(u))
    if arc_id is not None and str(arc_id).strip():
        aid = str(arc_id)
        matches = [a for a in outgoing if a.arc_id is not None and str(a.arc_id) == aid]
        if not matches:
            # Also search full instance (action may be correct but u mismatched)
            matches = [a for a in inst.arcs if a.arc_id is not None and str(a.arc_id) == aid]
        if len(matches) != 1:
            return None, "missing_or_ambiguous_arc_id"
        arc = matches[0]
        if arc.u != u or arc.v != v:
            return None, f"arc_id_endpoint_mismatch:{arc.u}->{arc.v}!={u}->{v}"
        return arc, None

    cands = [a for a in outgoing if a.v == v]
    if not cands:
        return None, "missing_arc"
    if len(cands) == 1:
        return cands[0], None
    # Legacy synthetics without arc_id: require a unique fingerprint.
    filtered = cands
    if road_cost is not None:
        filtered = [a for a in filtered if a.road_cost == int(road_cost)]
    if dt_steps is not None:
        filtered = [a for a in filtered if a.dt_steps == int(dt_steps)]
    if dE_truck_kwh is not None:
        filtered = [a for a in filtered if a.dE_truck_kwh == int(dE_truck_kwh)]
    if len(filtered) == 1:
        return filtered[0], None
    return None, "ambiguous_parallel_arc"


def replay_solution(
    inst: RoutingInstance,
    actions: list[dict[str, Any]],
    *,
    expected_cost: int | None = None,
) -> ReplayReport:
    """
    Walk actions from the origin label and verify transitions.

    Each DRIVE must leave the label's current node and use an exact arc identity.
    The reconstructed journey must end at the destination.
    """
    lab = Label(
        node=inst.origin,
        t=0,
        E_truck=inst.E_truck_init,
        E_trailer=inst.E_trailer_init,
        cost=0,
        pred_id=None,
        action={"type": "START"},
        label_id=0,
        can_charge=inst.origin in inst.active_stations,
    )
    path = [lab.node]
    nid = 1
    for act in actions:
        typ = act.get("type")
        if typ == "DRIVE":
            u, v = act["u"], act["v"]
            if lab.node != u:
                return ReplayReport(
                    False, None, None, None, None, path, reason=f"drive_from_wrong_node:{lab.node}!={u}"
                )
            arc, err = resolve_drive_arc(
                inst,
                u=u,
                v=v,
                arc_id=act.get("arc_id"),
                road_cost=int(act["road_cost"]) if "road_cost" in act else None,
                dt_steps=int(act["dt_steps"]) if "dt_steps" in act else None,
                dE_truck_kwh=int(act["dE_truck_kwh"]) if "dE_truck_kwh" in act else None,
            )
            if arc is None:
                return ReplayReport(False, None, None, None, None, path, reason=err)
            r = apply_drive(inst, lab, arc, nid)
            if not r.ok or r.label is None:
                return ReplayReport(False, None, None, None, None, path, reason=r.reason)
            lab = r.label
            nid += 1
            if path[-1] != lab.node:
                path.append(lab.node)
        elif typ == "CHARGE":
            if act.get("node") and act["node"] != lab.node:
                return ReplayReport(
                    False, None, None, None, None, path, reason="charge_wrong_node"
                )
            if lab.node not in inst.active_stations:
                return ReplayReport(
                    False, None, None, None, None, path, reason="station_inactive"
                )
            de = int(act["delta_e_kwh"])
            r = apply_charge(inst, lab, de, nid)
            if not r.ok or r.label is None:
                return ReplayReport(False, None, None, None, None, path, reason=r.reason)
            lab = r.label
            nid += 1
            q = max(1, int(inst.energy_quantum_kwh))
            if lab.E_truck % q != 0:
                return ReplayReport(
                    False, lab.cost, lab.t, lab.E_truck, lab.E_trailer, path,
                    reason="off_grid_after_charge",
                )
        elif typ == "WAIT":
            r = apply_wait(inst, lab, int(act["steps"]), nid)
            if not r.ok or r.label is None:
                return ReplayReport(False, None, None, None, None, path, reason=r.reason)
            lab = r.label
            nid += 1
            q = max(1, int(inst.energy_quantum_kwh))
            if lab.E_truck % q != 0:
                return ReplayReport(
                    False, lab.cost, lab.t, lab.E_truck, lab.E_trailer, path,
                    reason="off_grid_after_wait",
                )
        else:
            return ReplayReport(False, None, None, None, None, path, reason=f"unknown_action:{typ}")

    if lab.node != inst.destination:
        return ReplayReport(
            False,
            lab.cost,
            lab.t,
            lab.E_truck,
            lab.E_trailer,
            path,
            reason=f"not_at_destination:{lab.node}!={inst.destination}",
        )
    if lab.t > inst.deadline_steps:
        return ReplayReport(
            False, lab.cost, lab.t, lab.E_truck, lab.E_trailer, path, reason="deadline"
        )
    if lab.E_truck < inst.E_truck_min:
        return ReplayReport(
            False, lab.cost, lab.t, lab.E_truck, lab.E_trailer, path, reason="tractor_soc_floor"
        )
    if (
        inst.E_trailer_min is not None
        and lab.E_trailer is not None
        and lab.E_trailer < inst.E_trailer_min
    ):
        return ReplayReport(
            False, lab.cost, lab.t, lab.E_truck, lab.E_trailer, path, reason="trailer_soc_floor"
        )

    total = total_objective_cents(inst, lab.cost, lab.E_truck, lab.E_trailer)
    if expected_cost is not None and total != expected_cost:
        return ReplayReport(
            False,
            total,
            lab.t,
            lab.E_truck,
            lab.E_trailer,
            path,
            reason=f"cost_mismatch:{total}!={expected_cost}",
        )
    return ReplayReport(
        True,
        total,
        lab.t,
        lab.E_truck,
        lab.E_trailer,
        path,
        reason=None,
    )
