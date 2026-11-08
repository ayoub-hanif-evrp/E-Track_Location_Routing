"""Macro-arc micro-profiles and state-dependent DRIVE tables (Task 03B)."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Sequence

from shapely.geometry import LineString

from morocco_etruck.energy.refrigeration import RefrigerationParams
from morocco_etruck.energy.simulator import EdgeInput, J_PER_KWH
from morocco_etruck.energy.terrain import (
    TerrainSample,
    assess_terrain_quality,
    densify_linestring,
    elevation_at_distance,
    flat_profile,
)
from morocco_etruck.energy.transitions import EnergyState, apply_drive
from morocco_etruck.energy.vehicle import VehicleParams
from morocco_etruck.energy.weather import CorridorWeatherDay
from morocco_etruck.optimization.problem import DriveTableEntry
from morocco_etruck.road_network import geodesic_length_m, path_edge_geometries


@dataclass
class MacroArcSpec:
    """Directed baseline subpath between consecutive decision nodes."""

    u: str
    v: str
    path_nodes: list[Any]
    osm_edge_pairs: list[tuple[Any, Any]]
    geometry: LineString
    length_m: float
    micro_edges: list[EdgeInput]
    terrain: TerrainSample
    terrain_quality_status: str
    road_cost: int = 0
    meta: dict[str, Any] = field(default_factory=dict)


def _edge_lines_along_path(G, path: Sequence[Any]) -> list[tuple[Any, Any, LineString, float]]:
    """Return (u, v, geometry, length_m) for each hop on the path."""
    from morocco_etruck.road_network import _best_edge_data
    from shapely import wkt

    out: list[tuple[Any, Any, LineString, float]] = []
    for u, v in zip(path[:-1], path[1:]):
        data = _best_edge_data(G, u, v)
        wkt_s = data.get("geometry_wkt") or ""
        if wkt_s:
            geom = wkt.loads(str(wkt_s))
            if not isinstance(geom, LineString):
                coords = list(geom.coords) if hasattr(geom, "coords") else []
                geom = LineString(coords)
        else:
            geom = LineString(
                [
                    (float(G.nodes[u]["lon"]), float(G.nodes[u]["lat"])),
                    (float(G.nodes[v]["lon"]), float(G.nodes[v]["lat"])),
                ]
            )
        length = float(data.get("length_m") or 0.0)
        if length <= 0:
            length = geodesic_length_m([(c[0], c[1]) for c in geom.coords])
        out.append((u, v, geom, length))
    return out


def _merge_lines(geoms: Sequence[LineString]) -> LineString:
    coords: list[tuple[float, float]] = []
    for g in geoms:
        seg = [(float(c[0]), float(c[1])) for c in g.coords]
        if not seg:
            continue
        if coords and seg[0] == coords[-1]:
            coords.extend(seg[1:])
        else:
            coords.extend(seg)
    if len(coords) < 2:
        raise ValueError("cannot merge empty geometry")
    return LineString(coords)


def build_micro_edges_from_path(
    G,
    path: Sequence[Any],
    *,
    max_edge_m: float = 2000.0,
) -> tuple[LineString, float, list[EdgeInput], list[tuple[Any, Any]]]:
    """
    Build micro-segment EdgeInputs owned by a macro-arc (OSM edges, optionally split).

    Each micro-edge has its own geometry; DEM sampling must be edge-local / macro-local,
    never a single baseline s_cursor reused across unrelated edges.
    """
    hops = _edge_lines_along_path(G, path)
    pairs = [(u, v) for u, v, _g, _L in hops]
    micro: list[EdgeInput] = []
    for _u, _v, geom, length in hops:
        if length <= max_edge_m:
            micro.append(EdgeInput(geometry=geom, length_m=length))
            continue
        # Split long OSM edges into ~max_edge_m chunks along the edge geometry
        pts = densify_linestring(geom, step_m=max_edge_m)
        if len(pts) < 2:
            micro.append(EdgeInput(geometry=geom, length_m=length))
            continue
        for i in range(len(pts) - 1):
            sub = LineString([pts[i], pts[i + 1]])
            Lm = geodesic_length_m([pts[i], pts[i + 1]])
            if Lm > 0:
                micro.append(EdgeInput(geometry=sub, length_m=Lm))
    merged = _merge_lines([h[2] for h in hops])
    total = sum(e.length_m for e in micro)
    return merged, total, micro, pairs


def terrain_for_macro_arc(
    geom: LineString,
    *,
    mode: str,
    corridor_profile: TerrainSample | None = None,
    macro_s0_m: float = 0.0,
) -> tuple[TerrainSample, str]:
    """
    Build a *macro-local* terrain profile (distances start at 0).

    Flat: dz=0. DEM: slice the corridor COP-DEM profile to this macro-arc window
    and renumber distances locally (avoids cross-arc s_cursor misuse).
    """
    if mode == "flat" or corridor_profile is None:
        prof = flat_profile(geom)
        return prof, "flat"

    length = geodesic_length_m([(c[0], c[1]) for c in geom.coords])
    step = float((corridor_profile.meta or {}).get("step_m", 150.0))
    n = max(2, int(math.ceil(length / max(step, 1.0))) + 1)
    local_d: list[float] = []
    elevs: list[float] = []
    for i in range(n):
        d_loc = min(length, i * step) if i < n - 1 else length
        z = elevation_at_distance(corridor_profile, macro_s0_m + d_loc)
        local_d.append(d_loc)
        elevs.append(z)
    prof = TerrainSample(
        distances_m=local_d,
        elevations_m=elevs,
        source=corridor_profile.source,
        meta={
            **dict(corridor_profile.meta or {}),
            "macro_s0_m": macro_s0_m,
            "macro_local": True,
        },
        valid_mask=[math.isfinite(z) for z in elevs],
    )
    q = assess_terrain_quality(prof)
    return prof, q.status


def build_macro_arc(
    G,
    *,
    u_name: str,
    v_name: str,
    path_nodes: Sequence[Any],
    terrain_mode: str,
    corridor_profile: TerrainSample | None,
    macro_s0_m: float,
    road_cost_per_km: float = 0.0,
    max_edge_m: float = 2000.0,
) -> MacroArcSpec:
    geom, length_m, micro, pairs = build_micro_edges_from_path(
        G, path_nodes, max_edge_m=max_edge_m
    )
    terrain, tq = terrain_for_macro_arc(
        geom,
        mode=terrain_mode,
        corridor_profile=corridor_profile,
        macro_s0_m=macro_s0_m,
    )
    road_cost = int(round(road_cost_per_km * (length_m / 1000.0)))
    return MacroArcSpec(
        u=u_name,
        v=v_name,
        path_nodes=list(path_nodes),
        osm_edge_pairs=pairs,
        geometry=geom,
        length_m=length_m,
        micro_edges=micro,
        terrain=terrain,
        terrain_quality_status=tq,
        road_cost=road_cost,
        meta={"terrain_mode": terrain_mode, "macro_s0_m": macro_s0_m},
    )


def _floor_energy_kwh(kwh: float, quantum: int) -> int:
    """Conservative remaining energy: never round up."""
    if quantum <= 0:
        raise ValueError("quantum must be > 0")
    return int(math.floor(kwh / quantum) * quantum)


def _ceil_time_steps(dt_s: float, time_step_min: int) -> int:
    step_s = time_step_min * 60.0
    return max(1, int(math.ceil(dt_s / step_s)))


def simulate_drive_from_soc(
    micro_edges: Sequence[EdgeInput],
    terrain: TerrainSample,
    *,
    soc0: float,
    trailer_soc0: float | None,
    vehicle: VehicleParams,
    weather: CorridorWeatherDay,
    fridge_cfg: RefrigerationParams,
    gcm_kg: float,
    refrigeration_on: bool,
    power_source: str,
) -> tuple[bool, float, float, float | None, str | None]:
    """
    Continuous micro-profile simulation.

    Returns (ok, dt_s, soc_end, trailer_soc_end, reason).
    """
    state = EnergyState(soc=soc0, trailer_soc=trailer_soc0)
    s_cursor = 0.0
    dt_total = 0.0
    for edge in micro_edges:
        r = apply_drive(
            state,
            edge,
            vehicle=vehicle,
            weather=weather,
            fridge_cfg=fridge_cfg,
            gcm_kg=gcm_kg,
            refrigeration_on=refrigeration_on,
            power_source=power_source,  # type: ignore[arg-type]
            terrain=terrain,
            s_cursor_m=s_cursor,
        )
        dt_total += r.dt_s
        s_cursor += edge.length_m
        if r.violation_reason:
            return False, dt_total, state.soc, state.trailer_soc, r.violation_reason
        state = r.next_state
    return True, dt_total, state.soc, state.trailer_soc, None


def build_drive_table(
    macro: MacroArcSpec,
    *,
    vehicle: VehicleParams,
    weather: CorridorWeatherDay,
    fridge_cfg: RefrigerationParams,
    gcm_kg: float,
    refrigeration_on: bool,
    power_source: str,
    E_truck_min: int,
    E_truck_cap: int,
    E_trailer_min: int | None,
    E_trailer_cap: int | None,
    energy_quantum_kwh: int,
    time_step_min: int,
) -> dict[tuple[int, int | None], DriveTableEntry]:
    """
    State-dependent DRIVE outcomes for every discrete start energy quantum.

    Conservatism: ceil travel time to time steps; floor ending kWh to quantum grid.
    """
    q = energy_quantum_kwh
    usable = float(vehicle.usable_kwh)
    table: dict[tuple[int, int | None], DriveTableEntry] = {}

    trailer_vals: list[int | None]
    if power_source == "B" and refrigeration_on and E_trailer_cap is not None:
        assert E_trailer_min is not None
        trailer_vals = list(range(E_trailer_min, E_trailer_cap + 1, q))
        t_usable = float(fridge_cfg.trailer_usable_kwh)
    else:
        trailer_vals = [None]
        t_usable = 1.0

    for Et in range(E_truck_min, E_truck_cap + 1, q):
        for El in trailer_vals:
            soc0 = Et / usable
            trailer_soc0 = None if El is None else El / t_usable
            ok, dt_s, soc_end, trailer_end, reason = simulate_drive_from_soc(
                macro.micro_edges,
                macro.terrain,
                soc0=soc0,
                trailer_soc0=trailer_soc0,
                vehicle=vehicle,
                weather=weather,
                fridge_cfg=fridge_cfg,
                gcm_kg=gcm_kg,
                refrigeration_on=refrigeration_on,
                power_source=power_source,
            )
            if not ok:
                table[(Et, El)] = DriveTableEntry(feasible=False, reason=reason)
                continue
            E_end = _floor_energy_kwh(soc_end * usable, q)
            if E_end < E_truck_min:
                table[(Et, El)] = DriveTableEntry(
                    feasible=False, reason="tractor_soc_floor_after_quantize"
                )
                continue
            El_end: int | None = None
            if El is not None and trailer_end is not None:
                El_end = _floor_energy_kwh(trailer_end * t_usable, q)
                if E_trailer_min is not None and El_end < E_trailer_min:
                    table[(Et, El)] = DriveTableEntry(
                        feasible=False, reason="trailer_soc_floor_after_quantize"
                    )
                    continue
            table[(Et, El)] = DriveTableEntry(
                feasible=True,
                dt_steps=_ceil_time_steps(dt_s, time_step_min),
                E_end_truck=E_end,
                E_end_trailer=El_end,
            )
    return table


def path_geometry_coords(G, path: Sequence[Any]) -> list[tuple[float, float]]:
    return path_edge_geometries(G, list(path))
