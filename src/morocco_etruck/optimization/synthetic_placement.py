"""Synthetic placement instances for B&B pruning demos (not Moroccan traffic)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from morocco_etruck.optimization.instances import instance_from_dict
from morocco_etruck.optimization.label_setting import SolverStatus, solve_mrls
from morocco_etruck.optimization.placement_evaluation import MissionSolveResult, SubsetEvaluation
from morocco_etruck.optimization.placement_problem import (
    PlacementMission,
    PlacementSite,
    annualized_infra_cost,
    budget_ok,
    capital_recovery_factor,
)
from morocco_etruck.optimization.problem import RoutingInstance, StationData
from morocco_etruck.optimization.replay import replay_solution


@dataclass
class SyntheticPlacementProblem:
    sites: list[PlacementSite]
    missions: list[PlacementMission]
    templates: dict[str, RoutingInstance]
    site_to_station: dict[str, str]
    capex: dict[str, float]
    crf: float
    cents_to_currency: float
    budgets: list[dict[str, Any]]
    max_seconds: float
    max_expansions: int
    note: str = ""


def load_synthetic_placement(path: Path) -> SyntheticPlacementProblem:
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    sites = [
        PlacementSite(
            id=str(s["id"]),
            direction=str(s.get("direction", "synth")),
            station_key=str(s["station_key"]),
            label=str(s.get("label", s["id"])),
        )
        for s in raw["sites"]
    ]
    site_to_station = {s.id: s.station_key for s in sites}
    missions = [
        PlacementMission(
            id=str(m["id"]),
            direction=str(m.get("direction", "synth")),
            gcm="synth",
            terrain="flat",
            weather="cool",
            refrigeration="off",
            power_source="A",
            weight=float(m["weight"]),
            structural_candidate=False,
        )
        for m in raw["missions"]
    ]
    templates = {str(item["name"]): instance_from_dict(item) for item in raw["mission_instances"]}
    ann = raw.get("annualization", {"interest_rate": 0.08, "lifetime_years": 15})
    crf = capital_recovery_factor(ann["interest_rate"], ann["lifetime_years"])
    return SyntheticPlacementProblem(
        sites=sites,
        missions=missions,
        templates=templates,
        site_to_station=site_to_station,
        capex={str(k): float(v) for k, v in raw["site_capex"].items()},
        crf=crf,
        cents_to_currency=float(raw.get("cents_to_currency", 0.01)),
        budgets=list(raw["budgets"]),
        max_seconds=float(raw.get("solver", {}).get("max_seconds", 30.0)),
        max_expansions=int(raw.get("solver", {}).get("max_expansions", 200_000)),
        note=str(raw.get("note", "synthetic")),
    )


def _clone_active(inst: RoutingInstance, active: set[str]) -> RoutingInstance:
    stations = {
        k: StationData(
            node=st.node,
            power_kw=st.power_kw,
            eta=st.eta,
            price_cents_per_grid_kwh=st.price_cents_per_grid_kwh,
            compatible=st.compatible,
        )
        for k, st in inst.stations.items()
    }
    return RoutingInstance(
        name=inst.name,
        nodes=list(inst.nodes),
        arcs=list(inst.arcs),
        origin=inst.origin,
        destination=inst.destination,
        deadline_steps=inst.deadline_steps,
        E_truck_cap=inst.E_truck_cap,
        E_truck_min=inst.E_truck_min,
        E_truck_init=inst.E_truck_init,
        E_trailer_cap=inst.E_trailer_cap,
        E_trailer_min=inst.E_trailer_min,
        E_trailer_init=inst.E_trailer_init,
        stations=stations,
        active_stations=set(active),
        power_source=inst.power_source,
        refrigeration_on=inst.refrigeration_on,
        aux_kwh_per_step=inst.aux_kwh_per_step,
        tru_kwh_per_step=inst.tru_kwh_per_step,
        wait_max_steps=inst.wait_max_steps,
        time_step_min=inst.time_step_min,
        energy_quantum_kwh=inst.energy_quantum_kwh,
        notes=inst.notes,
    )


def evaluate_synthetic_subset(
    installed: set[str],
    problem: SyntheticPlacementProblem,
    *,
    max_capex: float | None = None,
) -> SubsetEvaluation:
    installed_stations = {
        problem.site_to_station[s] for s in installed if s in problem.site_to_station
    }
    rows: list[MissionSolveResult] = []
    certified = True
    cov = 0.0
    var = 0.0
    w_tot = sum(m.weight for m in problem.missions)
    for m in problem.missions:
        tmpl = problem.templates[m.id]
        # Only activate stations that exist on this mission's graph
        active = installed_stations & set(tmpl.stations.keys())
        inst = _clone_active(tmpl, active)
        result = solve_mrls(
            inst,
            use_dominance=True,
            max_seconds=problem.max_seconds,
            max_expansions=problem.max_expansions,
        )
        if result.status == SolverStatus.LIMIT_REACHED:
            certified = False
            rows.append(
                MissionSolveResult(
                    mission_id=m.id,
                    status=result.status.value,
                    served=False,
                    structural=False,
                    uncertified=True,
                    objective_cents=result.objective,
                    charge_kwh=0,
                    charges="",
                    path="",
                    continuous_replay_ok=False,
                    discrete_replay_ok=False,
                    active_stations=",".join(sorted(active)),
                    reason="LIMIT_REACHED",
                )
            )
            continue
        if result.status != SolverStatus.OPTIMAL or result.final_label is None:
            rows.append(
                MissionSolveResult(
                    mission_id=m.id,
                    status=result.status.value,
                    served=False,
                    structural=False,
                    uncertified=False,
                    objective_cents=result.objective,
                    charge_kwh=0,
                    charges="",
                    path="",
                    continuous_replay_ok=False,
                    discrete_replay_ok=False,
                    active_stations=",".join(sorted(active)),
                    reason=result.status.value,
                )
            )
            continue
        disc = replay_solution(inst, result.actions, expected_cost=result.objective)
        served = bool(disc.ok)
        if served:
            cov += m.weight
            if result.objective is not None:
                var += m.weight * result.objective * problem.cents_to_currency
        rows.append(
            MissionSolveResult(
                mission_id=m.id,
                status=result.status.value,
                served=served,
                structural=False,
                uncertified=False,
                objective_cents=result.objective,
                charge_kwh=0,
                charges="",
                path="->".join(result.path_nodes),
                continuous_replay_ok=True,  # synthetic: discrete-only certificate
                discrete_replay_ok=disc.ok,
                active_stations=",".join(sorted(active)),
                reason=None if served else disc.reason,
            )
        )
    infra_c = sum(problem.capex[s] for s in installed)
    infra_a = annualized_infra_cost(installed, problem.capex, problem.crf)
    return SubsetEvaluation(
        site_ids=frozenset(installed),
        budget_ok=budget_ok(installed, problem.capex, max_capex),
        certified=certified,
        coverage_total=cov,
        coverage_serviceable=cov,
        weight_total=w_tot,
        weight_serviceable=w_tot,
        infra_capex=infra_c,
        infra_annual=infra_a,
        variable_cost=var,
        secondary_cost=infra_a + var,
        missions=rows,
    )
