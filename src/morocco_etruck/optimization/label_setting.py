"""Multi-resource label-setting solver (Task 03A)."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from heapq import heappop, heappush
from typing import Any

from morocco_etruck.optimization.dominance import DominanceStore
from morocco_etruck.optimization.problem import RoutingInstance
from morocco_etruck.optimization.resource_transitions import (
    Label,
    apply_charge,
    apply_drive,
    apply_wait,
)


class SolverStatus(str, Enum):
    OPTIMAL = "OPTIMAL"
    INFEASIBLE = "INFEASIBLE"
    LIMIT_REACHED = "LIMIT_REACHED"


@dataclass
class SolveResult:
    status: SolverStatus
    objective: int | None
    path_nodes: list[str]
    actions: list[dict[str, Any]]
    final_label: Label | None
    stats: dict[str, Any] = field(default_factory=dict)


def _reconstruct(labels_by_id: dict[int, Label], lab: Label) -> tuple[list[str], list[dict[str, Any]]]:
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
    # Compress consecutive duplicate nodes from WAIT/CHARGE
    path: list[str] = []
    for n in nodes_rev:
        if not path or path[-1] != n:
            path.append(n)
    return path, actions


def solve_mrls(
    inst: RoutingInstance,
    *,
    use_dominance: bool = True,
    max_expansions: int | None = 200_000,
    max_seconds: float | None = 30.0,
) -> SolveResult:
    """
    Exact MRLS for the finite discrete instance (with optional computational limits).

    Priority: minimize cost, then time.
    """
    t0 = time.perf_counter()
    store = DominanceStore(enabled=use_dominance)
    labels_by_id: dict[int, Label] = {}
    next_id = 0

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
    store.accept(start)

    # heap entries: (cost, t, label_id)
    heap: list[tuple[int, int, int]] = []
    heappush(heap, (start.cost, start.t, start.label_id))

    generated = 1
    expanded = 0
    best: Label | None = None

    while heap:
        if max_seconds is not None and (time.perf_counter() - t0) > max_seconds:
            return SolveResult(
                status=SolverStatus.LIMIT_REACHED,
                objective=best.cost if best else None,
                path_nodes=[],
                actions=[],
                final_label=best,
                stats=_stats(generated, expanded, store.dominated_count, t0, best),
            )
        if max_expansions is not None and expanded >= max_expansions:
            return SolveResult(
                status=SolverStatus.LIMIT_REACHED,
                objective=best.cost if best else None,
                path_nodes=[],
                actions=[],
                final_label=best,
                stats=_stats(generated, expanded, store.dominated_count, t0, best),
            )

        _c, _t, lid = heappop(heap)
        lab = labels_by_id[lid]
        # Skip if a better label already made this stale (still in heap)
        # We keep all; dominance prevents inserting dominated ones.

        if lab.node == inst.destination:
            path, actions = _reconstruct(labels_by_id, lab)
            return SolveResult(
                status=SolverStatus.OPTIMAL,
                objective=lab.cost,
                path_nodes=path,
                actions=actions,
                final_label=lab,
                stats=_stats(generated, expanded, store.dominated_count, t0, lab),
            )

        expanded += 1

        # DRIVE
        for arc in inst.outgoing(lab.node):
            r = apply_drive(inst, lab, arc, next_id)
            if not r.ok or r.label is None:
                continue
            generated += 1
            nxt = r.label
            next_id += 1
            if store.accept(nxt):
                labels_by_id[nxt.label_id] = nxt
                heappush(heap, (nxt.cost, nxt.t, nxt.label_id))

        # CHARGE (at most one burst per visit; see Label.can_charge)
        if lab.can_charge and lab.node in inst.active_stations:
            headroom = inst.E_truck_cap - lab.E_truck
            for de in range(1, headroom + 1):
                r = apply_charge(inst, lab, de, next_id)
                if not r.ok or r.label is None:
                    continue
                generated += 1
                nxt = r.label
                next_id += 1
                if store.accept(nxt):
                    labels_by_id[nxt.label_id] = nxt
                    heappush(heap, (nxt.cost, nxt.t, nxt.label_id))

        # WAIT
        for k in range(1, inst.wait_max_steps + 1):
            r = apply_wait(inst, lab, k, next_id)
            if not r.ok or r.label is None:
                continue
            generated += 1
            nxt = r.label
            next_id += 1
            if store.accept(nxt):
                labels_by_id[nxt.label_id] = nxt
                heappush(heap, (nxt.cost, nxt.t, nxt.label_id))

    return SolveResult(
        status=SolverStatus.INFEASIBLE,
        objective=None,
        path_nodes=[],
        actions=[],
        final_label=None,
        stats=_stats(generated, expanded, store.dominated_count, t0, None),
    )


def _stats(generated: int, expanded: int, dominated: int, t0: float, best: Label | None) -> dict[str, Any]:
    return {
        "labels_generated": generated,
        "labels_expanded": expanded,
        "labels_dominated": dominated,
        "runtime_s": time.perf_counter() - t0,
        "best_cost": best.cost if best else None,
    }
