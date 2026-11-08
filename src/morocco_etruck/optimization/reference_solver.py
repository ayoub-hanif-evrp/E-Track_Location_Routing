"""Independent exhaustive discrete-state solver (no dominance pruning)."""

from __future__ import annotations

import time
from heapq import heappop, heappush
from typing import Any

from morocco_etruck.optimization.label_setting import SolveResult, SolverStatus
from morocco_etruck.optimization.problem import RoutingInstance
from morocco_etruck.optimization.resource_transitions import (
    Label,
    apply_charge,
    apply_drive,
    apply_wait,
)


def _state_key(lab: Label) -> tuple:
    return (lab.node, lab.t, lab.E_truck, lab.E_trailer, lab.cost)


def solve_reference(
    inst: RoutingInstance,
    *,
    max_expansions: int | None = 500_000,
    max_seconds: float | None = 60.0,
) -> SolveResult:
    """
    Exact shortest-path over the full discrete state graph.

    Visited key: (node, t, E_truck, E_trailer). Keeps best cost only per key
    (equality pruning, not Pareto dominance across unequal energies).
    """
    t0 = time.perf_counter()
    labels_by_id: dict[int, Label] = {}
    next_id = 0
    # best cost seen for (node, t, E_truck, E_trailer, can_charge)
    best_cost: dict[tuple, int] = {}

    start = Label(
        node=inst.origin,
        t=0,
        E_truck=inst.E_truck_init,
        E_trailer=inst.E_trailer_init,
        cost=0,
        pred_id=None,
        action={"type": "START"},
        label_id=next_id,
        can_charge=inst.origin in inst.active_stations,
    )
    next_id += 1
    labels_by_id[start.label_id] = start
    sk0 = (start.node, start.t, start.E_truck, start.E_trailer, start.can_charge)
    best_cost[sk0] = 0

    heap: list[tuple[int, int, int]] = [(0, 0, start.label_id)]
    generated = 1
    expanded = 0

    def reconstruct(lab: Label) -> tuple[list[str], list[dict[str, Any]]]:
        actions: list[dict[str, Any]] = []
        nodes_rev: list[str] = []
        cur: Label | None = lab
        while cur is not None:
            nodes_rev.append(cur.node)
            if cur.action.get("type") != "START":
                actions.append(cur.action)
            if cur.pred_id is None:
                break
            cur = labels_by_id.get(cur.pred_id)
        actions.reverse()
        nodes_rev.reverse()
        path: list[str] = []
        for n in nodes_rev:
            if not path or path[-1] != n:
                path.append(n)
        return path, actions

    while heap:
        if max_seconds is not None and (time.perf_counter() - t0) > max_seconds:
            return SolveResult(
                status=SolverStatus.LIMIT_REACHED,
                objective=None,
                path_nodes=[],
                actions=[],
                final_label=None,
                stats={
                    "labels_generated": generated,
                    "labels_expanded": expanded,
                    "labels_dominated": 0,
                    "runtime_s": time.perf_counter() - t0,
                    "solver": "reference",
                },
            )
        if max_expansions is not None and expanded >= max_expansions:
            return SolveResult(
                status=SolverStatus.LIMIT_REACHED,
                objective=None,
                path_nodes=[],
                actions=[],
                final_label=None,
                stats={
                    "labels_generated": generated,
                    "labels_expanded": expanded,
                    "labels_dominated": 0,
                    "runtime_s": time.perf_counter() - t0,
                    "solver": "reference",
                },
            )

        cost, _t, lid = heappop(heap)
        lab = labels_by_id[lid]
        sk = (lab.node, lab.t, lab.E_truck, lab.E_trailer, lab.can_charge)
        if cost > best_cost.get(sk, cost):
            continue

        if lab.node == inst.destination:
            path, actions = reconstruct(lab)
            return SolveResult(
                status=SolverStatus.OPTIMAL,
                objective=lab.cost,
                path_nodes=path,
                actions=actions,
                final_label=lab,
                stats={
                    "labels_generated": generated,
                    "labels_expanded": expanded,
                    "labels_dominated": 0,
                    "runtime_s": time.perf_counter() - t0,
                    "solver": "reference",
                    "best_cost": lab.cost,
                },
            )

        expanded += 1

        def _push(nxt: Label) -> None:
            nonlocal next_id, generated
            key = (nxt.node, nxt.t, nxt.E_truck, nxt.E_trailer, nxt.can_charge)
            prev = best_cost.get(key)
            if prev is not None and prev <= nxt.cost:
                return
            best_cost[key] = nxt.cost
            labels_by_id[nxt.label_id] = nxt
            heappush(heap, (nxt.cost, nxt.t, nxt.label_id))
            generated += 1

        for arc in inst.outgoing(lab.node):
            r = apply_drive(inst, lab, arc, next_id)
            if r.ok and r.label is not None:
                next_id += 1
                _push(r.label)

        if lab.can_charge and lab.node in inst.active_stations:
            headroom = inst.E_truck_cap - lab.E_truck
            for de in range(1, headroom + 1):
                r = apply_charge(inst, lab, de, next_id)
                if r.ok and r.label is not None:
                    next_id += 1
                    _push(r.label)

        for k in range(1, inst.wait_max_steps + 1):
            r = apply_wait(inst, lab, k, next_id)
            if r.ok and r.label is not None:
                next_id += 1
                _push(r.label)

    return SolveResult(
        status=SolverStatus.INFEASIBLE,
        objective=None,
        path_nodes=[],
        actions=[],
        final_label=None,
        stats={
            "labels_generated": generated,
            "labels_expanded": expanded,
            "labels_dominated": 0,
            "runtime_s": time.perf_counter() - t0,
            "solver": "reference",
        },
    )
