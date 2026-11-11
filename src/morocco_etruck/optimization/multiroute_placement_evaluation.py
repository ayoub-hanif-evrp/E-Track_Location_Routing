"""Evaluate infrastructure subsets on multi-route physics MRLS templates (Task 05C)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from morocco_etruck.optimization.branch_and_bound import (
    BranchAndBoundResult,
    run_branch_and_bound_core,
)
from morocco_etruck.optimization.label_setting import SolverStatus, solve_mrls
from morocco_etruck.optimization.multiroute_adapter import (
    build_physics_od_instance,
    clone_physics_instance_for_subset,
    load_multiroute_pilot_config,
)
from morocco_etruck.optimization.multiroute_placement import (
    MultiroutePlacementConfig,
    MultiroutePlacementMission,
)
from morocco_etruck.optimization.multiroute_physics import MultirouteMissionContext
from morocco_etruck.optimization.multiroute_replay import continuous_replay_multiroute
from morocco_etruck.optimization.placement_cache import CachedMissionResult, PlacementMemo
from morocco_etruck.optimization.placement_certification import OptimalityStatus
from morocco_etruck.optimization.placement_evaluation import MissionSolveResult, SubsetEvaluation
from morocco_etruck.optimization.placement_problem import (
    PlacementSite,
    annualized_infra_cost,
    budget_ok,
    subset_capex,
)
from morocco_etruck.optimization.problem import RoutingInstance
from morocco_etruck.optimization.replay import replay_solution
from morocco_etruck.optimization.site_enumeration import all_subsets


@dataclass
class PreparedMultirouteMission:
    mission: MultiroutePlacementMission
    template: RoutingInstance
    ctx: MultirouteMissionContext
    station_notes: list[str]


def active_keys_for_installed(
    sites: list[PlacementSite],
    installed: set[str],
    template: RoutingInstance,
) -> set[str]:
    """Installed physical sites whose station_key exists on this OD fixed graph."""
    return {
        s.station_key
        for s in sites
        if s.id in installed and s.station_key in template.stations
    }


def _charge_total(actions: list) -> int:
    return sum(int(a.get("delta_e_kwh", 0)) for a in actions if a.get("type") == "CHARGE")


def _charge_nodes(actions: list) -> str:
    return ";".join(
        f"{a['node']}:{a['delta_e_kwh']}" for a in actions if a.get("type") == "CHARGE"
    )


def resolve_mission_gcm_kg(
    mission: MultiroutePlacementMission,
    cfg_pilot,
    *,
    vehicle=None,
) -> float:
    """
    Immutable mission mass.

    Prefer fixed cargo_payload_kg (Task 07A) → GCM = empty combination + payload.
    Else light/heavy from pilot physics YAML — never from mutated cfg.gcm_kg.
    """
    payload = getattr(mission, "cargo_payload_kg", None)
    if payload is not None:
        if vehicle is None:
            raise ValueError("cargo_payload_kg requires a loaded vehicle to resolve GCM")
        from morocco_etruck.energy.vehicle import gcm_from_payload, validate_gcm

        gcm = gcm_from_payload(float(payload), vehicle)
        validate_gcm(gcm, vehicle)
        return float(gcm)
    phys = cfg_pilot.raw.get("physics") or {}
    light = float(phys.get("gcm_kg", getattr(cfg_pilot, "gcm_kg", 25000.0)))
    heavy = float(phys.get("gcm_heavy_kg", 40000.0))
    if mission.gcm == "heavy":
        return heavy
    if mission.gcm == "light":
        return light
    try:
        return float(mission.gcm)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Unknown mission.gcm={mission.gcm!r}") from exc


def prepare_multiroute_mission(
    mission: MultiroutePlacementMission,
    *,
    cfg_pilot,
    root: Path,
    path_rows: list[dict[str, Any]],
    energy_quantum_kwh: int | None = None,
    objective_mode: str = "enroute_incremental_cost",
    vehicle_yaml: Path | None = None,
    road_cost_per_km: float | None = None,
    gcm_kg: float | None = None,
    E_truck_init: int | None = None,
    deadline_steps: int | None = None,
    fridge_yaml: Path | None = None,
    charger_power_kw: float | None = None,
    max_alternatives_for_union: int | None = None,
) -> PreparedMultirouteMission:
    """Build fixed path-union graph once; template has active_stations=∅."""
    from morocco_etruck.energy.vehicle import load_vehicle

    v_yaml = Path(vehicle_yaml) if vehicle_yaml is not None else cfg_pilot.vehicle_yaml
    if not v_yaml.is_absolute():
        v_yaml = root / v_yaml
    vehicle = load_vehicle(v_yaml)
    mission_gcm = (
        float(gcm_kg)
        if gcm_kg is not None
        else resolve_mission_gcm_kg(mission, cfg_pilot, vehicle=vehicle)
    )
    # Energies derived from vehicle usable_kwh; mission.E_truck_init is kWh
    # (or caller override for equal-SOC experiments).
    raw_cap = cfg_pilot.raw.get("E_truck_cap")
    raw_min = cfg_pilot.raw.get("E_truck_min")
    e_init = int(mission.E_truck_init if E_truck_init is None else E_truck_init)
    soc_frac = getattr(mission, "E_init_soc_frac", None)
    if soc_frac is not None and E_truck_init is None:
        usable = float(vehicle.usable_kwh)
        e_init = int(round(float(soc_frac) * usable))
    inst, ctx, notes = build_physics_od_instance(
        cfg=cfg_pilot,
        root=root,
        od_id=mission.od_id,
        path_rows=path_rows,
        E_truck_init=e_init,
        E_truck_cap=None if raw_cap is None else int(raw_cap),
        E_truck_min=None if raw_min is None else int(raw_min),
        refrigeration_on=bool(mission.refrigeration_on),
        weather_id=str(mission.weather_id),
        with_chargers=False,  # graph still attaches candidates; none active
        terrain_mode=str(mission.terrain_mode),
        attach_candidate_chargers=True,
        energy_quantum_kwh=energy_quantum_kwh,
        objective_mode=objective_mode,
        vehicle_yaml=vehicle_yaml,
        road_cost_per_km=road_cost_per_km,
        gcm_kg=mission_gcm,
        deadline_steps=deadline_steps,
        fridge_yaml=fridge_yaml,
        charger_power_kw=charger_power_kw,
        max_alternatives_for_union=max_alternatives_for_union,
    )
    return PreparedMultirouteMission(
        mission=mission, template=inst, ctx=ctx, station_notes=list(notes)
    )


def evaluate_multiroute_mission(
    prepared: PreparedMultirouteMission,
    *,
    installed: set[str],
    sites: list[PlacementSite],
    max_seconds: float,
    max_expansions: int,
    memo: PlacementMemo | None = None,
    structural_ids: set[str] | None = None,
) -> MissionSolveResult:
    mission = prepared.mission
    active = active_keys_for_installed(sites, installed, prepared.template)
    is_struct = mission.id in (structural_ids or set())
    cache_key = None
    if memo is not None:
        cache_key = memo.make_key(
            mission_id=mission.id,
            active_station_keys=frozenset(active),
            price_mode=(
                f"uniform:{getattr(prepared.template, 'objective_mode', 'enroute_incremental_cost')}"
            ),
            q=prepared.template.energy_quantum_kwh,
            time_step_min=prepared.template.time_step_min,
        )
        hit = memo.get(cache_key)
        if hit is not None:
            return MissionSolveResult(
                mission_id=mission.id,
                status=hit.status,
                served=hit.served,
                structural=is_struct,
                uncertified=hit.uncertified,
                objective_cents=hit.objective_cents,
                charge_kwh=hit.charge_kwh,
                charges=hit.charges,
                path=hit.path,
                continuous_replay_ok=hit.continuous_replay_ok,
                discrete_replay_ok=hit.discrete_replay_ok,
                active_stations=",".join(sorted(active)),
                reason=hit.reason,
            )

    inst = clone_physics_instance_for_subset(
        prepared.template,
        active_stations=active,
        name=f"{mission.id}:{','.join(sorted(installed)) or 'none'}",
    )
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
    crep, _extras = continuous_replay_multiroute(
        prepared.ctx,
        inst,
        result.actions,
        discrete_cost=result.objective,
        discrete_t=result.final_label.t,
        discrete_E_truck=result.final_label.E_truck,
    )
    served = bool(disc.ok and crep.ok)
    return _store(
        MissionSolveResult(
            mission_id=mission.id,
            status=result.status.value,
            served=served,
            structural=is_struct,
            uncertified=not served,
            objective_cents=result.objective,
            charge_kwh=_charge_total(result.actions),
            charges=_charge_nodes(result.actions),
            path="->".join(result.path_nodes),
            continuous_replay_ok=crep.ok,
            discrete_replay_ok=disc.ok,
            active_stations=",".join(sorted(active)),
            reason=None if served else (crep.reason or disc.reason or "replay_invalid"),
        )
    )


def evaluate_multiroute_subset(
    installed: set[str],
    *,
    cfg: MultiroutePlacementConfig,
    prepared: dict[str, PreparedMultirouteMission],
    missions: list[MultiroutePlacementMission],
    capex: dict[str, float],
    max_capex: float | None,
    memo: PlacementMemo | None = None,
    structural_ids: set[str] | None = None,
    serviceable_ids: set[str] | None = None,
) -> SubsetEvaluation:
    ok_budget = budget_ok(installed, capex, max_capex)
    results: list[MissionSolveResult] = []
    for m in missions:
        results.append(
            evaluate_multiroute_mission(
                prepared[m.id],
                installed=installed,
                sites=cfg.sites,
                max_seconds=cfg.solver_max_seconds,
                max_expansions=cfg.solver_max_expansions,
                memo=memo,
                structural_ids=structural_ids,
            )
        )
    weight_by_id = {m.id: m.weight for m in missions}
    served_ids = {r.mission_id for r in results if r.served}
    if serviceable_ids is not None:
        cov_ids = served_ids & serviceable_ids
    else:
        cov_ids = served_ids
    coverage_serviceable = sum(weight_by_id[i] for i in cov_ids)
    coverage_total = sum(weight_by_id[r.mission_id] for r in results if r.served)
    weight_serviceable = sum(weight_by_id.get(i, 0.0) for i in (serviceable_ids or set()))
    weight_total = sum(m.weight for m in missions)
    var = 0.0
    certified = ok_budget and all(not r.uncertified for r in results)
    for r in results:
        if r.served and r.objective_cents is not None:
            var += weight_by_id[r.mission_id] * float(r.objective_cents) * cfg.cents_to_currency
    infra = subset_capex(installed, capex)
    infra_ann = annualized_infra_cost(installed, capex, cfg.crf)
    return SubsetEvaluation(
        site_ids=frozenset(installed),
        budget_ok=ok_budget,
        certified=certified,
        coverage_total=coverage_total,
        coverage_serviceable=coverage_serviceable,
        weight_total=weight_total,
        weight_serviceable=weight_serviceable,
        infra_capex=infra,
        infra_annual=infra_ann,
        variable_cost=var,
        secondary_cost=infra_ann + var,
        missions=results,
    )


def prepare_multiroute_placement_context(
    cfg: MultiroutePlacementConfig,
    *,
    root: Path,
    demand_name: str,
    memo: PlacementMemo | None = None,
    energy_quantum_kwh: int | None = None,
    objective_mode: str = "enroute_incremental_cost",
    vehicle_yaml: Path | None = None,
    road_cost_per_km: float | None = None,
    deadline_steps: int | None = None,
    fridge_yaml: Path | None = None,
    charger_power_kw: float | None = None,
    max_alternatives_for_union: int | None = None,
) -> dict[str, Any]:
    from morocco_etruck.optimization.drive_table_cache import file_sha256
    from morocco_etruck.optimization.placement_cache import build_mission_energy_fingerprint
    from morocco_etruck.optimization.placement_certification import ServiceabilityClass

    pilot = load_multiroute_pilot_config(cfg.multiroute_pilot_path, root=root)
    path_rows = pd.read_csv(pilot.path_alternatives_csv).to_dict(orient="records")
    missions = list(cfg.demand_scenarios[demand_name])
    prepared: dict[str, PreparedMultirouteMission] = {}
    for m in missions:
        prepared[m.id] = prepare_multiroute_mission(
            m,
            cfg_pilot=pilot,
            root=root,
            path_rows=path_rows,
            energy_quantum_kwh=energy_quantum_kwh,
            objective_mode=objective_mode,
            vehicle_yaml=vehicle_yaml,
            road_cost_per_km=road_cost_per_km,
            deadline_steps=deadline_steps,
            fridge_yaml=fridge_yaml,
            charger_power_kw=charger_power_kw,
            max_alternatives_for_union=max_alternatives_for_union,
        )

    # Serviceability: probe with all sites installed
    all_ids = {s.id for s in cfg.sites}
    serviceability: dict[str, str] = {}
    for m in missions:
        r = evaluate_multiroute_mission(
            prepared[m.id],
            installed=all_ids,
            sites=cfg.sites,
            max_seconds=cfg.solver_max_seconds,
            max_expansions=cfg.solver_max_expansions,
            memo=None,
        )
        if r.status == "LIMIT_REACHED":
            serviceability[m.id] = "limit_reached"
        elif r.served:
            serviceability[m.id] = "serviceable"
        elif r.uncertified:
            serviceability[m.id] = "replay_invalid"
        else:
            serviceability[m.id] = "unserved_all_candidates"

    from morocco_etruck.optimization.placement_certification import (
        is_unresolved_serviceability,
    )

    structural_ids = {mid for mid, v in serviceability.items() if v == "peak_motor"}
    serviceable_ids = {mid for mid, v in serviceability.items() if v == "serviceable"}
    unresolved_ids = {
        mid for mid, v in serviceability.items() if is_unresolved_serviceability(v)
    }
    weight_by_id = {m.id: float(m.weight) for m in missions}
    weight_total_demand = sum(weight_by_id.values())
    unresolved_weight = sum(weight_by_id[i] for i in unresolved_ids)
    if memo is None:
        sample = next(iter(prepared.values())).template
        vpath = Path(vehicle_yaml) if vehicle_yaml is not None else pilot.vehicle_yaml
        if not vpath.is_absolute():
            vpath = root / vpath
        fpath = Path(fridge_yaml) if fridge_yaml is not None else pilot.fridge_yaml
        if not fpath.is_absolute():
            fpath = root / fpath
        terrains = sorted({str(m.terrain_mode) for m in missions})
        memo = PlacementMemo(
            energy_model_fingerprint=build_mission_energy_fingerprint(
                vehicle_yaml=vpath if vpath.exists() else None,
                fridge_yaml=fpath if fpath.exists() else None,
                q=int(sample.energy_quantum_kwh),
                time_step_min=int(sample.time_step_min),
                terrain_mode=",".join(terrains),
                weather_id=",".join(sorted({str(m.weather_id) for m in missions})),
                refrigeration=",".join(
                    sorted({"on" if m.refrigeration_on else "off" for m in missions})
                ),
                power_source="A",
                extra={
                    "deadline_steps": int(sample.deadline_steps),
                    "charger_power_kw": (
                        None
                        if charger_power_kw is None
                        else float(charger_power_kw)
                    ),
                    "objective_mode": objective_mode,
                    "E_truck": [sample.E_truck_min, sample.E_truck_cap],
                    "max_alternatives_for_union": max_alternatives_for_union,
                    "demand_name": demand_name,
                },
            )
        )
    return {
        "pilot": pilot,
        "missions": missions,
        "prepared": prepared,
        "serviceability": serviceability,
        "structural_ids": structural_ids,
        "serviceable_ids": serviceable_ids,
        "unresolved_ids": unresolved_ids,
        "unresolved_weight": unresolved_weight,
        "weight_total_demand": weight_total_demand,
        "memo": memo,
        "vehicle_yaml": str(vehicle_yaml or pilot.vehicle_yaml),
        "objective_mode": objective_mode,
        "road_cost_per_km": road_cost_per_km,
    }


def all_optimal_site_sets(
    enum_rows: list[dict[str, Any]],
    *,
    tol_cov: float = 1e-9,
    tol_cost: float = 1e-6,
) -> list[str]:
    """All budget-feasible certified subsets matching best coverage then secondary cost."""
    feas = [r for r in enum_rows if r.get("budget_ok") and r.get("certified")]
    if not feas:
        return []
    best_cov = max(float(r["coverage_serviceable"]) for r in feas)
    at_cov = [
        r for r in feas if abs(float(r["coverage_serviceable"]) - best_cov) <= tol_cov
    ]
    best_cost = min(float(r["secondary_cost"]) for r in at_cov)
    opts = [
        str(r["sites"])
        for r in at_cov
        if abs(float(r["secondary_cost"]) - best_cost) <= tol_cost
    ]
    return sorted(set(opts))


def run_multiroute_enumeration(
    cfg: MultiroutePlacementConfig,
    *,
    root: Path,
    demand_name: str,
    capex_name: str,
    budget_name: str,
    context: dict[str, Any] | None = None,
) -> tuple[list[dict[str, Any]], SubsetEvaluation | None, dict[str, Any]]:
    if context is None:
        context = prepare_multiroute_placement_context(
            cfg, root=root, demand_name=demand_name
        )
    capex = cfg.capex_scenarios[capex_name]
    bud = next(b for b in cfg.budgets if b["name"] == budget_name)
    max_c = bud.get("max_capex")
    max_c_f = None if max_c is None else float(max_c)
    site_ids = [s.id for s in cfg.sites]
    rows: list[dict[str, Any]] = []
    best: SubsetEvaluation | None = None

    for subset in all_subsets(site_ids):
        if not budget_ok(set(subset), capex, max_c_f):
            continue
        ev = evaluate_multiroute_subset(
            set(subset),
            cfg=cfg,
            prepared=context["prepared"],
            missions=context["missions"],
            capex=capex,
            max_capex=max_c_f,
            memo=context["memo"],
            structural_ids=context["structural_ids"],
            serviceable_ids=context["serviceable_ids"],
        )
        row = {
            "method": "enumeration",
            "demand_scenario": demand_name,
            "capex_scenario": capex_name,
            "budget_name": budget_name,
            "max_capex": max_c,
            "sites": ",".join(sorted(subset)) or "NONE",
            "n_sites": len(subset),
            "coverage_serviceable": ev.coverage_serviceable,
            "coverage_total": ev.coverage_total,
            "infra_capex": ev.infra_capex,
            "infra_annual": ev.infra_annual,
            "variable_cost": ev.variable_cost,
            "secondary_cost": ev.secondary_cost,
            "certified": ev.certified,
            "budget_ok": ev.budget_ok,
            "mission_detail": ";".join(
                f"{m.mission_id}:{m.status}:served={int(m.served)}:chg={m.charges}:path={m.path}"
                for m in ev.missions
            ),
        }
        rows.append(row)
        if not ev.certified or not ev.budget_ok:
            continue
        if best is None:
            best = ev
        else:
            better_cov = ev.coverage_serviceable > best.coverage_serviceable + 1e-12
            equal_cov = abs(ev.coverage_serviceable - best.coverage_serviceable) <= 1e-12
            better_cost = ev.secondary_cost + 1e-12 < best.secondary_cost
            if better_cov or (equal_cov and better_cost):
                best = ev
    return rows, best, context


def run_multiroute_branch_and_bound(
    cfg: MultiroutePlacementConfig,
    *,
    root: Path,
    demand_name: str,
    capex_name: str,
    budget_name: str,
    context: dict[str, Any] | None = None,
) -> tuple[BranchAndBoundResult, dict[str, Any]]:
    if context is None:
        context = prepare_multiroute_placement_context(
            cfg, root=root, demand_name=demand_name
        )
    capex = cfg.capex_scenarios[capex_name]
    bud = next(b for b in cfg.budgets if b["name"] == budget_name)
    max_c = bud.get("max_capex")
    max_c_f = None if max_c is None else float(max_c)

    def evaluate_fn(installed: set[str]) -> SubsetEvaluation:
        return evaluate_multiroute_subset(
            installed,
            cfg=cfg,
            prepared=context["prepared"],
            missions=context["missions"],
            capex=capex,
            max_capex=max_c_f,
            memo=context["memo"],
            structural_ids=context["structural_ids"],
            serviceable_ids=context["serviceable_ids"],
        )

    core = run_branch_and_bound_core(
        site_ids=[s.id for s in cfg.sites],
        capex=capex,
        max_capex=max_c_f,
        crf=cfg.crf,
        evaluate_fn=evaluate_fn,
        memo=context["memo"],
        node_limit=cfg.node_limit,
        time_limit_sec=cfg.time_limit_sec,
    )
    from morocco_etruck.optimization.placement_certification import portfolio_optimality_status

    core.structural_ids = set(context["structural_ids"])
    core.serviceability = dict(context["serviceability"])
    core.optimality_status = portfolio_optimality_status(
        core_status=core.optimality_status,
        serviceability=core.serviceability,
    )
    return core, context
