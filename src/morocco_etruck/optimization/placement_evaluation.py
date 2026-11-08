"""Evaluate one infrastructure subset on a mission portfolio (Task 04A)."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from morocco_etruck.optimization.continuous_replay import continuous_replay
from morocco_etruck.optimization.label_setting import SolverStatus, solve_mrls
from morocco_etruck.optimization.morocco_adapter import (
    MoroccoMissionContext,
    build_mission_context,
    build_routing_instance,
    load_pilot_config,
)
from morocco_etruck.optimization.placement_problem import (
    PlacementConfig,
    PlacementMission,
    PlacementSite,
    annualized_infra_cost,
    budget_ok,
)
from morocco_etruck.optimization.replay import replay_solution


@dataclass
class MissionSolveResult:
    mission_id: str
    status: str
    served: bool
    structural: bool
    uncertified: bool
    objective_cents: int | None
    charge_kwh: int
    charges: str
    path: str
    continuous_replay_ok: bool
    discrete_replay_ok: bool
    active_stations: str
    reason: str | None = None


@dataclass
class SubsetEvaluation:
    site_ids: frozenset[str]
    budget_ok: bool
    certified: bool
    coverage_total: float
    coverage_serviceable: float
    weight_total: float
    weight_serviceable: float
    infra_capex: float
    infra_annual: float
    variable_cost: float
    secondary_cost: float
    missions: list[MissionSolveResult] = field(default_factory=list)


def sites_for_direction(sites: list[PlacementSite], direction: str) -> list[PlacementSite]:
    return [s for s in sites if s.direction == direction]


def active_keys_for_subset(
    sites: list[PlacementSite],
    installed: set[str],
    direction: str,
) -> set[str]:
    return {s.station_key for s in sites if s.id in installed and s.direction == direction}


def _charge_total(actions: list) -> int:
    return sum(int(a.get("delta_e_kwh", 0)) for a in actions if a.get("type") == "CHARGE")


def _charge_nodes(actions: list) -> str:
    return ";".join(
        f"{a['node']}:{a['delta_e_kwh']}" for a in actions if a.get("type") == "CHARGE"
    )


def prepare_mission(
    mission: PlacementMission,
    morocco_cfg: dict[str, Any],
    *,
    root: Path,
    G,
    table_cache_dir: Path | None,
) -> tuple[MoroccoMissionContext, Any]:
    """Build context once; return a template instance with no active stations."""
    ctx = build_mission_context(
        morocco_cfg,
        direction=mission.direction,
        gcm=mission.gcm,
        weather_id=mission.weather,
        terrain=mission.terrain,
        refrigeration=mission.refrigeration,
        power_source=mission.power_source,
        root=root,
        G=G,
    )
    # Build tables with empty active set (tables independent of active stations)
    inst = build_routing_instance(
        ctx,
        active_stations=set(),
        price_mode="uniform",
        name=mission.id,
        table_cache_dir=table_cache_dir,
    )
    return ctx, inst


def _clone_instance_for_subset(template_inst, *, active: set[str], price_mode: str, ctx: MoroccoMissionContext, name: str):
    """Reuse DRIVE tables; only active stations and prices change across subsets."""
    from morocco_etruck.optimization.morocco_adapter import _station_price
    from morocco_etruck.optimization.problem import RoutingInstance, StationData

    stations: dict[str, StationData] = {}
    for key, st in template_inst.stations.items():
        stations[key] = StationData(
            node=st.node,
            power_kw=st.power_kw,
            eta=st.eta,
            price_cents_per_grid_kwh=_station_price(ctx.cfg, key, price_mode),
            compatible=st.compatible,
            official_name=st.official_name,
            hypothetical_access=st.hypothetical_access,
            hgv_status=st.hgv_status,
            osm_id=st.osm_id,
            snap_distance_m=st.snap_distance_m,
        )
    return RoutingInstance(
        name=name,
        nodes=list(template_inst.nodes),
        arcs=list(template_inst.arcs),
        origin=template_inst.origin,
        destination=template_inst.destination,
        deadline_steps=template_inst.deadline_steps,
        E_truck_cap=template_inst.E_truck_cap,
        E_truck_min=template_inst.E_truck_min,
        E_truck_init=template_inst.E_truck_init,
        E_trailer_cap=template_inst.E_trailer_cap,
        E_trailer_min=template_inst.E_trailer_min,
        E_trailer_init=template_inst.E_trailer_init,
        stations=stations,
        active_stations=set(active),
        power_source=template_inst.power_source,
        refrigeration_on=template_inst.refrigeration_on,
        aux_kwh_per_step=template_inst.aux_kwh_per_step,
        tru_kwh_per_step=template_inst.tru_kwh_per_step,
        aux_w=template_inst.aux_w,
        tru_mean_w=template_inst.tru_mean_w,
        wait_max_steps=template_inst.wait_max_steps,
        time_step_min=template_inst.time_step_min,
        energy_quantum_kwh=template_inst.energy_quantum_kwh,
        notes=template_inst.notes,
    )


def evaluate_mission_on_subset(
    mission: PlacementMission,
    ctx: MoroccoMissionContext,
    template_inst,
    *,
    installed: set[str],
    sites: list[PlacementSite],
    price_mode: str,
    morocco_cfg: dict[str, Any],
    structural_ids: set[str],
    max_seconds: float,
    max_expansions: int,
) -> MissionSolveResult:
    active = active_keys_for_subset(sites, installed, mission.direction)
    inst = _clone_instance_for_subset(
        template_inst,
        active=active,
        price_mode=price_mode,
        ctx=ctx,
        name=f"{mission.id}:{','.join(sorted(installed)) or 'none'}",
    )
    _ = morocco_cfg

    is_struct = mission.id in structural_ids
    result = solve_mrls(
        inst,
        use_dominance=True,
        max_seconds=max_seconds,
        max_expansions=max_expansions,
    )
    if result.status == SolverStatus.LIMIT_REACHED:
        return MissionSolveResult(
            mission_id=mission.id,
            status=result.status.value,
            served=False,
            structural=is_struct,
            uncertified=True,
            objective_cents=result.objective,
            charge_kwh=_charge_total(result.actions),
            charges=_charge_nodes(result.actions),
            path="->".join(result.path_nodes),
            continuous_replay_ok=False,
            discrete_replay_ok=False,
            active_stations=",".join(sorted(active)),
            reason="LIMIT_REACHED",
        )
    if result.status != SolverStatus.OPTIMAL or result.final_label is None:
        return MissionSolveResult(
            mission_id=mission.id,
            status=result.status.value,
            served=False,
            structural=is_struct,
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

    # Coupling: charges only at active stations
    for act in result.actions:
        if act.get("type") == "CHARGE" and act.get("node") not in active:
            return MissionSolveResult(
                mission_id=mission.id,
                status="COUPLING_FAIL",
                served=False,
                structural=is_struct,
                uncertified=True,
                objective_cents=result.objective,
                charge_kwh=_charge_total(result.actions),
                charges=_charge_nodes(result.actions),
                path="->".join(result.path_nodes),
                continuous_replay_ok=False,
                discrete_replay_ok=False,
                active_stations=",".join(sorted(active)),
                reason="charge_at_inactive",
            )

    disc = replay_solution(inst, result.actions, expected_cost=result.objective)
    cont = continuous_replay(
        ctx,
        inst,
        result.actions,
        discrete_cost=result.objective,
        discrete_t=result.final_label.t,
        discrete_E_truck=result.final_label.E_truck,
    )
    served = bool(disc.ok and cont.ok)
    return MissionSolveResult(
        mission_id=mission.id,
        status=result.status.value,
        served=served,
        structural=is_struct,
        uncertified=False,
        objective_cents=result.objective,
        charge_kwh=_charge_total(result.actions),
        charges=_charge_nodes(result.actions),
        path="->".join(result.path_nodes),
        continuous_replay_ok=cont.ok,
        discrete_replay_ok=disc.ok,
        active_stations=",".join(sorted(active)),
        reason=None if served else (cont.reason or disc.reason),
    )


def detect_structural_missions(
    missions: list[PlacementMission],
    prepared: dict[str, tuple[MoroccoMissionContext, Any]],
    *,
    sites: list[PlacementSite],
    morocco_cfg: dict[str, Any],
    max_seconds: float,
    max_expansions: int,
) -> set[str]:
    """Missions infeasible even with all direction-matched sites installed."""
    all_ids = {s.id for s in sites}
    structural: set[str] = set()
    for m in missions:
        if not m.structural_candidate:
            continue
        ctx, tmpl = prepared[m.id]
        r = evaluate_mission_on_subset(
            m,
            ctx,
            tmpl,
            installed=all_ids,
            sites=sites,
            price_mode="uniform",
            morocco_cfg=morocco_cfg,
            structural_ids=set(),
            max_seconds=max_seconds,
            max_expansions=max_expansions,
        )
        if not r.served:
            structural.add(m.id)
    return structural


def evaluate_subset(
    installed: set[str],
    *,
    cfg: PlacementConfig,
    missions: list[PlacementMission],
    prepared: dict[str, tuple[MoroccoMissionContext, Any]],
    structural_ids: set[str],
    capex: dict[str, float],
    max_capex: float | None,
    price_mode: str,
    morocco_cfg: dict[str, Any],
) -> SubsetEvaluation:
    rows: list[MissionSolveResult] = []
    certified = True
    cov = 0.0
    cov_serv = 0.0
    w_tot = sum(m.weight for m in missions)
    w_serv = sum(m.weight for m in missions if m.id not in structural_ids)
    var = 0.0
    for m in missions:
        ctx, tmpl = prepared[m.id]
        r = evaluate_mission_on_subset(
            m,
            ctx,
            tmpl,
            installed=installed,
            sites=cfg.sites,
            price_mode=price_mode,
            morocco_cfg=morocco_cfg,
            structural_ids=structural_ids,
            max_seconds=cfg.solver_max_seconds,
            max_expansions=cfg.solver_max_expansions,
        )
        rows.append(r)
        if r.uncertified:
            certified = False
        if r.served and m.id not in structural_ids:
            cov += m.weight
            cov_serv += m.weight
            if r.objective_cents is not None:
                var += m.weight * r.objective_cents * cfg.cents_to_currency
        elif r.served and m.id in structural_ids:
            # Should not happen if structural detection is correct
            cov += m.weight
            if r.objective_cents is not None:
                var += m.weight * r.objective_cents * cfg.cents_to_currency

    infra_c = sum(capex[s] for s in installed)
    infra_a = annualized_infra_cost(installed, capex, cfg.crf)
    return SubsetEvaluation(
        site_ids=frozenset(installed),
        budget_ok=budget_ok(installed, capex, max_capex),
        certified=certified,
        coverage_total=cov,
        coverage_serviceable=cov_serv,
        weight_total=w_tot,
        weight_serviceable=w_serv,
        infra_capex=infra_c,
        infra_annual=infra_a,
        variable_cost=var,
        secondary_cost=infra_a + var,
        missions=rows,
    )
