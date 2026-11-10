"""Multi-route MRLS adapters (Task 05A legacy path-set + Task 05B path-union physics)."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

from morocco_etruck.energy.battery_bounds import derive_discrete_energy_bounds
from morocco_etruck.energy.refrigeration import load_refrigeration
from morocco_etruck.energy.vehicle import load_vehicle
from morocco_etruck.optimization.multiroute_charging import (
    ChargerSelectionResult,
    GroundedCharger,
    reject_artificial_midpoint_keys,
    select_grounded_chargers_on_union,
    split_arcs_at_charger_nodes,
    to_station_data,
)
from morocco_etruck.optimization.multiroute_physics import (
    MultirouteMissionContext,
    build_path_union_routing_instance,
    contract_od_path_union,
    load_weather_for_multiroute,
)
from morocco_etruck.optimization.problem import ArcData, RoutingInstance, StationData
from morocco_etruck.optimization.route_choice_graph import DecisionArc, RouteChoiceGraph
from morocco_etruck.road_network import load_graph_from_csv

ROOT = Path(__file__).resolve().parents[3]


@dataclass
class MultiroutePilotConfig:
    raw: dict[str, Any]
    decision_graph_path: Path
    nodes_csv: Path
    edges_csv: Path
    path_alternatives_csv: Path
    candidate_sites_csv: Path
    time_step_min: int
    energy_quantum_kwh: int
    deadline_steps: int
    consumption_kwh_per_km: float
    vehicle_yaml: Path
    fridge_yaml: Path
    morocco_pilot_yaml: Path
    speed_policy: dict[str, Any]
    disclaimer: str
    terrain_mode: str
    elevation_dir: Path
    drive_cache_dir: Path
    gcm_kg: float
    road_cost_per_km: float


def load_multiroute_pilot_config(path: Path, *, root: Path) -> MultiroutePilotConfig:
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    out = raw.get("outputs") or {}
    base = root / out.get("processed_dir", "data/processed/multiroute")
    phys = raw.get("physics") or {}
    return MultiroutePilotConfig(
        raw=raw,
        decision_graph_path=base / "decision_graph.json",
        nodes_csv=base / "nodes.csv" if (base / "nodes.csv").exists() else base / "road_nodes.csv",
        edges_csv=base / "edges.csv" if (base / "edges.csv").exists() else base / "road_edges.csv",
        path_alternatives_csv=base / "path_alternatives.csv",
        candidate_sites_csv=root
        / raw.get("candidate_sites_csv", "data/processed/candidate_sites.csv"),
        time_step_min=int(raw.get("time_step_min", 5)),
        energy_quantum_kwh=int(raw.get("energy_quantum_kwh", 5)),
        deadline_steps=int(raw.get("deadline_steps", 200)),
        consumption_kwh_per_km=float(raw.get("consumption_kwh_per_km", 1.2)),
        vehicle_yaml=root / raw.get("vehicle_config", "configs/vehicles/eactros_600.yaml"),
        fridge_yaml=root / raw.get("refrigeration_config", "configs/energy/refrigeration_approx.yaml"),
        morocco_pilot_yaml=root
        / raw.get("morocco_pilot_config", "configs/optimization/morocco_pilot.yaml"),
        speed_policy=dict(raw.get("speed_policy") or {}),
        disclaimer=str(raw.get("disclaimer", "")),
        terrain_mode=str(phys.get("terrain_mode", "flat")),
        elevation_dir=root
        / phys.get("elevation_dir", "data/processed/multiroute/elevation"),
        drive_cache_dir=root
        / phys.get("drive_cache_dir", "data/processed/multiroute/drive_tables"),
        gcm_kg=float(phys.get("gcm_kg", 25000.0)),
        road_cost_per_km=float(phys.get("road_cost_per_km", 1.0)),
    )


def load_decision_graph(path: Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _dt_steps(length_m: float, speed_kmh: float, time_step_min: int) -> int:
    if speed_kmh <= 0:
        speed_kmh = 50.0
    dt_s = (length_m / 1000.0) / speed_kmh * 3600.0
    step_s = time_step_min * 60.0
    return max(1, int(math.ceil(dt_s / step_s)))


def _dE_kwh(length_m: float, consumption_kwh_per_km: float, quantum: int) -> int:
    raw = (length_m / 1000.0) * consumption_kwh_per_km
    if raw <= 0:
        return 0
    q = max(1, int(quantum))
    return int(math.ceil(raw / q) * q)


def build_legacy_path_set_instance(
    *,
    cfg: MultiroutePilotConfig,
    od_id: str,
    origin_name: str,
    dest_name: str,
    path_rows: list[dict[str, Any]],
    active_stations: set[str] | None = None,
    stations: dict[str, StationData] | None = None,
    E_truck_init: int = 600,
    E_truck_cap: int = 600,
    E_truck_min: int = 60,
    refrigeration_on: bool = False,
    name: str | None = None,
    mean_speed_kmh: float = 70.0,
) -> RoutingInstance:
    """
    LEGACY Task 05A artificial O → R_i → D path-set model (illustrative 1 kWh/km).

    Not used for scientific Task 05B Moroccan claims. Kept for regression benchmarks.
    """
    if stations:
        reject_artificial_midpoint_keys(list(stations.keys()))
    od_paths = [r for r in path_rows if str(r.get("od_id")) == od_id]
    arcs: list[ArcData] = []
    nodes = {origin_name, dest_name}
    for i, row in enumerate(od_paths):
        mid = f"R{i}_{od_id}"
        nodes.add(mid)
        length_m = float(row["length_m"])
        half = length_m / 2.0
        for u, v in ((origin_name, mid), (mid, dest_name)):
            dt = _dt_steps(half, mean_speed_kmh, cfg.time_step_min)
            dE = _dE_kwh(half, cfg.consumption_kwh_per_km, cfg.energy_quantum_kwh)
            # No per-macro max(1, …) floor (Task 06A/06B representation integrity).
            road_cost = max(0, int(round(half / 1000.0)))
            arcs.append(
                ArcData(
                    u=u,
                    v=v,
                    dt_steps=dt,
                    dE_truck_kwh=max(1, dE),
                    dE_trailer_kwh=0,
                    road_cost=road_cost,
                    power_ok=True,
                    arc_id=f"legacy_{od_id}_{i}_{u}_{v}",
                )
            )
        _ = json.loads(row["node_path_json"])
    return RoutingInstance(
        name=name or f"legacy_path_set_{od_id}",
        nodes=sorted(nodes),
        arcs=arcs,
        origin=origin_name,
        destination=dest_name,
        deadline_steps=cfg.deadline_steps,
        E_truck_cap=E_truck_cap,
        E_truck_min=E_truck_min,
        E_truck_init=E_truck_init,
        E_trailer_cap=None,
        E_trailer_min=None,
        E_trailer_init=None,
        stations=stations or {},
        active_stations=set(active_stations or []),
        power_source="A",
        refrigeration_on=refrigeration_on,
        wait_max_steps=0,
        time_step_min=cfg.time_step_min,
        energy_quantum_kwh=cfg.energy_quantum_kwh,
        notes=(
            "LEGACY Task 05A path-set model (artificial R_i midpoints; flat kWh/km). "
            "Not a physics-validated Moroccan claim."
        ),
    )


# Back-compat alias used by older scripts/tests
build_od_routing_instance = build_legacy_path_set_instance


def _station_specs_for_od(cfg: MultiroutePilotConfig, od_id: str) -> list[dict[str, Any]]:
    specs = list((cfg.raw.get("grounded_chargers") or {}).get(od_id) or [])
    if not specs:
        specs = list((cfg.raw.get("grounded_chargers") or {}).get("default") or [])
    return specs


def resolve_od_chargers(
    *,
    cfg: MultiroutePilotConfig,
    G,
    arcs: list[DecisionArc],
    nodes: dict[str, Any],
    od_id: str,
) -> tuple[ChargerSelectionResult, list[str]]:
    """Direction-correct ADM resolution for one OD (no graph mutation)."""
    notes: list[str] = []
    specs = _station_specs_for_od(cfg, od_id)
    reject_artificial_midpoint_keys([str(s.get("key", "")) for s in specs])
    if not specs:
        return ChargerSelectionResult(), ["no_charger_specs_for_od"]
    union_nodes: set[int] = set()
    for a in arcs:
        union_nodes.update(int(x) for x in a.path_nodes)
    sites = pd.read_csv(cfg.candidate_sites_csv)
    allow_snap = bool((cfg.raw.get("charger") or {}).get("allow_proximity_snap", False))
    max_snap = float((cfg.raw.get("charger") or {}).get("max_snap_m", 2500.0))
    selection = select_grounded_chargers_on_union(
        sites,
        union_osm_nodes=union_nodes,
        decision_nodes=nodes,
        station_specs=specs,
        G=G,
        max_snap_m=max_snap,
        allow_proximity_snap=allow_snap,
    )
    notes.append(
        "verified="
        + ",".join(sorted(c.key for c in selection.verified))
        + ";hypothetical="
        + ",".join(sorted(c.key for c in selection.hypothetical))
        + ";unresolved="
        + ",".join(
            f"{c.key}:{c.reason}" for c in selection.unresolved
        )
    )
    return selection, notes


def clone_physics_instance_for_subset(
    template: RoutingInstance,
    *,
    active_stations: set[str],
    name: str | None = None,
) -> RoutingInstance:
    """Reuse fixed DRIVE tables/graph; only active charging actions change."""
    return RoutingInstance(
        name=name or template.name,
        nodes=list(template.nodes),
        arcs=list(template.arcs),
        origin=template.origin,
        destination=template.destination,
        deadline_steps=template.deadline_steps,
        E_truck_cap=template.E_truck_cap,
        E_truck_min=template.E_truck_min,
        E_truck_init=template.E_truck_init,
        E_trailer_cap=template.E_trailer_cap,
        E_trailer_min=template.E_trailer_min,
        E_trailer_init=template.E_trailer_init,
        stations=dict(template.stations),
        active_stations=set(active_stations),
        power_source=template.power_source,
        refrigeration_on=template.refrigeration_on,
        aux_kwh_per_step=template.aux_kwh_per_step,
        tru_kwh_per_step=template.tru_kwh_per_step,
        aux_w=template.aux_w,
        tru_mean_w=template.tru_mean_w,
        wait_max_steps=template.wait_max_steps,
        time_step_min=template.time_step_min,
        energy_quantum_kwh=template.energy_quantum_kwh,
        objective_mode=getattr(template, "objective_mode", "enroute_incremental_cost"),
        terminal_target_truck_kwh=getattr(template, "terminal_target_truck_kwh", None),
        terminal_target_trailer_kwh=getattr(template, "terminal_target_trailer_kwh", None),
        terminal_price_cents_per_grid_kwh=getattr(
            template, "terminal_price_cents_per_grid_kwh", None
        ),
        terminal_eta=getattr(template, "terminal_eta", None),
        notes=template.notes,
    )


def build_physics_od_instance(
    *,
    cfg: MultiroutePilotConfig,
    root: Path,
    od_id: str,
    path_rows: list[dict[str, Any]],
    E_truck_init: int | None = None,
    E_truck_cap: int | None = None,
    E_truck_min: int | None = None,
    refrigeration_on: bool = False,
    weather_id: str = "cool",
    with_chargers: bool = False,
    energy_quantum_kwh: int | None = None,
    terrain_mode: str | None = None,
    attach_candidate_chargers: bool | None = None,
    active_station_keys: set[str] | None = None,
    objective_mode: str = "enroute_incremental_cost",
    terminal_price_cents_per_grid_kwh: int | None = None,
    terminal_eta: float | None = None,
    terminal_target_truck_kwh: int | None = None,
    road_cost_per_km: float | None = None,
    vehicle_yaml: Path | None = None,
) -> tuple[RoutingInstance, MultirouteMissionContext, list[str]]:
    """
    Scientific Task 05B/05C builder: OD path-union + DRIVE tables.

    Architecture (Task 05C):
      - Resolve all direction-compatible attachable candidates once.
      - Split macros once at those OSM nodes (fixed physical graph).
      - ``with_chargers`` / ``active_station_keys`` only toggle charging actions.
      - DRIVE tables are never rebuilt when activating/deactivating sites.
    """
    dec = load_decision_graph(cfg.decision_graph_path)
    G = load_graph_from_csv(cfg.nodes_csv, cfg.edges_csv)
    # Tractability: optional cap on alternatives used for the OD path-union
    max_alts = int((cfg.raw.get("physics") or {}).get("max_alternatives_for_union") or 0)
    rows_for_od = [r for r in path_rows if str(r.get("od_id")) == od_id]
    if max_alts > 0 and len(rows_for_od) > max_alts:
        short = [r for r in rows_for_od if str(r.get("method")) == "shortest_distance"]
        rest = sorted(
            [r for r in rows_for_od if str(r.get("method")) != "shortest_distance"],
            key=lambda r: -float(r.get("jaccard_distance_vs_shortest") or 0.0),
        )
        rows_for_od = (short[:1] + rest)[:max_alts]
        path_rows = [r for r in path_rows if str(r.get("od_id")) != od_id] + rows_for_od
    arcs, origin, dest, nodes = contract_od_path_union(
        G,
        path_rows,
        od_id,
        speed_policy=cfg.speed_policy,
        origin_name="O",
        dest_name="D",
    )

    # Always attach eligible candidates when charger specs exist (fixed graph).
    # attach_candidate_chargers=False disables split (legacy diagnostic only).
    do_attach = True if attach_candidate_chargers is None else bool(attach_candidate_chargers)
    station_notes: list[str] = []
    stations: dict[str, StationData] = {}
    selection = ChargerSelectionResult()
    if do_attach and _station_specs_for_od(cfg, od_id):
        selection, sel_notes = resolve_od_chargers(
            cfg=cfg, G=G, arcs=arcs, nodes=nodes, od_id=od_id
        )
        station_notes.extend(sel_notes)
        attachable: list[GroundedCharger] = selection.attachable
        if not attachable:
            station_notes.append("no_topology_verified_charger_on_union")
        else:
            ch = cfg.raw.get("charger") or {}
            # vehicle loaded below; temporary charger power — capped after load
            stations = to_station_data(
                attachable,
                power_kw=float(ch.get("power_kw", 350.0)),
                eta=float(ch.get("eta", 0.95)),
                price_cents=int(ch.get("price_uniform_cents", 20)),
            )
            arcs, nodes, _alias = split_arcs_at_charger_nodes(
                arcs, chargers=attachable, decision_nodes=nodes, G=G
            )
            for c in attachable:
                nodes[c.key] = c.osm_node_id
            station_notes.append(
                "fixed_graph_chargers=" + ",".join(sorted(stations.keys()))
            )

    if active_station_keys is not None:
        active = set(active_station_keys) & set(stations.keys())
    elif with_chargers:
        # Activate topology-verified sites only (hypothetical remain inactive unless listed)
        active = {c.key for c in selection.verified}
        if not active and selection.hypothetical:
            # Explicit hypothetical-only portfolio: activate only if snap mode enabled
            active = {c.key for c in selection.hypothetical}
        station_notes.append(f"active_chargers={sorted(active)}")
    else:
        active = set()
        station_notes.append("active_chargers=[]")

    v_yaml = Path(vehicle_yaml) if vehicle_yaml is not None else cfg.vehicle_yaml
    if not v_yaml.is_absolute():
        v_yaml = root / v_yaml
    vehicle = load_vehicle(v_yaml)
    fridge = load_refrigeration(cfg.fridge_yaml)
    weather, weather_assumed = load_weather_for_multiroute(
        root=root, morocco_pilot_yaml=cfg.morocco_pilot_yaml, weather_id=weather_id
    )
    q = int(energy_quantum_kwh if energy_quantum_kwh is not None else cfg.energy_quantum_kwh)

    derive = bool(cfg.raw.get("derive_energy_from_vehicle", True))
    if derive or E_truck_cap is None or E_truck_min is None or E_truck_init is None:
        E_min, E_init, E_cap, e_notes = derive_discrete_energy_bounds(
            vehicle,
            energy_quantum_kwh=q,
            E_truck_init_kwh=None if E_truck_init is None else float(E_truck_init),
        )
        station_notes.append("energy_from_vehicle=" + ";".join(f"{k}:{v}" for k, v in e_notes.items()))
    else:
        def _floor_q(x: int) -> int:
            return (x // q) * q

        def _ceil_q(x: int) -> int:
            return int(math.ceil(x / q) * q)

        if int(E_truck_init) < int(E_truck_min):
            raise ValueError(
                f"INVALID_INPUT: E_truck_init={E_truck_init} < E_truck_min={E_truck_min}"
            )
        E_cap = _floor_q(int(E_truck_cap))
        E_min = _ceil_q(int(E_truck_min))
        E_init = min(E_cap, _floor_q(int(E_truck_init)))
        if E_init < E_min:
            raise ValueError(
                f"NUMERICAL_GRID_REJECT: floored E_init={E_init} < E_min={E_min} "
                f"(declared init={E_truck_init}, quantum={q}); not increasing energy"
            )

    # Cap charger power by vehicle CCS acceptance (constant-power approx).
    if stations and vehicle.ccs_max_charge_kw is not None:
        cap_kw = float(vehicle.ccs_max_charge_kw)
        stations = {
            k: StationData(
                node=st.node,
                power_kw=min(float(st.power_kw), cap_kw),
                eta=st.eta,
                price_cents_per_grid_kwh=st.price_cents_per_grid_kwh,
                compatible=st.compatible,
                official_name=st.official_name,
                hypothetical_access=st.hypothetical_access,
                hgv_status=st.hgv_status,
                osm_id=st.osm_id,
                snap_distance_m=st.snap_distance_m,
            )
            for k, st in stations.items()
        }
        station_notes.append(f"ccs_accept_cap_kw={cap_kw}")

    rckm = float(cfg.road_cost_per_km if road_cost_per_km is None else road_cost_per_km)
    term_target = terminal_target_truck_kwh if terminal_target_truck_kwh is not None else E_cap

    inst, ctx = build_path_union_routing_instance(
        G=G,
        dec=dec,
        path_rows=path_rows,
        od_id=od_id,
        vehicle=vehicle,
        fridge=fridge,
        weather=weather,
        vehicle_yaml=v_yaml,
        fridge_yaml=cfg.fridge_yaml,
        gcm_kg=cfg.gcm_kg,
        refrigeration_on=refrigeration_on,
        power_source="A",
        terrain_mode=terrain_mode or cfg.terrain_mode,
        elevation_dir=cfg.elevation_dir,
        cache_dir=cfg.drive_cache_dir,
        time_step_min=cfg.time_step_min,
        energy_quantum_kwh=q,
        deadline_steps=cfg.deadline_steps,
        E_truck_init=E_init,
        E_truck_cap=E_cap,
        E_truck_min=E_min,
        road_cost_per_km=rckm,
        stations=stations,
        active_stations=active,
        decision_arcs=arcs,
        origin=origin,
        destination=dest,
        decision_nodes=nodes,
        wait_max_steps=int(cfg.raw.get("wait_max_steps", 0)),
        speed_policy=cfg.speed_policy,
        objective_mode=objective_mode,  # type: ignore[arg-type]
        terminal_price_cents_per_grid_kwh=(
            terminal_price_cents_per_grid_kwh
            if terminal_price_cents_per_grid_kwh is not None
            else int((cfg.raw.get("charger") or {}).get("price_uniform_cents", 20))
        ),
        terminal_eta=(
            terminal_eta
            if terminal_eta is not None
            else float((cfg.raw.get("charger") or {}).get("eta", 0.95))
        ),
        terminal_target_truck_kwh=term_target,
    )
    if weather_assumed:
        ctx.weather_assumed = True
        ctx.notes.append("weather_assumed_synthetic_placeholder")
    return inst, ctx, station_notes


def decision_graph_to_route_choice(dec: dict[str, Any]) -> RouteChoiceGraph:
    arcs = [
        DecisionArc(
            u=str(a["u"]),
            v=str(a["v"]),
            path_nodes=list(a.get("path_nodes") or []),
            osm_edge_pairs=[tuple(p) for p in (a.get("osm_edge_pairs") or [])],
            length_m=float(a["length_m"]),
            highway_classes=list(a.get("highway_classes") or []),
            scenario_speed_kmh=float(a.get("scenario_speed_kmh") or 50),
            hgv_access=str(a.get("hgv_access") or "unknown"),
            arc_id=str(a.get("arc_id") or ""),
        )
        for a in dec.get("arcs") or []
    ]
    return RouteChoiceGraph(
        decision_nodes={k: v for k, v in (dec.get("decision_nodes") or {}).items()},
        arcs=arcs,
        path_records=[],
        notes=list(dec.get("notes") or []),
        alias_to_canonical=dict(dec.get("alias_to_canonical") or {}),
        od_terminals=dict(dec.get("od_terminals") or {}),
    )
