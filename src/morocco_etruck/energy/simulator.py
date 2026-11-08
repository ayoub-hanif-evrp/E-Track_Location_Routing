"""Route-level energy / SOC evaluation (independent of charger logic)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Sequence

from shapely.geometry import LineString

from morocco_etruck.energy.refrigeration import (
    RefrigerationParams,
    refrigeration_energy_j,
)
from morocco_etruck.energy.terrain import (
    TerrainSample,
    edge_dz_from_profile,
    elevation_at_distance,
    flat_profile,
    split_route_into_edges,
)
from morocco_etruck.energy.traction import segment_traction_energy
from morocco_etruck.energy.vehicle import VehicleParams, mass_from_gcm
from morocco_etruck.energy.weather import (
    CorridorWeatherDay,
    heading_deg,
    wind_along_travel_mps,
)

PowerSource = Literal["A", "B"]
J_PER_KWH = 3.6e6


@dataclass
class EdgeInput:
    """One evaluation edge with geometry and length."""

    geometry: LineString
    length_m: float


@dataclass
class EnergyResult:
    distance_m: float
    duration_s: float
    E_traction_j: float
    E_aux_j: float
    E_refrig_j: float
    E_net_tractor_j: float
    E_trailer_refrig_j: float
    soc_final: float
    trailer_soc_final: float | None
    mission_feasible: bool
    terrain_source: str
    tags: dict[str, Any] = field(default_factory=dict)
    cumulative_energy_kwh: list[float] = field(default_factory=list)
    cumulative_distance_m: list[float] = field(default_factory=list)
    elevations_m: list[float] = field(default_factory=list)

    @property
    def distance_km(self) -> float:
        return self.distance_m / 1000.0

    @property
    def duration_h(self) -> float:
        return self.duration_s / 3600.0

    @property
    def E_traction_kWh(self) -> float:
        return self.E_traction_j / J_PER_KWH

    @property
    def E_aux_kWh(self) -> float:
        return self.E_aux_j / J_PER_KWH

    @property
    def E_refrig_kWh(self) -> float:
        return self.E_refrig_j / J_PER_KWH

    @property
    def E_net_tractor_kWh(self) -> float:
        return self.E_net_tractor_j / J_PER_KWH


def _clip(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def edges_from_route_geometry(
    geom: LineString,
    *,
    max_edge_m: float = 2000.0,
) -> list[EdgeInput]:
    return [EdgeInput(geometry=ls, length_m=L) for ls, L in split_route_into_edges(geom, max_edge_m=max_edge_m)]


def evaluate_route(
    edges: Sequence[EdgeInput],
    vehicle: VehicleParams,
    weather: CorridorWeatherDay,
    fridge_cfg: RefrigerationParams,
    *,
    gcm_kg: float,
    refrigeration_on: bool = False,
    power_source: PowerSource = "A",
    terrain: TerrainSample | None = None,
    speed_mps: float | None = None,
    accel_mps2: float = 0.0,
    tags: dict[str, Any] | None = None,
) -> EnergyResult:
    """
    Evaluate traction + aux + refrigeration energy and tractor SOC along a route.

    Config A: TRU energy deducted from tractor usable battery.
    Config B: TRU energy from trailer pack only; tractor SOC unaffected by TRU.
    """
    if not edges:
        raise ValueError("edges must be non-empty")

    v = vehicle.cruise_mps if speed_mps is None else float(speed_mps)
    if v <= 0:
        raise ValueError("speed must be positive")

    mass = mass_from_gcm(gcm_kg)
    # Build a flat profile if none provided, using concatenated geometry
    if terrain is None:
        from shapely.ops import linemerge

        geoms = [e.geometry for e in edges]
        merged = linemerge(geoms)
        if merged.geom_type == "MultiLineString":
            # concatenate coordinates
            coords = []
            for g in merged.geoms:
                coords.extend(list(g.coords))
            route_geom = LineString(coords)
        else:
            route_geom = merged
        terrain = flat_profile(route_geom)

    soc = vehicle.soc_initial
    trailer_soc: float | None = fridge_cfg.trailer_soc_initial if power_source == "B" else None

    E_trac = 0.0
    E_aux = 0.0
    E_refrig_total = 0.0
    E_refrig_tractor = 0.0
    E_refrig_trailer = 0.0
    duration = 0.0
    distance = 0.0
    s_cursor = 0.0

    cum_e: list[float] = [0.0]
    cum_d: list[float] = [0.0]
    elevs: list[float] = [terrain.elevations_m[0] if terrain.elevations_m else 0.0]

    for edge in edges:
        L = edge.length_m
        if L <= 0:
            raise ValueError("zero-length edge is invalid")
        coords = list(edge.geometry.coords)
        lon1, lat1 = coords[0][0], coords[0][1]
        lon2, lat2 = coords[-1][0], coords[-1][1]
        mid_lat = 0.5 * (lat1 + lat2)
        mid_lon = 0.5 * (lon1 + lon2)
        wp = weather.nearest(mid_lat, mid_lon)
        rho = wp.air_density_kg_m3(vehicle.air_density_default_kg_m3)
        head = heading_deg(lon1, lat1, lon2, lat2)
        wind_along = wind_along_travel_mps(wp.wind_speed_mean_mps, wp.wind_dir_mean_deg, head)
        dz = edge_dz_from_profile(terrain, s_cursor, L)

        seg = segment_traction_energy(
            length_m=L,
            dz_m=dz,
            mass_kg=mass,
            v_mps=v,
            wind_along_travel_mps=wind_along,
            rho_kg_m3=rho,
            vehicle=vehicle,
            soc=soc,
            accel_mps2=accel_mps2,
        )

        # Cap regen energy by SOC headroom
        e_trac = seg.E_batt_trac_j
        if e_trac < 0:
            headroom_j = (vehicle.soc_max - soc) * vehicle.usable_j
            if -e_trac > headroom_j:
                e_trac = -headroom_j

        e_aux = vehicle.P_aux_w * seg.dt_s
        e_ref = refrigeration_energy_j(
            duration_s=seg.dt_s,
            T_amb_c=wp.T_mean_c,
            params=fridge_cfg,
            refrigeration_on=refrigeration_on,
        )

        # Tractor deductions
        e_tractor = e_trac + e_aux
        if power_source == "A":
            e_tractor += e_ref
            E_refrig_tractor += e_ref
        else:
            # Config B: trailer only
            E_refrig_trailer += e_ref
            if trailer_soc is not None:
                trailer_soc = _clip(
                    trailer_soc - e_ref / fridge_cfg.trailer_usable_j,
                    0.0,
                    1.0,
                )

        soc = _clip(soc - e_tractor / vehicle.usable_j, 0.0, vehicle.soc_max)

        E_trac += e_trac
        E_aux += e_aux
        E_refrig_total += e_ref
        duration += seg.dt_s
        distance += L
        s_cursor += L

        cum_e.append((E_trac + E_aux + (E_refrig_tractor if power_source == "A" else 0.0)) / J_PER_KWH)
        cum_d.append(distance)
        elevs.append(elevation_at_distance(terrain, s_cursor))

    E_net_tractor = E_trac + E_aux + E_refrig_tractor

    tractor_ok = soc >= vehicle.soc_min - 1e-12
    trailer_ok = True
    if power_source == "B" and refrigeration_on and trailer_soc is not None:
        trailer_ok = trailer_soc >= fridge_cfg.trailer_soc_min - 1e-12
    # Also infeasible if SOC hit 0 early with more discharge needed — clip already applied;
    # check net energy against available window
    available = (vehicle.soc_initial - vehicle.soc_min) * vehicle.usable_j
    if E_net_tractor > available + 1e-6:
        tractor_ok = False

    return EnergyResult(
        distance_m=distance,
        duration_s=duration,
        E_traction_j=E_trac,
        E_aux_j=E_aux,
        E_refrig_j=E_refrig_total,
        E_net_tractor_j=E_net_tractor,
        E_trailer_refrig_j=E_refrig_trailer,
        soc_final=soc,
        trailer_soc_final=trailer_soc,
        mission_feasible=bool(tractor_ok and trailer_ok),
        terrain_source=terrain.source,
        tags=dict(tags or {}),
        cumulative_energy_kwh=cum_e,
        cumulative_distance_m=cum_d,
        elevations_m=elevs,
    )
