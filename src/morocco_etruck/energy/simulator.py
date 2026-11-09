"""Route-level energy / SOC evaluation (independent of charger logic)."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Literal, Sequence

from shapely.geometry import LineString

from morocco_etruck.energy.refrigeration import (
    RefrigerationParams,
    refrigeration_energy_j,
)
from morocco_etruck.energy.terrain import (
    TerrainQuality,
    TerrainSample,
    assess_terrain_quality,
    edge_dz_from_profile,
    elevation_at_distance,
    flat_profile,
    split_route_into_edges,
)
from morocco_etruck.energy.traction import segment_traction_energy
from morocco_etruck.energy.vehicle import VehicleParams, mass_from_gcm, validate_gcm
from morocco_etruck.energy.weather import (
    CorridorWeatherDay,
    heading_deg,
    wind_along_travel_mps,
)
from morocco_etruck.road_network import geodesic_length_m

PowerSource = Literal["A", "B"]
J_PER_KWH = 3.6e6


@dataclass
class EdgeInput:
    """One evaluation edge with geometry, geodesic length, and optional cruise speed."""

    geometry: LineString
    length_m: float
    # Assumed research cruise speed for this micro-segment (not observed HGV speed).
    speed_mps: float | None = None
    highway: str = ""
    speed_source: str = ""  # e.g. osm_maxspeed | class_default | vehicle_cruise


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
    mission_feasible: bool | None
    """True/False when evaluable; None when terrain/input status is indeterminate."""
    terrain_source: str
    terrain_quality_status: str
    power_feasible: bool
    soc_feasible: bool
    trailer_soc_feasible: bool
    minimum_soc: float
    minimum_trailer_soc: float | None
    first_violation_distance_km: float | None
    first_violation_reason: str | None
    E_regen_ideal_j: float
    E_regen_accepted_j: float
    E_regen_rejected_j: float
    continuous_power_exceeded: bool
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

    # Aliases matching pilot CSV naming
    @property
    def power_feasible_bool(self) -> bool:
        return self.power_feasible

    @property
    def soc_feasible_bool(self) -> bool:
        return self.soc_feasible

    @property
    def trailer_soc_feasible_bool(self) -> bool:
        return self.trailer_soc_feasible

    @property
    def mission_feasible_bool(self) -> bool | None:
        return self.mission_feasible


def edges_from_route_geometry(
    geom: LineString,
    *,
    max_edge_m: float = 2000.0,
) -> list[EdgeInput]:
    return [EdgeInput(geometry=ls, length_m=L) for ls, L in split_route_into_edges(geom, max_edge_m=max_edge_m)]


def route_geodesic_length_m(geom: LineString) -> float:
    coords = [(c[0], c[1]) for c in geom.coords]
    return geodesic_length_m(coords)


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
    terrain_quality: TerrainQuality | None = None,
    speed_mps: float | None = None,
    accel_mps2: float = 0.0,
    tags: dict[str, Any] | None = None,
) -> EnergyResult:
    """
    Evaluate traction + aux + refrigeration energy and tractor/trailer SOC along a route.

    Config A: TRU energy deducted from tractor usable battery.
    Config B: TRU energy from trailer pack only; tractor SOC unaffected by TRU.

    Feasibility is audited segment-by-segment. Later regeneration cannot erase an earlier
    SOC-floor violation. Invalid DEM/terrain yields mission_feasible=None (indeterminate).
    """
    if not edges:
        raise ValueError("edges must be non-empty")

    v = vehicle.cruise_mps if speed_mps is None else float(speed_mps)
    if v <= 0:
        raise ValueError("speed must be positive")

    validate_gcm(gcm_kg, vehicle)
    mass = mass_from_gcm(gcm_kg)

    if terrain is None:
        from shapely.ops import linemerge

        geoms = [e.geometry for e in edges]
        merged = linemerge(geoms)
        if merged.geom_type == "MultiLineString":
            coords: list[tuple[float, float]] = []
            for g in merged.geoms:
                coords.extend(list(g.coords))
            route_geom = LineString(coords)
        else:
            route_geom = merged
        terrain = flat_profile(route_geom)

    if terrain_quality is None:
        terrain_quality = assess_terrain_quality(terrain)

    # DEM scenarios with invalid/missing terrain cannot yield a boolean mission feasibility.
    terrain_indeterminate = terrain.source != "flat" and terrain_quality.status in {
        "invalid",
        "missing_data",
    }

    soc = vehicle.soc_initial
    trailer_soc: float | None = fridge_cfg.trailer_soc_initial if power_source == "B" else None
    min_soc = soc
    min_trailer = trailer_soc

    E_trac = 0.0
    E_aux = 0.0
    E_refrig_total = 0.0
    E_refrig_tractor = 0.0
    E_refrig_trailer = 0.0
    E_regen_ideal = 0.0
    E_regen_accepted = 0.0
    duration = 0.0
    distance = 0.0
    s_cursor = 0.0

    power_ok = True
    continuous_exceeded = False
    soc_ok = True
    trailer_ok = True
    first_violation_km: float | None = None
    first_violation_reason: str | None = None

    cum_e: list[float] = [0.0]
    cum_d: list[float] = [0.0]
    elevs: list[float] = [
        terrain.elevations_m[0] if terrain.elevations_m and math.isfinite(terrain.elevations_m[0]) else 0.0
    ]

    def _record_violation(reason: str, at_distance_m: float) -> None:
        nonlocal first_violation_km, first_violation_reason
        if first_violation_reason is None:
            first_violation_km = at_distance_m / 1000.0
            first_violation_reason = reason

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

        if terrain.source != "flat" and not math.isfinite(dz):
            _record_violation("missing_elevation", distance + L)
            # Cannot integrate a physical grade — mark indeterminate path and skip force model
            terrain_indeterminate = True
            duration += L / v
            distance += L
            s_cursor += L
            cum_e.append((E_trac + E_aux + E_refrig_tractor) / J_PER_KWH)
            cum_d.append(distance)
            elevs.append(float("nan"))
            continue

        seg = segment_traction_energy(
            length_m=L,
            dz_m=0.0 if terrain.source == "flat" else dz,
            mass_kg=mass,
            v_mps=v,
            wind_along_travel_mps=wind_along,
            rho_kg_m3=rho,
            vehicle=vehicle,
            soc=soc,
            accel_mps2=accel_mps2,
        )

        if not seg.power_feasible_peak:
            power_ok = False
            _record_violation("peak_motor_power_exceeded", distance + L)
        if not seg.power_feasible_continuous:
            continuous_exceeded = True

        # Energy accounting: propulsion uses required (uncapped) battery power;
        # regen uses accepted power after peak/SOC caps, with extra SOC energy headroom.
        e_trac = seg.E_batt_trac_j
        e_regen_ideal_seg = seg.E_regen_ideal_j
        e_regen_accepted_seg = seg.E_regen_accepted_j
        if e_trac < 0:
            headroom_j = (vehicle.soc_max - soc) * vehicle.usable_j
            if -e_trac > headroom_j:
                rejected = -e_trac - headroom_j
                e_trac = -headroom_j
                e_regen_accepted_seg = e_trac
                _ = rejected

        e_aux = vehicle.P_aux_w * seg.dt_s
        e_ref = refrigeration_energy_j(
            duration_s=seg.dt_s,
            T_amb_c=wp.T_mean_c,
            params=fridge_cfg,
            refrigeration_on=refrigeration_on,
        )

        e_tractor = e_trac + e_aux
        if power_source == "A":
            e_tractor += e_ref
            E_refrig_tractor += e_ref
        else:
            E_refrig_trailer += e_ref
            if trailer_soc is not None and refrigeration_on:
                trailer_before = trailer_soc
                trailer_raw = trailer_before - e_ref / fridge_cfg.trailer_usable_j
                min_trailer = trailer_raw if min_trailer is None else min(min_trailer, trailer_raw)
                if trailer_raw < fridge_cfg.trailer_soc_min - 1e-12:
                    trailer_ok = False
                    _record_violation("trailer_soc_floor", distance + L)
                # Display clip separate from feasibility
                trailer_soc = max(0.0, min(1.0, trailer_raw))

        soc_before = soc
        soc_raw = soc_before - e_tractor / vehicle.usable_j
        min_soc = min(min_soc, soc_raw)
        if soc_raw < vehicle.soc_min - 1e-12:
            soc_ok = False
            _record_violation("tractor_soc_floor", distance + L)
        # Numerical display clip — does not restore feasibility
        soc = max(0.0, min(vehicle.soc_max, soc_raw))

        E_trac += e_trac
        E_aux += e_aux
        E_refrig_total += e_ref
        E_regen_ideal += e_regen_ideal_seg
        E_regen_accepted += e_regen_accepted_seg
        duration += seg.dt_s
        distance += L
        s_cursor += L

        cum_e.append((E_trac + E_aux + E_refrig_tractor) / J_PER_KWH)
        cum_d.append(distance)
        elevs.append(elevation_at_distance(terrain, s_cursor))

    E_net_tractor = E_trac + E_aux + E_refrig_tractor
    E_regen_rejected = E_regen_ideal - E_regen_accepted  # both ≤0; rejected magnitude is ideal−accepted

    if terrain_indeterminate:
        mission: bool | None = None
    else:
        mission = bool(power_ok and soc_ok and trailer_ok)

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
        mission_feasible=mission,
        terrain_source=terrain.source,
        terrain_quality_status=terrain_quality.status,
        power_feasible=power_ok,
        soc_feasible=soc_ok,
        trailer_soc_feasible=trailer_ok,
        minimum_soc=min_soc,
        minimum_trailer_soc=min_trailer,
        first_violation_distance_km=first_violation_km,
        first_violation_reason=first_violation_reason,
        E_regen_ideal_j=E_regen_ideal,
        E_regen_accepted_j=E_regen_accepted,
        E_regen_rejected_j=E_regen_rejected,
        continuous_power_exceeded=continuous_exceeded,
        tags=dict(tags or {}),
        cumulative_energy_kwh=cum_e,
        cumulative_distance_m=cum_d,
        elevations_m=elevs,
    )
