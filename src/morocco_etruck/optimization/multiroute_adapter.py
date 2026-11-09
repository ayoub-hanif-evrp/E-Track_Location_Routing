"""Multi-route MRLS adapters (Task 05A legacy path-set + Task 05B path-union physics)."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

from morocco_etruck.energy.refrigeration import load_refrigeration
from morocco_etruck.energy.vehicle import load_vehicle
from morocco_etruck.optimization.multiroute_charging import (
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
            road_cost = max(1, int(round(half / 1000.0)))
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


def build_physics_od_instance(
    *,
    cfg: MultiroutePilotConfig,
    root: Path,
    od_id: str,
    path_rows: list[dict[str, Any]],
    E_truck_init: int,
    E_truck_cap: int,
    E_truck_min: int,
    refrigeration_on: bool = False,
    weather_id: str = "cool",
    with_chargers: bool = False,
    energy_quantum_kwh: int | None = None,
    terrain_mode: str | None = None,
) -> tuple[RoutingInstance, MultirouteMissionContext, list[str]]:
    """
    Scientific Task 05B builder: OD-induced path-union decision arcs + DRIVE tables.
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
        # Keep other ODs' rows out; induce uses only matching od_id
        path_rows = [r for r in path_rows if str(r.get("od_id")) != od_id] + rows_for_od
    arcs, origin, dest, nodes = contract_od_path_union(
        G,
        path_rows,
        od_id,
        speed_policy=cfg.speed_policy,
        origin_name="O",
        dest_name="D",
    )
    _ = dec  # audited global graph retained for reporting / legacy helpers

    station_notes: list[str] = []
    stations: dict[str, StationData] = {}
    active: set[str] = set()
    if with_chargers:
        specs = list((cfg.raw.get("grounded_chargers") or {}).get(od_id) or [])
        # Default southbound ADM set when OD not listed
        if not specs:
            specs = list((cfg.raw.get("grounded_chargers") or {}).get("default") or [])
        reject_artificial_midpoint_keys([str(s.get("key", "")) for s in specs])
        union_nodes: set[int] = set()
        for a in arcs:
            union_nodes.update(int(x) for x in a.path_nodes)
        sites = pd.read_csv(cfg.candidate_sites_csv)
        chargers = select_grounded_chargers_on_union(
            sites,
            union_osm_nodes=union_nodes,
            decision_nodes=nodes,
            station_specs=specs,
            G=G,
        )
        if not chargers:
            station_notes.append("no_grounded_charger_on_union")
        else:
            ch = cfg.raw.get("charger") or {}
            stations = to_station_data(
                chargers,
                power_kw=float(ch.get("power_kw", 350.0)),
                eta=float(ch.get("eta", 0.95)),
                price_cents=int(ch.get("price_uniform_cents", 20)),
            )
            # Align StationData.node with decision labels after split
            arcs, nodes, _alias = split_arcs_at_charger_nodes(
                arcs, chargers=chargers, decision_nodes=nodes
            )
            for c in chargers:
                stations[c.key] = StationData(
                    node=c.key,
                    power_kw=float(ch.get("power_kw", 350.0)),
                    eta=float(ch.get("eta", 0.95)),
                    price_cents_per_grid_kwh=int(ch.get("price_uniform_cents", 20)),
                    compatible=True,
                    official_name=c.official_name,
                    hypothetical_access=True,
                    hgv_status=c.hgv_status,
                    osm_id=c.osm_id,
                    snap_distance_m=c.snap_distance_m,
                )
                nodes[c.key] = c.osm_node_id
            active = set(stations.keys())
            station_notes.append(f"grounded_chargers={sorted(active)}")

    vehicle = load_vehicle(cfg.vehicle_yaml)
    fridge = load_refrigeration(cfg.fridge_yaml)
    weather = load_weather_for_multiroute(
        root=root, morocco_pilot_yaml=cfg.morocco_pilot_yaml, weather_id=weather_id
    )
    q = int(energy_quantum_kwh if energy_quantum_kwh is not None else cfg.energy_quantum_kwh)
    # Snap energies onto quantum grid
    def _floor_q(x: int) -> int:
        return (x // q) * q

    def _ceil_q(x: int) -> int:
        return int(math.ceil(x / q) * q)

    E_cap = _floor_q(E_truck_cap)
    E_min = _ceil_q(E_truck_min)
    E_init = min(E_cap, _floor_q(E_truck_init))
    if E_init < E_min:
        E_init = E_min

    inst, ctx = build_path_union_routing_instance(
        G=G,
        dec=dec,
        path_rows=path_rows,
        od_id=od_id,
        vehicle=vehicle,
        fridge=fridge,
        weather=weather,
        vehicle_yaml=cfg.vehicle_yaml,
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
        road_cost_per_km=cfg.road_cost_per_km,
        stations=stations,
        active_stations=active,
        decision_arcs=arcs,
        origin=origin,
        destination=dest,
        decision_nodes=nodes,
        wait_max_steps=int(cfg.raw.get("wait_max_steps", 0)),
    )
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
