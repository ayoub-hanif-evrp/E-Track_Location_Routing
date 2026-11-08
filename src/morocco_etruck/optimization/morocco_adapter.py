"""Build Moroccan fixed-corridor RoutingInstance + DRIVE tables (Task 03B)."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd
import yaml
from morocco_etruck.baseline_routing import (
    a3_motorway_subgraph,
    directional_a3_components,
    shortest_path_length_m,
)
from morocco_etruck.energy.refrigeration import RefrigerationParams, load_refrigeration
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
from morocco_etruck.optimization.problem import (
    ArcData,
    RoutingInstance,
    StationData,
)
from morocco_etruck.road_network import geodesic_length_m, load_graph_from_csv


ROOT = Path(__file__).resolve().parents[3]


@dataclass
class HypotheticalStation:
    key: str
    node: str
    official_name: str
    osm_id: str
    lat: float
    lon: float
    connected_node_id: int
    path_index: int
    snap_distance_m: float
    travel_direction: str
    hgv_status: str


@dataclass
class MoroccoMissionContext:
    direction: str
    path_nodes: list[int]
    stations: list[HypotheticalStation]
    macros: list[MacroArcSpec]
    vehicle: VehicleParams
    fridge: RefrigerationParams
    weather: CorridorWeatherDay
    gcm_kg: float
    gcm_label: str
    terrain_mode: str
    refrigeration_on: bool
    power_source: str
    energy_quantum_kwh: int
    time_step_min: int
    deadline_steps: int
    wait_max_steps: int
    cfg: dict[str, Any]
    drive_tables: dict[tuple[str, str], dict] = field(default_factory=dict)


def load_pilot_config(path: str | Path | None = None) -> dict[str, Any]:
    p = Path(path) if path else ROOT / "configs/optimization/morocco_pilot.yaml"
    return yaml.safe_load(p.read_text(encoding="utf-8"))


def _resolve(root: Path, rel: str) -> Path:
    p = Path(rel)
    return p if p.is_absolute() else root / p


def load_weather(
    cfg: dict[str, Any],
    *,
    weather_id: str,
    root: Path = ROOT,
) -> CorridorWeatherDay:
    energy_cfg = yaml.safe_load(
        _resolve(root, cfg["energy_pilot_config"]).read_text(encoding="utf-8")
    )
    date = energy_cfg["weather_days"][weather_id]["default_date"]
    points_cfg = energy_cfg["corridor_weather_points"]
    for d in (
        _resolve(root, cfg["weather_cache_dir"]),
        _resolve(root, cfg["weather_fixture_dir"]),
    ):
        pts: dict[str, WeatherPointDay] = {}
        ok = True
        for pid in points_cfg:
            fpath = d / f"{pid}_{date}.json"
            if not fpath.exists():
                ok = False
                break
            raw = json.loads(fpath.read_text(encoding="utf-8"))
            pts[pid] = WeatherPointDay(**raw)
        if ok and pts:
            return CorridorWeatherDay(day_id=weather_id, date=date, points=pts)
    raise FileNotFoundError(f"No weather fixtures for {weather_id} date={date}")


def load_baseline_path(
    G,
    direction: str,
    baseline_json: Path,
) -> list[int]:
    cache = baseline_json.parent / f"_path_{direction}.json"
    if cache.exists():
        return [int(x) for x in json.loads(cache.read_text(encoding="utf-8"))]
    bj = json.loads(baseline_json.read_text(encoding="utf-8"))
    H = a3_motorway_subgraph(G)
    southbound, northbound = directional_a3_components(H)
    graph = southbound if direction == "casablanca_to_agadir" else northbound
    src = bj["anchors"][direction]["source"]
    tgt = bj["anchors"][direction]["target"]
    path, _ = shortest_path_length_m(graph, src, tgt)
    path_i = [int(x) for x in path]
    cache.write_text(json.dumps(path_i), encoding="utf-8")
    return path_i


def _match_direction(travel: str, wanted: str) -> bool:
    a = travel.replace(" ", "").lower()
    b = wanted.replace(" ", "").lower()
    # tolerate ascii arrows
    for ch in ("→", "-->", "->", "—"):
        a = a.replace(ch, ">")
        b = b.replace(ch, ">")
    return a == b or wanted.lower() in travel.lower()


def select_hypothetical_stations(
    sites: pd.DataFrame,
    *,
    direction: str,
    path_nodes: list[int],
    station_specs: list[dict[str, Any]],
    G,
) -> list[HypotheticalStation]:
    path_index = {nid: i for i, nid in enumerate(path_nodes)}
    out: list[HypotheticalStation] = []
    for spec in station_specs:
        token = str(spec["name_contains"]).upper()
        wanted_dir = str(spec["travel_direction"])
        hits = sites[
            sites["official_name"].astype(str).str.upper().str.contains(token, regex=False)
            & (sites["directed_access_status"].astype(str) == "entrance_and_exit")
        ]
        chosen = None
        for _, row in hits.iterrows():
            if not _match_direction(str(row["travel_direction"]), wanted_dir):
                continue
            if pd.isna(row.get("connected_node_id")):
                continue
            cid = int(row["connected_node_id"])
            if cid not in path_index:
                # snap to nearest path node (scenario uncertainty)
                best_i, best_d = 0, float("inf")
                for i, nid in enumerate(path_nodes):
                    d = geodesic_length_m(
                        [
                            (float(row["lon"]), float(row["lat"])),
                            (float(G.nodes[nid]["lon"]), float(G.nodes[nid]["lat"])),
                        ]
                    )
                    if d < best_d:
                        best_d = d
                        best_i = i
                cid = path_nodes[best_i]
                snap = best_d
                pidx = best_i
            else:
                snap = float(row.get("connection_distance_m") or 0.0)
                pidx = path_index[cid]
            chosen = HypotheticalStation(
                key=str(spec["key"]),
                node=str(spec["key"]),
                official_name=str(row["official_name"]),
                osm_id=str(int(row["osm_id"])) if pd.notna(row.get("osm_id")) else "",
                lat=float(row["lat"]),
                lon=float(row["lon"]),
                connected_node_id=cid,
                path_index=pidx,
                snap_distance_m=snap,
                travel_direction=str(row["travel_direction"]),
                hgv_status=str(row.get("hgv_access_status") or "unknown"),
            )
            break
        if chosen is None:
            raise ValueError(f"No entrance_and_exit station for {spec} on {direction}")
        out.append(chosen)
    out.sort(key=lambda s: s.path_index)
    return out


def _corridor_profile(cfg: dict[str, Any], direction: str, mode: str, root: Path) -> TerrainSample | None:
    if mode != "dem":
        return None
    path = _resolve(root, cfg["elevation_dir"]) / f"elevation_profile_{direction}.json"
    if not path.exists():
        return None
    return load_profile(path)


def build_mission_context(
    cfg: dict[str, Any],
    *,
    direction: str,
    gcm: str,
    weather_id: str,
    terrain: str,
    refrigeration: str,
    power_source: str,
    energy_quantum_kwh: int | None = None,
    root: Path = ROOT,
    G=None,
) -> MoroccoMissionContext:
    energy_cfg = yaml.safe_load(
        _resolve(root, cfg["energy_pilot_config"]).read_text(encoding="utf-8")
    )
    vehicle = load_vehicle(_resolve(root, cfg["vehicle_config"]))
    fridge = load_refrigeration(_resolve(root, cfg["refrigeration_config"]))
    weather = load_weather(cfg, weather_id=weather_id, root=root)
    gcm_kg = float(energy_cfg["gcm_scenarios"][gcm]["gcm_kg"])
    gcm_label = str(energy_cfg["gcm_scenarios"][gcm]["label"])

    if G is None:
        G = load_graph_from_csv(
            _resolve(root, cfg["nodes_csv"]),
            _resolve(root, cfg["edges_csv"]),
        )
    path = load_baseline_path(G, direction, _resolve(root, cfg["baseline_json"]))
    sites = pd.read_csv(_resolve(root, cfg["candidate_sites_csv"]))
    stations = select_hypothetical_stations(
        sites,
        direction=direction,
        path_nodes=path,
        station_specs=list(cfg["stations_by_direction"][direction]),
        G=G,
    )

    corridor_prof = _corridor_profile(cfg, direction, terrain, root)
    # cumulative distance to each path node
    s_at: list[float] = [0.0]
    for i in range(1, len(path)):
        u, v = path[i - 1], path[i]
        data = G.get_edge_data(u, v)
        if data is None:
            raise KeyError((u, v))
        if G.is_multigraph():
            length = min(float(d.get("length_m") or 0.0) for d in data.values())
        else:
            length = float(data.get("length_m") or 0.0)
        s_at.append(s_at[-1] + length)

    decision_idx = [0] + [s.path_index for s in stations] + [len(path) - 1]
    decision_names = ["O"] + [s.node for s in stations] + ["D"]
    macros: list[MacroArcSpec] = []
    for i in range(len(decision_names) - 1):
        i0, i1 = decision_idx[i], decision_idx[i + 1]
        if i1 <= i0:
            raise ValueError(f"non-increasing decision indices {decision_names[i]}->{decision_names[i+1]}")
        sub = path[i0 : i1 + 1]
        macros.append(
            build_macro_arc(
                G,
                u_name=decision_names[i],
                v_name=decision_names[i + 1],
                path_nodes=sub,
                terrain_mode=terrain,
                corridor_profile=corridor_prof,
                macro_s0_m=s_at[i0],
                road_cost_per_km=float(cfg.get("road_cost_per_km", 0.0)),
            )
        )

    q = int(energy_quantum_kwh if energy_quantum_kwh is not None else cfg["energy_quantum_kwh"])
    return MoroccoMissionContext(
        direction=direction,
        path_nodes=path,
        stations=stations,
        macros=macros,
        vehicle=vehicle,
        fridge=fridge,
        weather=weather,
        gcm_kg=gcm_kg,
        gcm_label=gcm_label,
        terrain_mode=terrain,
        refrigeration_on=(refrigeration == "on"),
        power_source=power_source,
        energy_quantum_kwh=q,
        time_step_min=int(cfg["time_step_min"]),
        deadline_steps=int(cfg["deadline_steps"]),
        wait_max_steps=int(cfg.get("wait_max_steps", 0)),
        cfg=cfg,
    )


def _quantize_capacity(usable_kwh: float, quantum: int, soc_min: float, soc_init: float) -> tuple[int, int, int]:
    cap = int(math.floor(usable_kwh / quantum) * quantum)
    emin = int(math.ceil((soc_min * usable_kwh) / quantum) * quantum)
    einit = int(math.floor((soc_init * usable_kwh) / quantum) * quantum)
    einit = min(cap, max(emin, einit))
    return emin, einit, cap


def _station_price(cfg: dict[str, Any], key: str, price_mode: str) -> int:
    ch = cfg["charger"]
    if price_mode == "differentiated":
        return int(ch["price_differentiated_cents"].get(key, ch["price_uniform_cents"]))
    return int(ch["price_uniform_cents"])


def resolve_active_stations(
    ctx: MoroccoMissionContext,
    *,
    active_policy: str,
    preferred_station: str | None = None,
) -> set[str]:
    keys = [s.key for s in ctx.stations]
    if active_policy == "none":
        return set()
    if active_policy == "all":
        return set(keys)
    if active_policy == "one":
        if preferred_station and preferred_station in keys:
            return {preferred_station}
        return {keys[len(keys) // 2]} if keys else set()
    raise ValueError(f"unknown active_policy {active_policy}")


def build_routing_instance(
    ctx: MoroccoMissionContext,
    *,
    active_stations: set[str],
    price_mode: str = "uniform",
    name: str = "morocco",
    table_cache_dir: Path | None = None,
) -> RoutingInstance:
    q = ctx.energy_quantum_kwh
    E_min, E_init, E_cap = _quantize_capacity(
        ctx.vehicle.usable_kwh, q, ctx.vehicle.soc_min, ctx.vehicle.soc_initial
    )
    El_min = El_init = El_cap = None
    if ctx.power_source == "B" and ctx.refrigeration_on:
        El_min, El_init, El_cap = _quantize_capacity(
            ctx.fridge.trailer_usable_kwh,
            q,
            ctx.fridge.trailer_soc_min,
            ctx.fridge.trailer_soc_initial,
        )

    vehicle_yaml = _resolve(ROOT, ctx.cfg["vehicle_config"])
    fridge_yaml = _resolve(ROOT, ctx.cfg["refrigeration_config"])
    weather_ser = {
        pid: {
            "T_mean_c": wp.T_mean_c,
            "wind_speed_mean_mps": wp.wind_speed_mean_mps,
            "wind_dir_mean_deg": wp.wind_dir_mean_deg,
            "date": wp.date,
        }
        for pid, wp in ctx.weather.points.items()
    }

    # Build / cache DRIVE tables (fingerprinted)
    arcs: list[ArcData] = []
    for macro in ctx.macros:
        cache_key = (
            f"{ctx.direction}_{macro.u}_{macro.v}_{ctx.terrain_mode}_{ctx.gcm_label}_"
            f"{ctx.weather.day_id}_refrig{int(ctx.refrigeration_on)}_{ctx.power_source}_q{q}"
        )
        t_hash = terrain_sample_hash(
            macro.terrain.distances_m,
            macro.terrain.elevations_m,
            macro.terrain.source,
            valid_mask=macro.terrain.valid_mask,
        )
        fp = build_drive_table_fingerprint(
            vehicle_yaml=vehicle_yaml,
            fridge_yaml=fridge_yaml,
            weather_points=weather_ser,
            terrain_mode=ctx.terrain_mode,
            terrain_source=macro.terrain.source,
            terrain_hash=t_hash,
            macro_u=macro.u,
            macro_v=macro.v,
            edge_pairs=macro.osm_edge_pairs,
            length_m=macro.length_m,
            gcm_kg=ctx.gcm_kg,
            refrigeration_on=ctx.refrigeration_on,
            power_source=ctx.power_source,
            energy_quantum_kwh=q,
            time_step_min=ctx.time_step_min,
            E_truck_min=E_min,
            E_truck_cap=E_cap,
            E_trailer_min=El_min,
            E_trailer_cap=El_cap,
        )
        table = None
        cache_path = None
        if table_cache_dir is not None:
            table_cache_dir.mkdir(parents=True, exist_ok=True)
            cache_path = table_cache_dir / f"{cache_key}.json"
            table = load_cached_table(cache_path, fp)
        if table is None:
            table = build_drive_table(
                macro,
                vehicle=ctx.vehicle,
                weather=ctx.weather,
                fridge_cfg=ctx.fridge,
                gcm_kg=ctx.gcm_kg,
                refrigeration_on=ctx.refrigeration_on,
                power_source=ctx.power_source,
                E_truck_min=E_min,
                E_truck_cap=E_cap,
                E_trailer_min=El_min,
                E_trailer_cap=El_cap,
                energy_quantum_kwh=q,
                time_step_min=ctx.time_step_min,
            )
            if cache_path is not None:
                save_cached_table(cache_path, fp, table)
        ctx.drive_tables[(macro.u, macro.v)] = table
        arcs.append(
            ArcData(
                u=macro.u,
                v=macro.v,
                dt_steps=1,
                dE_truck_kwh=0,
                dE_trailer_kwh=0,
                road_cost=macro.road_cost,
                power_ok=True,
                drive_table=table,
            )
        )

    ch = ctx.cfg["charger"]
    stations: dict[str, StationData] = {}
    for s in ctx.stations:
        stations[s.node] = StationData(
            node=s.node,
            power_kw=float(ch["power_kw"]),
            eta=float(ch["eta"]),
            price_cents_per_grid_kwh=_station_price(ctx.cfg, s.key, price_mode),
            compatible=True,
            official_name=s.official_name,
            hypothetical_access=True,
            hgv_status=s.hgv_status,
            osm_id=s.osm_id,
            snap_distance_m=s.snap_distance_m,
        )

    nodes = ["O"] + [s.node for s in ctx.stations] + ["D"]
    # Continuous stationary watts (action-level integration in resource_transitions)
    aux_w = float(ctx.vehicle.P_aux_w)
    tru_mean_w = 0.0
    if ctx.refrigeration_on:
        from morocco_etruck.energy.refrigeration import refrigeration_energy_j

        mid = next(iter(ctx.weather.points.values()))
        step_s = ctx.time_step_min * 60.0
        e_j = refrigeration_energy_j(
            duration_s=step_s,
            T_amb_c=mid.T_mean_c,
            params=ctx.fridge,
            refrigeration_on=True,
        )
        tru_mean_w = e_j / step_s  # mean W over one discrete time step

    return RoutingInstance(
        name=name,
        nodes=nodes,
        arcs=arcs,
        origin="O",
        destination="D",
        deadline_steps=ctx.deadline_steps,
        E_truck_cap=E_cap,
        E_truck_min=E_min,
        E_truck_init=E_init,
        E_trailer_cap=El_cap,
        E_trailer_min=El_min,
        E_trailer_init=El_init,
        stations=stations,
        active_stations=set(active_stations),
        power_source=ctx.power_source,  # type: ignore[arg-type]
        refrigeration_on=ctx.refrigeration_on,
        aux_kwh_per_step=0,
        tru_kwh_per_step=0,
        aux_w=aux_w,
        tru_mean_w=tru_mean_w,
        wait_max_steps=ctx.wait_max_steps,
        time_step_min=ctx.time_step_min,
        energy_quantum_kwh=q,
        notes=str(ctx.cfg.get("disclaimer", "")),
    )


def corridor_map_features(ctx: MoroccoMissionContext) -> dict[str, Any]:
    """GeoJSON FeatureCollection: baseline path + hypothetical stops."""
    features = []
    # Full path geometry from macros
    coords: list[list[float]] = []
    for m in ctx.macros:
        for c in m.geometry.coords:
            xy = [float(c[0]), float(c[1])]
            if not coords or coords[-1] != xy:
                coords.append(xy)
    features.append(
        {
            "type": "Feature",
            "geometry": {"type": "LineString", "coordinates": coords},
            "properties": {
                "layer": "baseline_path",
                "direction": ctx.direction,
                "legend": "OSM A3 directed baseline (not HGV-certified)",
            },
        }
    )
    for s in ctx.stations:
        features.append(
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [s.lon, s.lat]},
                "properties": {
                    "layer": "hypothetical_charger",
                    "key": s.key,
                    "official_name": s.official_name,
                    "hypothetical_access": True,
                    "hgv_status": s.hgv_status,
                    "snap_distance_m": s.snap_distance_m,
                    "legend": "Assumed access (entrance_and_exit topology); not verified HGV",
                },
            }
        )
    return {"type": "FeatureCollection", "features": features}
