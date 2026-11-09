"""Path-union multiroute DRIVE physics (Task 05B)."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Sequence

import yaml

from morocco_etruck.energy.refrigeration import (
    RefrigerationParams,
    load_refrigeration,
    tru_electrical_power_w,
)
from morocco_etruck.energy.terrain import TerrainSample, load_profile
from morocco_etruck.energy.vehicle import VehicleParams, load_vehicle
from morocco_etruck.energy.weather import CorridorWeatherDay, WeatherPointDay
from morocco_etruck.optimization.arc_preprocessing import (
    MacroArcSpec,
    build_drive_table,
    build_macro_arc,
)
from morocco_etruck.optimization.drive_table_cache import (
    build_drive_table_fingerprint,
    load_cached_table,
    save_cached_table,
    terrain_sample_hash,
)
from morocco_etruck.optimization.problem import ArcData, RoutingInstance, StationData
from morocco_etruck.optimization.route_choice_graph import DecisionArc, make_arc_id

ROOT = Path(__file__).resolve().parents[3]


@dataclass
class MultirouteMissionContext:
    """Physics context for continuous replay of path-union MRLS solutions."""

    od_id: str
    macros_by_arc_id: dict[str, MacroArcSpec]
    vehicle: VehicleParams
    fridge: RefrigerationParams
    weather: CorridorWeatherDay
    gcm_kg: float
    refrigeration_on: bool
    power_source: str
    time_step_min: int
    terrain_mode: str
    notes: list[str] = field(default_factory=list)
    dem_complete: bool = True
    weather_assumed: bool = False


def _is_subsequence(sub: list[int], full: list[int]) -> bool:
    n, m = len(full), len(sub)
    if m > n or m == 0:
        return False
    for i in range(n - m + 1):
        if full[i : i + m] == sub:
            return True
    return False


def induce_od_decision_arcs(
    dec: dict[str, Any],
    path_rows: Sequence[dict[str, Any]],
    od_id: str,
) -> tuple[list[DecisionArc], str, str, dict[str, Any]]:
    """
    Filter global decision arcs to those on verified OD paths (legacy helper).

    Prefer ``contract_od_path_union`` for scientific MRLS instances — it rebuilds
    a compact OD-local contraction and avoids excess quantization boundaries.
    """
    od_paths: list[list[int]] = []
    for row in path_rows:
        if str(row.get("od_id")) != od_id:
            continue
        od_paths.append([int(x) for x in json.loads(row["node_path_json"])])
    if not od_paths:
        raise ValueError(f"No path alternatives for {od_id}")

    terminals = dec.get("od_terminals") or {}
    if od_id in terminals:
        origin = str(terminals[od_id]["origin"])
        dest = str(terminals[od_id]["destination"])
    else:
        alias = dec.get("alias_to_canonical") or {}
        origin = alias.get(f"{od_id}__o", f"{od_id}__o")
        dest = alias.get(f"{od_id}__d", f"{od_id}__d")

    all_nodes = {k: int(v) for k, v in (dec.get("decision_nodes") or {}).items()}
    arcs: list[DecisionArc] = []
    for a in dec.get("arcs") or []:
        pn = [int(x) for x in (a.get("path_nodes") or [])]
        if not any(_is_subsequence(pn, path) for path in od_paths):
            continue
        pairs_raw = a.get("osm_edge_pairs")
        if pairs_raw:
            pairs = [(int(u), int(v)) for u, v in pairs_raw]
        else:
            pairs = list(zip(pn[:-1], pn[1:]))
        aid = str(a.get("arc_id") or make_arc_id(pairs))
        arcs.append(
            DecisionArc(
                u=str(a["u"]),
                v=str(a["v"]),
                path_nodes=pn,
                osm_edge_pairs=pairs,
                length_m=float(a["length_m"]),
                highway_classes=list(a.get("highway_classes") or []),
                scenario_speed_kmh=float(a.get("scenario_speed_kmh") or 50),
                hgv_access=str(a.get("hgv_access") or "unknown"),
                arc_id=aid,
            )
        )

    succ: dict[str, list[str]] = {}
    for arc in arcs:
        succ.setdefault(arc.u, []).append(arc.v)
    reach: set[str] = set()
    stack = [origin]
    while stack:
        n = stack.pop()
        if n in reach:
            continue
        reach.add(n)
        stack.extend(succ.get(n, []))
    arcs = [a for a in arcs if a.u in reach and a.v in reach]
    used_nodes = {a.u for a in arcs} | {a.v for a in arcs} | {origin, dest}
    nodes = {k: all_nodes[k] for k in used_nodes if k in all_nodes}
    if origin in all_nodes:
        nodes[origin] = all_nodes[origin]
    if dest in all_nodes:
        nodes[dest] = all_nodes[dest]
    return arcs, origin, dest, nodes


def contract_od_path_union(
    G,
    path_rows: Sequence[dict[str, Any]],
    od_id: str,
    *,
    speed_policy: dict[str, Any] | None = None,
    origin_name: str = "O",
    dest_name: str = "D",
) -> tuple[list[DecisionArc], str, str, dict[str, Any]]:
    """
    Build a compact decision graph from the OD's verified alternatives only.

    Junctions = branch/merge points of that path union (+ terminals). This keeps
    macro count small so discrete energy flooring stays scientifically usable.
    """
    from morocco_etruck.optimization.route_choice_graph import (
        PathRecord,
        contract_to_decision_graph,
        union_path_digraph,
    )

    records: list[PathRecord] = []
    for row in path_rows:
        if str(row.get("od_id")) != od_id:
            continue
        path = [int(x) for x in json.loads(row["node_path_json"])]
        records.append(
            PathRecord(
                od_id=od_id,
                node_path=path,
                length_m=float(row["length_m"]),
                edge_keys=[],
                method=str(row.get("method") or ""),
                jaccard_distance_vs_shortest=float(row.get("jaccard_distance_vs_shortest") or 0.0),
            )
        )
    if not records:
        raise ValueError(f"No path alternatives for {od_id}")

    o_nid = int(records[0].node_path[0])
    d_nid = int(records[0].node_path[-1])
    # Prefer consistent terminals across records
    for r in records:
        if int(r.node_path[0]) != o_nid or int(r.node_path[-1]) != d_nid:
            # Still allow; terminals from first shortest if present
            pass
    short = next((r for r in records if r.method == "shortest_distance"), records[0])
    o_nid = int(short.node_path[0])
    d_nid = int(short.node_path[-1])

    terminals = {origin_name: o_nid, dest_name: d_nid}
    union = union_path_digraph(G, [r.node_path for r in records])
    rcg = contract_to_decision_graph(
        union,
        terminals=terminals,
        path_records=records,
        speed_policy=speed_policy or {},
        od_pairs=[{"id": od_id, "origin": origin_name, "destination": dest_name}],
    )
    return list(rcg.arcs), origin_name, dest_name, dict(rcg.decision_nodes)


def _flat_weather_placeholder() -> CorridorWeatherDay:
    """Neutral weather when pilot fixtures are unavailable."""
    pts = {
        "mid": WeatherPointDay(
            point_id="mid",
            lat=32.0,
            lon=-8.0,
            date="synthetic",
            T_mean_c=20.0,
            wind_speed_mean_mps=2.0,
            wind_dir_mean_deg=270.0,
            pressure_mean_hpa=1013.25,
        )
    }
    return CorridorWeatherDay(day_id="flat", date="synthetic", points=pts)


def load_weather_for_multiroute(
    *,
    root: Path,
    morocco_pilot_yaml: Path,
    weather_id: str = "cool",
) -> tuple[CorridorWeatherDay, bool]:
    """
    Returns (weather, assumed).

    ``assumed=True`` when historical pilot fixtures are missing and a synthetic
    placeholder is used — not valid for historical-weather certification.
    """
    try:
        from morocco_etruck.optimization.morocco_adapter import load_weather

        cfg = yaml.safe_load(Path(morocco_pilot_yaml).read_text(encoding="utf-8"))
        return load_weather(cfg, weather_id=weather_id, root=root), False
    except Exception:
        return _flat_weather_placeholder(), True


def try_load_macro_dem(elevation_dir: Path, arc_id: str) -> TerrainSample | None:
    if not arc_id:
        return None
    path = elevation_dir / f"arc_{arc_id}.json"
    if not path.exists():
        return None
    try:
        return load_profile(path)
    except Exception:
        return None


def build_macro_with_terrain(
    G,
    arc: DecisionArc,
    *,
    terrain_mode: str,
    elevation_dir: Path,
    road_cost_per_km: float,
) -> tuple[MacroArcSpec, str, bool]:
    """
    Build geometry-owned macro.

    DEM sources (never A3 corridor files):
      1. per-child ``arc_{arc_id}.json`` if present
      2. parent profile ``arc_{parent_arc_id}.json`` windowed at ``macro_s0_m``

    In DEM mode, missing required terrain ⇒ ``dem_unavailable`` (not a silent
    flat result labeled as DEM). Flat remains an explicit separate scenario.
    """
    mode = terrain_mode
    corridor = None
    note = "flat"
    dem_ok = True
    macro_s0 = 0.0
    if terrain_mode == "dem":
        corridor = try_load_macro_dem(elevation_dir, arc.arc_id)
        if corridor is not None:
            note = "dem_per_arc"
            macro_s0 = 0.0
        elif arc.parent_arc_id:
            corridor = try_load_macro_dem(elevation_dir, arc.parent_arc_id)
            if corridor is not None:
                note = "dem_parent_slice"
                macro_s0 = float(arc.macro_s0_m)
            else:
                mode = "flat"
                note = "dem_unavailable"
                dem_ok = False
                macro_s0 = 0.0
        else:
            mode = "flat"
            note = "dem_unavailable"
            dem_ok = False
            macro_s0 = 0.0
    macro = build_macro_arc(
        G,
        u_name=arc.u,
        v_name=arc.v,
        path_nodes=arc.path_nodes,
        terrain_mode=mode,
        corridor_profile=corridor,
        macro_s0_m=macro_s0,
        road_cost_per_km=road_cost_per_km,
    )
    macro.meta["arc_id"] = arc.arc_id
    macro.meta["parent_arc_id"] = arc.parent_arc_id
    macro.meta["terrain_note"] = note
    macro.meta["dem_ok"] = dem_ok
    macro.meta["scenario_speed_kmh"] = arc.scenario_speed_kmh
    macro.meta["hgv_access"] = arc.hgv_access
    return macro, note, dem_ok


def drive_table_for_macro(
    macro: MacroArcSpec,
    *,
    vehicle: VehicleParams,
    fridge: RefrigerationParams,
    weather: CorridorWeatherDay,
    gcm_kg: float,
    refrigeration_on: bool,
    power_source: str,
    E_truck_min: int,
    E_truck_cap: int,
    E_trailer_min: int | None,
    E_trailer_cap: int | None,
    energy_quantum_kwh: int,
    time_step_min: int,
    vehicle_yaml: Path,
    fridge_yaml: Path,
    cache_dir: Path | None,
) -> dict:
    th = terrain_sample_hash(
        list(macro.terrain.distances_m),
        list(macro.terrain.elevations_m),
        str(macro.terrain.source),
        list(macro.terrain.valid_mask) if macro.terrain.valid_mask is not None else None,
    )
    arc_id = str(macro.meta.get("arc_id") or make_arc_id(macro.osm_edge_pairs))
    fp = build_drive_table_fingerprint(
        vehicle_yaml=vehicle_yaml,
        fridge_yaml=fridge_yaml,
        weather_points={k: vars(v) for k, v in weather.points.items()},
        terrain_mode=str(macro.meta.get("terrain_mode") or "flat"),
        terrain_source=str(macro.terrain.source),
        terrain_hash=th,
        macro_u=macro.u,
        macro_v=f"{macro.v}:{arc_id}",
        edge_pairs=macro.osm_edge_pairs,
        length_m=macro.length_m,
        gcm_kg=gcm_kg,
        refrigeration_on=refrigeration_on,
        power_source=power_source,
        energy_quantum_kwh=energy_quantum_kwh,
        time_step_min=time_step_min,
        E_truck_min=E_truck_min,
        E_truck_cap=E_truck_cap,
        E_trailer_min=E_trailer_min,
        E_trailer_cap=E_trailer_cap,
    )
    if cache_dir is not None:
        cpath = cache_dir / f"{arc_id}.json"
        cached = load_cached_table(cpath, fp)
        if cached is not None:
            return cached
    table = build_drive_table(
        macro,
        vehicle=vehicle,
        weather=weather,
        fridge_cfg=fridge,
        gcm_kg=gcm_kg,
        refrigeration_on=refrigeration_on,
        power_source=power_source,
        E_truck_min=E_truck_min,
        E_truck_cap=E_truck_cap,
        E_trailer_min=E_trailer_min,
        E_trailer_cap=E_trailer_cap,
        energy_quantum_kwh=energy_quantum_kwh,
        time_step_min=time_step_min,
    )
    if cache_dir is not None:
        save_cached_table(cache_dir / f"{arc_id}.json", fp, table)
    return table


def build_path_union_routing_instance(
    *,
    G,
    dec: dict[str, Any],
    path_rows: Sequence[dict[str, Any]],
    od_id: str,
    vehicle: VehicleParams,
    fridge: RefrigerationParams,
    weather: CorridorWeatherDay,
    vehicle_yaml: Path,
    fridge_yaml: Path,
    gcm_kg: float,
    refrigeration_on: bool,
    power_source: str,
    terrain_mode: str,
    elevation_dir: Path,
    cache_dir: Path | None,
    time_step_min: int,
    energy_quantum_kwh: int,
    deadline_steps: int,
    E_truck_init: int,
    E_truck_cap: int,
    E_truck_min: int,
    E_trailer_init: int | None = None,
    E_trailer_cap: int | None = None,
    E_trailer_min: int | None = None,
    road_cost_per_km: float = 1.0,
    stations: dict[str, StationData] | None = None,
    active_stations: set[str] | None = None,
    decision_arcs: list[DecisionArc] | None = None,
    origin: str | None = None,
    destination: str | None = None,
    decision_nodes: dict[str, Any] | None = None,
    wait_max_steps: int = 0,
    name: str | None = None,
) -> tuple[RoutingInstance, MultirouteMissionContext]:
    if decision_arcs is None:
        arcs_in, origin_n, dest_n, nodes = induce_od_decision_arcs(dec, path_rows, od_id)
    else:
        arcs_in = decision_arcs
        assert origin is not None and destination is not None and decision_nodes is not None
        origin_n, dest_n, nodes = origin, destination, decision_nodes

    macros: dict[str, MacroArcSpec] = {}
    notes: list[str] = []
    arc_data: list[ArcData] = []
    dem_complete = True
    weather_assumed = bool(getattr(weather, "date", "") == "synthetic") or str(
        getattr(weather, "day_id", "")
    ) in {"flat", "synthetic"}
    node_names = set(nodes.keys()) | {origin_n, dest_n}
    if stations:
        for sid, st in stations.items():
            node_names.add(sid)
            node_names.add(st.node)

    for darc in arcs_in:
        macro, tnote, dem_ok = build_macro_with_terrain(
            G,
            darc,
            terrain_mode=terrain_mode,
            elevation_dir=elevation_dir,
            road_cost_per_km=road_cost_per_km,
        )
        notes.append(f"{darc.arc_id}:{tnote}")
        if terrain_mode == "dem" and not dem_ok:
            dem_complete = False
        table = drive_table_for_macro(
            macro,
            vehicle=vehicle,
            fridge=fridge,
            weather=weather,
            gcm_kg=gcm_kg,
            refrigeration_on=refrigeration_on,
            power_source=power_source,
            E_truck_min=E_truck_min,
            E_truck_cap=E_truck_cap,
            E_trailer_min=E_trailer_min,
            E_trailer_cap=E_trailer_cap,
            energy_quantum_kwh=energy_quantum_kwh,
            time_step_min=time_step_min,
            vehicle_yaml=vehicle_yaml,
            fridge_yaml=fridge_yaml,
            cache_dir=cache_dir,
        )
        macros[darc.arc_id] = macro
        node_names.add(darc.u)
        node_names.add(darc.v)
        arc_data.append(
            ArcData(
                u=darc.u,
                v=darc.v,
                dt_steps=1,
                dE_truck_kwh=0,
                dE_trailer_kwh=0,
                road_cost=max(1, int(round(macro.length_m / 1000.0 * max(road_cost_per_km, 0.0))))
                if road_cost_per_km > 0
                else max(1, int(round(macro.length_m / 1000.0))),
                power_ok=True,
                drive_table=table,
                arc_id=darc.arc_id,
            )
        )

    # Stationary loads (W) for CHARGE accounting
    aux_w = float(vehicle.P_aux_w)
    t_amb = float(weather.T_corridor_mean_c)
    tru_w = float(tru_electrical_power_w(t_amb, fridge)) if refrigeration_on else 0.0

    inst = RoutingInstance(
        name=name or f"multiroute_union_{od_id}",
        nodes=sorted(node_names),
        arcs=arc_data,
        origin=origin_n,
        destination=dest_n,
        deadline_steps=deadline_steps,
        E_truck_cap=E_truck_cap,
        E_truck_min=E_truck_min,
        E_truck_init=E_truck_init,
        E_trailer_cap=E_trailer_cap,
        E_trailer_min=E_trailer_min,
        E_trailer_init=E_trailer_init,
        stations=stations or {},
        active_stations=set(active_stations or []),
        power_source=power_source,  # type: ignore[arg-type]
        refrigeration_on=refrigeration_on,
        aux_w=aux_w,
        tru_mean_w=tru_w,
        wait_max_steps=wait_max_steps,
        time_step_min=time_step_min,
        energy_quantum_kwh=energy_quantum_kwh,
        notes=(
            "Task 05B path-union MRLS with DRIVE tables; "
            "claim_scope=path_union_of_verified_alternatives_only"
        ),
    )
    if terrain_mode == "dem" and not dem_complete:
        notes.append("dem_incomplete_scenario_indeterminate")
    if weather_assumed:
        notes.append("weather_assumed_synthetic_placeholder")
    ctx = MultirouteMissionContext(
        od_id=od_id,
        macros_by_arc_id=macros,
        vehicle=vehicle,
        fridge=fridge,
        weather=weather,
        gcm_kg=gcm_kg,
        refrigeration_on=refrigeration_on,
        power_source=power_source,
        time_step_min=time_step_min,
        terrain_mode=terrain_mode,
        notes=notes,
        dem_complete=dem_complete if terrain_mode == "dem" else True,
        weather_assumed=weather_assumed,
    )
    return inst, ctx
