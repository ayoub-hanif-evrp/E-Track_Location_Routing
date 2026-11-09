"""Exact exhaustive enumeration of directional charger subsets (Task 04A)."""

from __future__ import annotations

import itertools
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from morocco_etruck.optimization.morocco_adapter import load_pilot_config
from morocco_etruck.optimization.drive_table_cache import DRIVE_TABLE_CACHE_VERSION
from morocco_etruck.optimization.placement_cache import (
    PlacementMemo,
    default_energy_fingerprint,
)
from morocco_etruck.optimization.placement_certification import OptimalityStatus
from morocco_etruck.optimization.placement_evaluation import (
    SubsetEvaluation,
    classify_all_missions,
    detect_structural_missions,
    evaluate_subset,
    prepare_mission,
)
from morocco_etruck.optimization.placement_problem import (
    LexScore,
    PlacementConfig,
    PlacementMission,
    load_placement_config,
)
from morocco_etruck.road_network import load_graph_from_csv


def all_subsets(site_ids: list[str]) -> Iterable[frozenset[str]]:
    n = len(site_ids)
    for k in range(n + 1):
        for comb in itertools.combinations(site_ids, k):
            yield frozenset(comb)


@dataclass
class EnumerationResult:
    rows: list[dict[str, Any]]
    optimal_rows: list[dict[str, Any]]
    structural_ids: set[str]
    serviceability: dict[str, str] | None = None


def greedy_by_marginal_coverage(
    evaluations: list[SubsetEvaluation],
    *,
    site_ids: list[str],
    capex: dict[str, float],
    max_capex: float | None,
) -> SubsetEvaluation | None:
    """Simple greedy: add site with best coverage gain under budget (among evaluated subsets)."""
    # Prefer looking up evaluated subsets rather than re-solving
    by_set = {e.site_ids: e for e in evaluations if e.budget_ok and e.certified}
    chosen: set[str] = set()
    current = by_set.get(frozenset())
    if current is None:
        return None
    improved = True
    while improved:
        improved = False
        best_next = None
        best_eval = None
        best_gain = 0.0
        for s in site_ids:
            if s in chosen:
                continue
            cand = frozenset(chosen | {s})
            ev = by_set.get(cand)
            if ev is None:
                continue
            if max_capex is not None and ev.infra_capex > max_capex + 1e-9:
                continue
            gain = ev.coverage_serviceable - current.coverage_serviceable
            if gain > best_gain + 1e-12 or (
                abs(gain - best_gain) < 1e-12
                and best_eval is not None
                and ev.secondary_cost < best_eval.secondary_cost
            ):
                best_gain = gain
                best_next = s
                best_eval = ev
        if best_next is not None and best_eval is not None and best_gain > 0:
            chosen.add(best_next)
            current = best_eval
            improved = True
        elif best_next is not None and best_eval is not None and best_gain == 0:
            # Allow zero-gain if secondary cost improves
            if best_eval.secondary_cost + 1e-12 < current.secondary_cost:
                chosen.add(best_next)
                current = best_eval
                improved = True
    return current


def run_enumeration(
    cfg: PlacementConfig,
    *,
    root: Path,
    demand_name: str,
    capex_name: str,
    price_mode: str,
    G=None,
    max_subsets: int | None = None,
) -> EnumerationResult:
    morocco_cfg = load_pilot_config(cfg.morocco_pilot_path)
    if G is None:
        G = load_graph_from_csv(
            root / morocco_cfg["nodes_csv"],
            root / morocco_cfg["edges_csv"],
        )
    missions: list[PlacementMission] = list(cfg.demand_scenarios[demand_name])
    capex = cfg.capex_scenarios[capex_name]
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
    # Keep detect_structural_missions available for callers; assert consistency
    _ = detect_structural_missions

    site_ids = [s.id for s in cfg.sites]
    subsets = list(all_subsets(site_ids))
    if max_subsets is not None:
        subsets = subsets[: max_subsets]

    sample_inst = next(iter(prepared.values()))[1]
    memo = PlacementMemo(
        energy_model_fingerprint=default_energy_fingerprint(
            version=DRIVE_TABLE_CACHE_VERSION,
            q=sample_inst.energy_quantum_kwh,
            time_step_min=sample_inst.time_step_min,
        )
    )

    # Evaluate each subset once (budget filter applied when selecting optima)
    evals: list[SubsetEvaluation] = []
    for subset in subsets:
        ev = evaluate_subset(
            set(subset),
            cfg=cfg,
            missions=missions,
            prepared=prepared,
            structural_ids=structural_ids,
            capex=capex,
            max_capex=None,  # record all; filter per budget later
            price_mode=price_mode,
            morocco_cfg=morocco_cfg,
            memo=memo,
            serviceable_ids=serviceable_ids,
        )
        evals.append(ev)

    rows: list[dict[str, Any]] = []
    for ev in evals:
        for mr in ev.missions:
            rows.append(
                {
                    "demand_scenario": demand_name,
                    "capex_scenario": capex_name,
                    "price_mode": price_mode,
                    "sites": ",".join(sorted(ev.site_ids)) or "NONE",
                    "n_sites": len(ev.site_ids),
                    "infra_capex": ev.infra_capex,
                    "infra_annual": ev.infra_annual,
                    "coverage_total": ev.coverage_total,
                    "coverage_serviceable": ev.coverage_serviceable,
                    "weight_total": ev.weight_total,
                    "weight_serviceable": ev.weight_serviceable,
                    "variable_cost": ev.variable_cost,
                    "secondary_cost": ev.secondary_cost,
                    "subset_certified": ev.certified,
                    "mission_id": mr.mission_id,
                    "mission_status": mr.status,
                    "mission_served": mr.served,
                    "mission_structural": mr.mission_id in structural_ids,
                    "mission_uncertified": mr.uncertified,
                    "objective_cents": mr.objective_cents,
                    "charge_kwh": mr.charge_kwh,
                    "charges": mr.charges,
                    "path": mr.path,
                    "active_stations": mr.active_stations,
                    "continuous_replay_ok": mr.continuous_replay_ok,
                    "discrete_replay_ok": mr.discrete_replay_ok,
                    "reason": mr.reason,
                    "structural_ids": ",".join(sorted(structural_ids)),
                }
            )

    optimal_rows: list[dict[str, Any]] = []
    for bud in cfg.budgets:
        bname = bud["name"]
        max_c = bud.get("max_capex")

        def in_budget(e: SubsetEvaluation) -> bool:
            return max_c is None or e.infra_capex <= float(max_c) + 1e-9

        budget_evals = [e for e in evals if in_budget(e)]
        certified_pool = [e for e in budget_evals if e.certified]
        uncertified_pool = [e for e in budget_evals if not e.certified]

        if not budget_evals:
            optimal_rows.append(
                {
                    "demand_scenario": demand_name,
                    "capex_scenario": capex_name,
                    "price_mode": price_mode,
                    "budget_name": bname,
                    "max_capex": max_c,
                    "best_sites": "",
                    "optimality_status": OptimalityStatus.NO_FEASIBLE.value,
                    "certified": False,
                    "structural_ids": ",".join(sorted(structural_ids)),
                    "serviceability_json": str(serviceability),
                }
            )
            continue

        # Lex-best among certified budget-feasible; else among all (unproved)
        pool = certified_pool if certified_pool else budget_evals
        best = min(
            pool,
            key=lambda e: LexScore.from_parts(
                e.coverage_serviceable, e.secondary_cost, e.certified
            ),
        )
        # Global certificate: all budget-feasible subsets certified (or none unresolved)
        if uncertified_pool:
            # Without proved dominance bounds over unresolved competitors, cannot certify
            opt_status = OptimalityStatus.INCUMBENT_UNPROVED.value
            globally_certified = False
        elif certified_pool:
            opt_status = OptimalityStatus.CERTIFIED_OPTIMAL.value
            globally_certified = True
        else:
            opt_status = OptimalityStatus.INCUMBENT_UNPROVED.value
            globally_certified = False

        greedy = greedy_by_marginal_coverage(
            evals, site_ids=site_ids, capex=capex, max_capex=None if max_c is None else float(max_c)
        )
        baseline_gap = {}
        for bname_bl, bl_sites in cfg.baselines.items():
            bl_set = frozenset(bl_sites)
            bl_ev = next((e for e in evals if e.site_ids == bl_set), None)
            if bl_ev is None:
                continue
            if max_c is not None and bl_ev.infra_capex > float(max_c) + 1e-9:
                baseline_gap[bname_bl] = "over_budget"
            else:
                baseline_gap[bname_bl] = {
                    "coverage_serviceable": bl_ev.coverage_serviceable,
                    "secondary_cost": bl_ev.secondary_cost,
                    "cov_gap": best.coverage_serviceable - bl_ev.coverage_serviceable,
                    "cost_gap": bl_ev.secondary_cost - best.secondary_cost,
                }

        optimal_rows.append(
            {
                "demand_scenario": demand_name,
                "capex_scenario": capex_name,
                "price_mode": price_mode,
                "budget_name": bname,
                "max_capex": max_c,
                "best_sites": ",".join(sorted(best.site_ids)) or "NONE",
                "n_sites": len(best.site_ids),
                "coverage_serviceable": best.coverage_serviceable,
                "coverage_total": best.coverage_total,
                "weight_serviceable": best.weight_serviceable,
                "infra_capex": best.infra_capex,
                "infra_annual": best.infra_annual,
                "variable_cost": best.variable_cost,
                "secondary_cost": best.secondary_cost,
                "certified": globally_certified and best.certified,
                "optimality_status": opt_status,
                "n_uncertified_competitors": len(uncertified_pool),
                "greedy_sites": ",".join(sorted(greedy.site_ids)) if greedy else "",
                "greedy_coverage": greedy.coverage_serviceable if greedy else None,
                "greedy_secondary": greedy.secondary_cost if greedy else None,
                "greedy_cov_gap": (
                    best.coverage_serviceable - greedy.coverage_serviceable if greedy else None
                ),
                "baselines_json": str(baseline_gap),
                "structural_ids": ",".join(sorted(structural_ids)),
                "serviceability_json": str(serviceability),
            }
        )

    return EnumerationResult(
        rows=rows,
        optimal_rows=optimal_rows,
        structural_ids=structural_ids,
        serviceability=serviceability,
    )


def load_configs(placement_yaml: Path, root: Path) -> PlacementConfig:
    return load_placement_config(placement_yaml, root=root)
