"""Independent exhaustive discrete-state solver (no dominance pruning)."""

from __future__ import annotations

import time
from heapq import heappop, heappush
from typing import Any

from morocco_etruck.optimization.label_setting import SolveResult, SolverStatus
from morocco_etruck.optimization.problem import (
    RoutingInstance,
    total_objective_cents,
    validate_routing_instance,
)
from morocco_etruck.optimization.resource_transitions import (
    Label,
    apply_charge,
    apply_drive,
    apply_wait,
)


def solve_reference(
    inst: RoutingInstance,
    *,
    max_expansions: int | None = 500_000,
    max_seconds: float | None = 60.0,
) -> SolveResult:
    """
    Exact shortest-path over the full discrete state graph.

    Visited key: (node, t, E_truck, E_trailer, can_charge). Keeps best en-route
    cost only per key (equality pruning, not Pareto dominance across unequal energies).

    Under ``energy_replenishment_cost``, first destination pop is not sufficient:
    continue while unfinished labels can improve the best completed total.
    """
    validate_routing_instance(inst)
    t0 = time.perf_counter()
    labels_by_id: dict[int, Label] = {}
    next_id = 0
    best_cost: dict[tuple, int] = {}
    terminal_mode = (
        getattr(inst, "objective_mode", "enroute_incremental_cost") == "energy_replenishment_cost"
    )

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
    best: Label | None = None
    best_total: int | None = None

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

    def _stats() -> dict[str, Any]:
        return {
            "labels_generated": generated,
            "labels_expanded": expanded,
            "labels_dominated": 0,
            "runtime_s": time.perf_counter() - t0,
            "solver": "reference",
            "best_cost": best_total,
            "best_enroute_cost": best.cost if best else None,
        }

    while heap:
        if max_seconds is not None and (time.perf_counter() - t0) > max_seconds:
            return SolveResult(
                status=SolverStatus.LIMIT_REACHED,
                objective=best_total,
                path_nodes=[],
                actions=[],
                final_label=best,
                stats=_stats(),
            )
        if max_expansions is not None and expanded >= max_expansions:
            return SolveResult(
                status=SolverStatus.LIMIT_REACHED,
                objective=best_total,
                path_nodes=[],
                actions=[],
                final_label=best,
                stats=_stats(),
            )

        cost, _t, lid = heappop(heap)
        lab = labels_by_id[lid]
        sk = (lab.node, lab.t, lab.E_truck, lab.E_trailer, lab.can_charge)
        if cost > best_cost.get(sk, cost):
            continue
        if terminal_mode and best_total is not None and lab.cost >= best_total:
            continue

        if lab.node == inst.destination:
            total = total_objective_cents(inst, lab.cost, lab.E_truck, lab.E_trailer)
            better = best_total is None or total < best_total
            tie_faster = (
                best_total is not None
                and total == best_total
                and best is not None
                and lab.t < best.t
            )
            if better or tie_faster:
                best = lab
                best_total = total
            if not terminal_mode:
                path, actions = reconstruct(lab)
                return SolveResult(
                    status=SolverStatus.OPTIMAL,
                    objective=total,
                    path_nodes=path,
                    actions=actions,
                    final_label=lab,
                    stats=_stats(),
                )
            continue

        expanded += 1

        def _push(nxt: Label) -> None:
            nonlocal next_id, generated
            if terminal_mode and best_total is not None and nxt.cost >= best_total:
                return
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
            q = max(1, int(inst.energy_quantum_kwh))
            for de in range(q, headroom + 1, q):
                r = apply_charge(inst, lab, de, next_id)
                if r.ok and r.label is not None:
                    next_id += 1
                    _push(r.label)

        for k in range(1, inst.wait_max_steps + 1):
            r = apply_wait(inst, lab, k, next_id)
            if r.ok and r.label is not None:
                next_id += 1
                _push(r.label)

    if best is not None and best_total is not None:
        path, actions = reconstruct(best)
        return SolveResult(
            status=SolverStatus.OPTIMAL,
            objective=best_total,
            path_nodes=path,
            actions=actions,
            final_label=best,
            stats=_stats(),
        )

    return SolveResult(
        status=SolverStatus.INFEASIBLE,
        objective=None,
        path_nodes=[],
        actions=[],
        final_label=None,
        stats=_stats(),
    )
