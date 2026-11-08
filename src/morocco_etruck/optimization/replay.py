"""Replay discrete solutions action-by-action for reconstruction checks."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from morocco_etruck.optimization.problem import RoutingInstance
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


def replay_solution(
    inst: RoutingInstance,
    actions: list[dict[str, Any]],
    *,
    expected_cost: int | None = None,
) -> ReplayReport:
    """
    Walk actions from the origin label and verify transitions.

    Each DRIVE must leave the label's current node.
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
            arcs = [a for a in inst.outgoing(lab.node) if a.v == v]
            if not arcs:
                return ReplayReport(False, None, None, None, None, path, reason="missing_arc")
            # Prefer matching road_cost if parallel arcs
            arc = arcs[0]
            for a in arcs:
                if a.road_cost == int(act.get("road_cost", a.road_cost)):
                    arc = a
                    break
            r = apply_drive(inst, lab, arc, nid)
            if not r.ok or r.label is None:
                return ReplayReport(False, None, None, None, None, path, reason=r.reason)
            lab = r.label
            nid += 1
            if path[-1] != lab.node:
                path.append(lab.node)
        elif typ == "CHARGE":
            de = int(act["delta_e_kwh"])
            r = apply_charge(inst, lab, de, nid)
            if not r.ok or r.label is None:
                return ReplayReport(False, None, None, None, None, path, reason=r.reason)
            lab = r.label
            nid += 1
        elif typ == "WAIT":
            r = apply_wait(inst, lab, int(act["steps"]), nid)
            if not r.ok or r.label is None:
                return ReplayReport(False, None, None, None, None, path, reason=r.reason)
            lab = r.label
            nid += 1
        else:
            return ReplayReport(False, None, None, None, None, path, reason=f"unknown_action:{typ}")

    if expected_cost is not None and lab.cost != expected_cost:
        return ReplayReport(
            False,
            lab.cost,
            lab.t,
            lab.E_truck,
            lab.E_trailer,
            path,
            reason=f"cost_mismatch:{lab.cost}!={expected_cost}",
        )
    return ReplayReport(
        True,
        lab.cost,
        lab.t,
        lab.E_truck,
        lab.E_trailer,
        path,
        reason=None,
    )
