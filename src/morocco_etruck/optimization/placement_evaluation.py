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
from morocco_etruck.optimization.placement_cache import CachedMissionResult, PlacementMemo
from morocco_etruck.optimization.placement_certification import (
    ServiceabilityClass,
    is_peak_motor_reason,
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
    serviceability: str | None = None


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
        objective_mode=getattr(template_inst, "objective_mode", "enroute_incremental_cost"),
        terminal_target_truck_kwh=getattr(template_inst, "terminal_target_truck_kwh", None),
        terminal_target_trailer_kwh=getattr(template_inst, "terminal_target_trailer_kwh", None),
        terminal_price_cents_per_grid_kwh=getattr(
            template_inst, "terminal_price_cents_per_grid_kwh", None
        ),
        terminal_eta=getattr(template_inst, "terminal_eta", None),
        notes=template_inst.notes,
    )


def _result_from_cache(
    mission_id: str,
    active: set[str],
    is_struct: bool,
    cached: CachedMissionResult,
) -> MissionSolveResult:
    return MissionSolveResult(
        mission_id=mission_id,
        status=cached.status,
        served=cached.served,
        structural=is_struct,
        uncertified=cached.uncertified,
        objective_cents=cached.objective_cents,
        charge_kwh=cached.charge_kwh,
        charges=cached.charges,
        path=cached.path,
        continuous_replay_ok=cached.continuous_replay_ok,
        discrete_replay_ok=cached.discrete_replay_ok,
        active_stations=",".join(sorted(active)),
        reason=cached.reason,
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
    memo: PlacementMemo | None = None,
    skip_continuous_replay: bool = False,
) -> MissionSolveResult:
    active = active_keys_for_subset(sites, installed, mission.direction)
    is_struct = mission.id in structural_ids
    cache_key = None
    if memo is not None:
        cache_key = memo.make_key(
            mission_id=mission.id,
            active_station_keys=frozenset(active),
            price_mode=price_mode,
            q=template_inst.energy_quantum_kwh,
            time_step_min=template_inst.time_step_min,
        )
        hit = memo.get(cache_key)
        if hit is not None:
            return _result_from_cache(mission.id, active, is_struct, hit)

    inst = _clone_instance_for_subset(
        template_inst,
        active=active,
        price_mode=price_mode,
        ctx=ctx,
        name=f"{mission.id}:{','.join(sorted(installed)) or 'none'}",
    )
    _ = morocco_cfg

    result = solve_mrls(
        inst,
        use_dominance=True,
        max_seconds=max_seconds,
        max_expansions=max_expansions,
    )

    def _store(mr: MissionSolveResult) -> MissionSolveResult:
        if memo is not None and cache_key is not None:
            memo.put(
                cache_key,
                CachedMissionResult(
                    status=mr.status,
                    served=mr.served,
                    uncertified=mr.uncertified,
                    objective_cents=mr.objective_cents,
                    charge_kwh=mr.charge_kwh,
                    charges=mr.charges,
                    path=mr.path,
                    continuous_replay_ok=mr.continuous_replay_ok,
                    discrete_replay_ok=mr.discrete_replay_ok,
                    reason=mr.reason,
                ),
            )
        return mr

    if result.status == SolverStatus.LIMIT_REACHED:
        return _store(
            MissionSolveResult(
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
        )
    if result.status != SolverStatus.OPTIMAL or result.final_label is None:
        return _store(
            MissionSolveResult(
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
        )

    # Coupling: charges only at active stations
    for act in result.actions:
        if act.get("type") == "CHARGE" and act.get("node") not in active:
            return _store(
                MissionSolveResult(
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
            )

    disc = replay_solution(inst, result.actions, expected_cost=result.objective)
    if skip_continuous_replay:
        cont_ok = True
        cont_reason = None
    else:
        cont = continuous_replay(
            ctx,
            inst,
            result.actions,
            discrete_cost=result.objective,
            discrete_t=result.final_label.t,
            discrete_E_truck=result.final_label.E_truck,
        )
        cont_ok = cont.ok
        cont_reason = cont.reason
    served = bool(disc.ok and cont_ok)
    # OPTIMAL + failed discrete/continuous replay is unresolved for certification:
    # must not justify coverage/secondary B&B prunes (undercounted coverage).
    replay_uncert = not served
    return _store(
        MissionSolveResult(
            mission_id=mission.id,
            status=result.status.value,
            served=served,
            structural=is_struct,
            uncertified=replay_uncert,
            objective_cents=result.objective,
            charge_kwh=_charge_total(result.actions),
            charges=_charge_nodes(result.actions),
            path="->".join(result.path_nodes),
            continuous_replay_ok=cont_ok,
            discrete_replay_ok=disc.ok,
            active_stations=",".join(sorted(active)),
            reason=None if served else (cont_reason or disc.reason or "replay_invalid"),
        )
    )


def _peak_motor_from_tables(template_inst) -> bool:
    """True if any drive-table entry is infeasible specifically for peak motor."""
    for arc in template_inst.arcs:
        table = arc.drive_table or {}
        for entry in table.values():
            if entry.feasible:
                continue
            if is_peak_motor_reason(entry.reason):
                return True
    # Also: if ALL starts infeasible and majority peak-motor
    peak = 0
    bad = 0
    for arc in template_inst.arcs:
        table = arc.drive_table or {}
        for entry in table.values():
            if entry.feasible:
                continue
            bad += 1
            if is_peak_motor_reason(entry.reason):
                peak += 1
    return bad > 0 and peak >= max(1, bad // 2)


def classify_mission_serviceability(
    mission: PlacementMission,
    prepared: dict[str, tuple[MoroccoMissionContext, Any]],
    *,
    sites: list[PlacementSite],
    morocco_cfg: dict[str, Any],
    max_seconds: float,
    max_expansions: int,
) -> tuple[ServiceabilityClass, MissionSolveResult]:
    """
    Probe full direction-compatible install set for one mission.

    Classes: serviceable | peak_motor | unserved_all_candidates | limit_reached | replay_invalid
    """
    # Only sites matching mission direction count as "all candidates" for that mission
    dir_ids = {s.id for s in sites if s.direction == mission.direction}
    ctx, tmpl = prepared[mission.id]
    r = evaluate_mission_on_subset(
        mission,
        ctx,
        tmpl,
        installed=dir_ids,
        sites=sites,
        price_mode="uniform",
        morocco_cfg=morocco_cfg,
        structural_ids=set(),
        max_seconds=max_seconds,
        max_expansions=max_expansions,
    )
    if r.uncertified and r.status == "LIMIT_REACHED":
        cls = ServiceabilityClass.LIMIT_REACHED
    elif r.served:
        cls = ServiceabilityClass.SERVICEABLE
    elif r.status == "OPTIMAL" and (not r.continuous_replay_ok or not r.discrete_replay_ok):
        cls = ServiceabilityClass.REPLAY_INVALID
    elif is_peak_motor_reason(r.reason) or _peak_motor_from_tables(tmpl):
        # Unserved and tables / solve reason indicate peak motor under fixed speed
        cls = ServiceabilityClass.PEAK_MOTOR
    else:
        cls = ServiceabilityClass.UNSERVED_ALL_CANDIDATES
    r.serviceability = cls.value
    r.structural = cls == ServiceabilityClass.PEAK_MOTOR
    return cls, r


def classify_all_missions(
    missions: list[PlacementMission],
    prepared: dict[str, tuple[MoroccoMissionContext, Any]],
    *,
    sites: list[PlacementSite],
    morocco_cfg: dict[str, Any],
    max_seconds: float,
    max_expansions: int,
) -> dict[str, ServiceabilityClass]:
    """Classify every mission; peak_motor IDs form the structural reporting set."""
    out: dict[str, ServiceabilityClass] = {}
    for m in missions:
        cls, _ = classify_mission_serviceability(
            m,
            prepared,
            sites=sites,
            morocco_cfg=morocco_cfg,
            max_seconds=max_seconds,
            max_expansions=max_expansions,
        )
        out[m.id] = cls
    return out


def detect_structural_missions(
    missions: list[PlacementMission],
    prepared: dict[str, tuple[MoroccoMissionContext, Any]],
    *,
    sites: list[PlacementSite],
    morocco_cfg: dict[str, Any],
    max_seconds: float,
    max_expansions: int,
) -> set[str]:
    """Peak-motor missions only (power-policy structural infeasibility)."""
    classes = classify_all_missions(
        missions,
        prepared,
        sites=sites,
        morocco_cfg=morocco_cfg,
        max_seconds=max_seconds,
        max_expansions=max_expansions,
    )
    return {mid for mid, cls in classes.items() if cls == ServiceabilityClass.PEAK_MOTOR}


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
    memo: PlacementMemo | None = None,
    serviceable_ids: set[str] | None = None,
) -> SubsetEvaluation:
    """
    Evaluate one install set.

    Serviceable denominator = missions classified ``serviceable`` under the
    full-candidate probe (not merely ``not peak_motor``). Structural reporting
    remains ``peak_motor`` only via ``structural_ids``.
    """
    if serviceable_ids is None:
        # Backward-compatible fallback: treat non-structural as serviceable
        serviceable_ids = {m.id for m in missions if m.id not in structural_ids}
    rows: list[MissionSolveResult] = []
    certified = True
    cov = 0.0
    cov_serv = 0.0
    w_tot = sum(m.weight for m in missions)
    w_serv = sum(m.weight for m in missions if m.id in serviceable_ids)
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
            memo=memo,
        )
        rows.append(r)
        if r.uncertified:
            certified = False
        if r.served:
            cov += m.weight
            if m.id in serviceable_ids:
                cov_serv += m.weight
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
