"""Certified charger-placement branch-and-bound with MRLS leaf evaluation (Task 04B)."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable

from morocco_etruck.optimization.drive_table_cache import DRIVE_TABLE_CACHE_VERSION
from morocco_etruck.optimization.morocco_adapter import load_pilot_config
from morocco_etruck.optimization.placement_bounds import (
    budget_infeasible,
    can_prune_coverage,
    can_prune_secondary,
    coverage_upper_bound,
)
from morocco_etruck.optimization.placement_cache import (
    PlacementMemo,
    portfolio_energy_fingerprint,
)
from morocco_etruck.optimization.placement_certification import OptimalityStatus
from morocco_etruck.optimization.placement_evaluation import (
    SubsetEvaluation,
    classify_all_missions,
    evaluate_subset,
    prepare_mission,
)
from morocco_etruck.optimization.placement_problem import (
    LexScore,
    PlacementConfig,
    PlacementMission,
)
from morocco_etruck.road_network import load_graph_from_csv


class NodeStatus(str, Enum):
    OPEN = "open"
    PRUNED_BUDGET = "pruned_budget"
    PRUNED_COVERAGE = "pruned_coverage"
    PRUNED_SECONDARY = "pruned_secondary"
    LEAF_EVALUATED = "leaf_evaluated"
    INCUMBENT = "incumbent"


@dataclass
class BBNode:
    installed: frozenset[str]
    excluded: frozenset[str]
    undecided: frozenset[str]
    committed_capex: float
    depth: int
    last_branch: tuple[str, str] | None = None  # (site_id, "install"|"exclude")
    status: NodeStatus = NodeStatus.OPEN


@dataclass
class BranchAndBoundStats:
    nodes_visited: int = 0
    nodes_expanded: int = 0
    leaves_evaluated: int = 0
    prune_budget: int = 0
    prune_coverage: int = 0
    prune_secondary: int = 0
    mrls_calls: int = 0
    mrls_cache_hits: int = 0
    uncertified_bounds: int = 0
    runtime_sec: float = 0.0
    limit_reached: bool = False


@dataclass
class BranchAndBoundResult:
    optimality_status: OptimalityStatus
    incumbent: SubsetEvaluation | None
    stats: BranchAndBoundStats
    structural_ids: set[str]
    serviceability: dict[str, str]
    rows: list[dict[str, Any]] = field(default_factory=list)


def _next_branch_site(undecided: frozenset[str]) -> str:
    """Deterministic site order by id (heuristic only)."""
    return sorted(undecided)[0]


def _lex_better(cand: SubsetEvaluation, incumbent: SubsetEvaluation | None) -> bool:
    if incumbent is None:
        return cand.certified  # only accept certified incumbents for proved search
    if not cand.certified:
        return False
    return LexScore.from_parts(
        cand.coverage_serviceable, cand.secondary_cost, cand.certified
    ) < LexScore.from_parts(
        incumbent.coverage_serviceable, incumbent.secondary_cost, incumbent.certified
    )


def run_branch_and_bound_core(
    *,
    site_ids: list[str],
    capex: dict[str, float],
    max_capex: float | None,
    crf: float,
    evaluate_fn: Callable[[set[str]], SubsetEvaluation],
    memo: PlacementMemo | None = None,
    node_limit: int | None = None,
    time_limit_sec: float | None = None,
    install_first: bool = True,
) -> BranchAndBoundResult:
    """
    Best-bound / DFS B&B over install/exclude decisions.

    Uses proved budget, coverage UB, and secondary LB pruning. Uncertified
    bounds never prune. Search terminates CERTIFIED_OPTIMAL only if every open
    node is resolved / pruned by proved bounds and no LIMIT_REACHED remains.

    ``install_first`` is a search heuristic only (child stack order).
    """
    t0 = time.perf_counter()
    stats = BranchAndBoundStats()
    root = BBNode(
        installed=frozenset(),
        excluded=frozenset(),
        undecided=frozenset(site_ids),
        committed_capex=0.0,
        depth=0,
    )
    open_nodes: list[BBNode] = [root]
    incumbent: SubsetEvaluation | None = None
    had_uncertified_leaf = False
    stopped_early = False

    while open_nodes:
        if node_limit is not None and stats.nodes_visited >= node_limit:
            stopped_early = True
            stats.limit_reached = True
            break
        if time_limit_sec is not None and (time.perf_counter() - t0) >= time_limit_sec:
            stopped_early = True
            stats.limit_reached = True
            break

        N = open_nodes.pop()
        stats.nodes_visited += 1

        if budget_infeasible(set(N.installed), capex, max_capex):
            N.status = NodeStatus.PRUNED_BUDGET
            stats.prune_budget += 1
            continue

        if not N.undecided:
            ev = evaluate_fn(set(N.installed))
            stats.leaves_evaluated += 1
            if not ev.certified:
                had_uncertified_leaf = True
            if max_capex is not None and ev.infra_capex > float(max_capex) + 1e-9:
                N.status = NodeStatus.LEAF_EVALUATED
                continue
            if _lex_better(ev, incumbent):
                incumbent = ev
                N.status = NodeStatus.INCUMBENT
            else:
                N.status = NodeStatus.LEAF_EVALUATED
            continue

        # Coverage UB on installed ∪ undecided (budget relaxed)
        ub = coverage_upper_bound(
            installed=set(N.installed),
            undecided=set(N.undecided),
            evaluate_fn=evaluate_fn,
        )
        if not ub.ub_certified:
            stats.uncertified_bounds += 1
            # Cannot prune — must branch
        else:
            cov_star = None if incumbent is None else incumbent.coverage_serviceable
            if can_prune_coverage(ub=ub, incumbent_coverage=cov_star):
                N.status = NodeStatus.PRUNED_COVERAGE
                stats.prune_coverage += 1
                continue
            if incumbent is not None:
                prune_sec, _lb = can_prune_secondary(
                    ub=ub,
                    installed=set(N.installed),
                    capex=capex,
                    crf=crf,
                    incumbent_coverage=incumbent.coverage_serviceable,
                    incumbent_secondary=incumbent.secondary_cost,
                )
                if prune_sec:
                    N.status = NodeStatus.PRUNED_SECONDARY
                    stats.prune_secondary += 1
                    continue

        # Branch
        stats.nodes_expanded += 1
        s = _next_branch_site(N.undecided)
        remaining = N.undecided - {s}

        child_install = BBNode(
            installed=N.installed | {s},
            excluded=N.excluded,
            undecided=remaining,
            committed_capex=N.committed_capex + float(capex[s]),
            depth=N.depth + 1,
            last_branch=(s, "install"),
        )
        child_exclude = BBNode(
            installed=N.installed,
            excluded=N.excluded | {s},
            undecided=remaining,
            committed_capex=N.committed_capex,
            depth=N.depth + 1,
            last_branch=(s, "exclude"),
        )
        # DFS child order is a heuristic only
        if install_first:
            open_nodes.append(child_exclude)
            open_nodes.append(child_install)
        else:
            open_nodes.append(child_install)
            open_nodes.append(child_exclude)

    stats.runtime_sec = time.perf_counter() - t0
    if memo is not None:
        st = memo.stats()
        stats.mrls_cache_hits = int(st["hits"])
        stats.mrls_calls = int(st["hits"]) + int(st["misses"])

    if stopped_early or open_nodes:
        status = OptimalityStatus.LIMIT_REACHED
    elif had_uncertified_leaf:
        # Unresolved / uncertified leaf competitors prevent global certificate
        status = OptimalityStatus.INCUMBENT_UNPROVED
    elif incumbent is None:
        status = OptimalityStatus.NO_FEASIBLE
    else:
        status = OptimalityStatus.CERTIFIED_OPTIMAL

    return BranchAndBoundResult(
        optimality_status=status,
        incumbent=incumbent,
        stats=stats,
        structural_ids=set(),
        serviceability={},
    )


def prepare_placement_context(
    cfg: PlacementConfig,
    *,
    root: Path,
    demand_name: str,
    G=None,
    memo: PlacementMemo | None = None,
) -> dict[str, Any]:
    """Shared prep (graph tables, serviceability, memo) across budgets."""
    morocco_cfg = load_pilot_config(cfg.morocco_pilot_path)
    if G is None:
        G = load_graph_from_csv(
            root / morocco_cfg["nodes_csv"],
            root / morocco_cfg["edges_csv"],
        )
    missions: list[PlacementMission] = list(cfg.demand_scenarios[demand_name])
    table_cache = root / cfg.outputs.get("table_cache_dir", "data/processed/optimization/drive_tables")
    prepared = {}
    for m in missions:
        prepared[m.id] = prepare_mission(
            m, morocco_cfg, root=root, G=G, table_cache_dir=table_cache
        )
    serviceability = {
        mid: cls.value
        for mid, cls in classify_all_missions(
            missions,
            prepared,
            sites=cfg.sites,
            morocco_cfg=morocco_cfg,
            max_seconds=cfg.solver_max_seconds,
            max_expansions=cfg.solver_max_expansions,
        ).items()
    }
    structural_ids = {mid for mid, v in serviceability.items() if v == "peak_motor"}
    serviceable_ids = {mid for mid, v in serviceability.items() if v == "serviceable"}
    if memo is None:
        sample = next(iter(prepared.values()))[1]
        memo = PlacementMemo(
            energy_model_fingerprint=portfolio_energy_fingerprint(
                missions,
                version=DRIVE_TABLE_CACHE_VERSION,
                q=sample.energy_quantum_kwh,
                time_step_min=sample.time_step_min,
                vehicle_yaml=root / morocco_cfg["vehicle_config"],
                fridge_yaml=root / morocco_cfg["refrigeration_config"],
            )
        )
    return {
        "G": G,
        "morocco_cfg": morocco_cfg,
        "missions": missions,
        "prepared": prepared,
        "serviceability": serviceability,
        "structural_ids": structural_ids,
        "serviceable_ids": serviceable_ids,
        "memo": memo,
    }


def run_branch_and_bound(
    cfg: PlacementConfig,
    *,
    root: Path,
    demand_name: str,
    capex_name: str,
    price_mode: str,
    budget_name: str,
    G=None,
    memo: PlacementMemo | None = None,
    node_limit: int | None = None,
    time_limit_sec: float | None = None,
    context: dict[str, Any] | None = None,
) -> BranchAndBoundResult:
    if context is None:
        context = prepare_placement_context(
            cfg, root=root, demand_name=demand_name, G=G, memo=memo
        )
    morocco_cfg = context["morocco_cfg"]
    missions = context["missions"]
    prepared = context["prepared"]
    serviceability = context["serviceability"]
    structural_ids = context["structural_ids"]
    serviceable_ids = context.get("serviceable_ids") or {
        mid for mid, v in serviceability.items() if v == "serviceable"
    }
    memo = context["memo"] if memo is None else memo
    capex = cfg.capex_scenarios[capex_name]
    bud = next(b for b in cfg.budgets if b["name"] == budget_name)
    max_c = bud.get("max_capex")

    eval_count = {"n": 0}

    def evaluate_fn(installed: set[str]) -> SubsetEvaluation:
        eval_count["n"] += 1
        return evaluate_subset(
            installed,
            cfg=cfg,
            missions=missions,
            prepared=prepared,
            structural_ids=structural_ids,
            capex=capex,
            max_capex=max_c if max_c is None else float(max_c),
            price_mode=price_mode,
            morocco_cfg=morocco_cfg,
            memo=memo,
            serviceable_ids=serviceable_ids,
        )

    site_ids = [s.id for s in cfg.sites]
    core = run_branch_and_bound_core(
        site_ids=site_ids,
        capex=capex,
        max_capex=None if max_c is None else float(max_c),
        crf=cfg.crf,
        evaluate_fn=evaluate_fn,
        memo=memo,
        node_limit=node_limit,
        time_limit_sec=time_limit_sec,
    )
    core.structural_ids = structural_ids
    core.serviceability = serviceability
    core.stats.mrls_calls = max(core.stats.mrls_calls, eval_count["n"])
    if core.incumbent is not None:
        core.rows.append(
            {
                "demand_scenario": demand_name,
                "capex_scenario": capex_name,
                "price_mode": price_mode,
                "budget_name": budget_name,
                "max_capex": max_c,
                "best_sites": ",".join(sorted(core.incumbent.site_ids)) or "NONE",
                "n_sites": len(core.incumbent.site_ids),
                "coverage_serviceable": core.incumbent.coverage_serviceable,
                "coverage_total": core.incumbent.coverage_total,
                "weight_serviceable": core.incumbent.weight_serviceable,
                "infra_capex": core.incumbent.infra_capex,
                "infra_annual": core.incumbent.infra_annual,
                "variable_cost": core.incumbent.variable_cost,
                "secondary_cost": core.incumbent.secondary_cost,
                "optimality_status": core.optimality_status.value,
                "certified": core.optimality_status == OptimalityStatus.CERTIFIED_OPTIMAL,
                "nodes_visited": core.stats.nodes_visited,
                "nodes_expanded": core.stats.nodes_expanded,
                "leaves_evaluated": core.stats.leaves_evaluated,
                "prune_budget": core.stats.prune_budget,
                "prune_coverage": core.stats.prune_coverage,
                "prune_secondary": core.stats.prune_secondary,
                "mrls_calls": core.stats.mrls_calls,
                "mrls_cache_hits": core.stats.mrls_cache_hits,
                "runtime_sec": core.stats.runtime_sec,
                "structural_ids": ",".join(sorted(structural_ids)),
                "serviceability_json": str(serviceability),
            }
        )
    else:
        core.rows.append(
            {
                "demand_scenario": demand_name,
                "capex_scenario": capex_name,
                "price_mode": price_mode,
                "budget_name": budget_name,
                "max_capex": max_c,
                "best_sites": "",
                "optimality_status": core.optimality_status.value,
                "certified": False,
                "nodes_visited": core.stats.nodes_visited,
                "prune_budget": core.stats.prune_budget,
                "prune_coverage": core.stats.prune_coverage,
                "prune_secondary": core.stats.prune_secondary,
                "runtime_sec": core.stats.runtime_sec,
                "structural_ids": ",".join(sorted(structural_ids)),
                "serviceability_json": str(serviceability),
            }
        )
    return core
