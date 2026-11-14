"""Incremental energy transitions for routing (incoming SOC; no charger logic)."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal

from morocco_etruck.energy.refrigeration import RefrigerationParams, refrigeration_energy_j
from morocco_etruck.energy.simulator import EdgeInput, J_PER_KWH
from morocco_etruck.energy.terrain import TerrainSample, edge_dz_from_profile
from morocco_etruck.energy.traction import (
    max_power_feasible_speed_mps,
    segment_traction_energy,
)
from morocco_etruck.energy.vehicle import VehicleParams, mass_from_gcm, validate_gcm
from morocco_etruck.energy.weather import (
    CorridorWeatherDay,
    heading_deg,
    wind_along_travel_mps,
)

PowerSource = Literal["A", "B"]


@dataclass
class EnergyState:
    soc: float
    trailer_soc: float | None = None


@dataclass
class DriveTransitionResult:
    next_state: EnergyState
    dt_s: float
    length_m: float
    E_traction_j: float
    E_aux_j: float
    E_refrig_j: float
    E_net_tractor_j: float
    E_trailer_refrig_j: float
    power_feasible_peak: bool
    power_feasible_continuous: bool
    soc_feasible: bool
    trailer_soc_feasible: bool
    violation_reason: str | None
    speed_mps_used: float | None = None
    speed_adapted: bool = False


def apply_drive(
    state: EnergyState,
    edge: EdgeInput,
    *,
    vehicle: VehicleParams,
    weather: CorridorWeatherDay,
    fridge_cfg: RefrigerationParams,
    gcm_kg: float,
    refrigeration_on: bool,
    power_source: PowerSource,
    terrain: TerrainSample,
    s_cursor_m: float,
    speed_mps: float | None = None,
    accel_mps2: float = 0.0,
    adapt_speed_to_peak_power: bool = False,
    adapt_speed_to_continuous_power: bool = False,
    min_adapt_speed_mps: float = 1.0 / 3.6,
) -> DriveTransitionResult:
    """
    Apply one DRIVE edge starting from an existing energy state.

    Unlike evaluate_route(), does not reset SOC to vehicle.soc_initial.

    Optional speed adaptation (research / PASS correction): if the commanded
    cruise exceeds peak (and optionally continuous) motor ratings, reduce speed
    to the largest feasible value ≥ min_adapt_speed_mps. Does **not** retune
    manufacturer power ratings. Peak is never treated as unlimited-duration
    continuous capability when ``adapt_speed_to_continuous_power`` is True.
    """
    validate_gcm(gcm_kg, vehicle)
    mass = mass_from_gcm(gcm_kg)
    v_cmd = vehicle.cruise_mps if speed_mps is None else float(speed_mps)
    L = edge.length_m
    if L <= 0:
        raise ValueError("zero-length edge is invalid")
    if v_cmd <= 0:
        raise ValueError("speed must be positive")

    coords = list(edge.geometry.coords)
    lon1, lat1 = coords[0][0], coords[0][1]
    lon2, lat2 = coords[-1][0], coords[-1][1]
    mid_lat = 0.5 * (lat1 + lat2)
    mid_lon = 0.5 * (lon1 + lon2)
    wp = weather.nearest(mid_lat, mid_lon)
    rho = wp.air_density_kg_m3(vehicle.air_density_default_kg_m3)
    head = heading_deg(lon1, lat1, lon2, lat2)
    wind_along = wind_along_travel_mps(wp.wind_speed_mean_mps, wp.wind_dir_mean_deg, head)
    dz = edge_dz_from_profile(terrain, s_cursor_m, L)
    if terrain.source != "flat" and not math.isfinite(dz):
        return DriveTransitionResult(
            next_state=state,
            dt_s=L / v_cmd,
            length_m=L,
            E_traction_j=0.0,
            E_aux_j=0.0,
            E_refrig_j=0.0,
            E_net_tractor_j=0.0,
            E_trailer_refrig_j=0.0,
            power_feasible_peak=False,
            power_feasible_continuous=False,
            soc_feasible=False,
            trailer_soc_feasible=True,
            violation_reason="missing_elevation",
            speed_mps_used=v_cmd,
            speed_adapted=False,
        )

    v = v_cmd
    speed_adapted = False
    if adapt_speed_to_peak_power or adapt_speed_to_continuous_power:
        limit = float(vehicle.peak_power_w)
        if adapt_speed_to_continuous_power:
            limit = min(limit, float(vehicle.continuous_power_w))
        v_star, _p = max_power_feasible_speed_mps(
            length_m=L,
            dz_m=0.0 if terrain.source == "flat" else float(dz),
            mass_kg=mass,
            wind_along_travel_mps=wind_along,
            rho_kg_m3=rho,
            vehicle=vehicle,
            power_limit_w=limit,
            v_hi_mps=v_cmd,
            v_lo_mps=float(min_adapt_speed_mps),
            accel_mps2=accel_mps2,
        )
        if v_star is None:
            return DriveTransitionResult(
                next_state=state,
                dt_s=L / max(v_cmd, min_adapt_speed_mps),
                length_m=L,
                E_traction_j=0.0,
                E_aux_j=0.0,
                E_refrig_j=0.0,
                E_net_tractor_j=0.0,
                E_trailer_refrig_j=0.0,
                power_feasible_peak=False,
                power_feasible_continuous=False,
                soc_feasible=False,
                trailer_soc_feasible=True,
                violation_reason="peak_motor_power_exceeded",
                speed_mps_used=float(min_adapt_speed_mps),
                speed_adapted=True,
            )
        if v_star + 1e-9 < v_cmd:
            speed_adapted = True
        v = float(v_star)

    soc = state.soc
    trailer_soc = state.trailer_soc
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

    e_tractor = e_trac + e_aux
    e_trailer_ref = 0.0
    trailer_ok = True
    if power_source == "A":
        e_tractor += e_ref
    else:
        e_trailer_ref = e_ref
        if trailer_soc is not None and refrigeration_on:
            trailer_raw = trailer_soc - e_ref / fridge_cfg.trailer_usable_j
            if trailer_raw < fridge_cfg.trailer_soc_min - 1e-12:
                trailer_ok = False
            trailer_soc = max(0.0, min(1.0, trailer_raw))

    soc_raw = soc - e_tractor / vehicle.usable_j
    soc_ok = soc_raw >= vehicle.soc_min - 1e-12
    soc_next = max(0.0, min(vehicle.soc_max, soc_raw))

    reason = None
    if not seg.power_feasible_peak:
        reason = "peak_motor_power_exceeded"
    elif not soc_ok:
        reason = "tractor_soc_floor"
    elif not trailer_ok:
        reason = "trailer_soc_floor"

    return DriveTransitionResult(
        next_state=EnergyState(soc=soc_next, trailer_soc=trailer_soc),
        dt_s=seg.dt_s,
        length_m=L,
        E_traction_j=e_trac,
        E_aux_j=e_aux,
        E_refrig_j=e_ref,
        E_net_tractor_j=e_tractor,
        E_trailer_refrig_j=e_trailer_ref,
        power_feasible_peak=seg.power_feasible_peak,
        power_feasible_continuous=seg.power_feasible_continuous,
        soc_feasible=soc_ok,
        trailer_soc_feasible=trailer_ok,
        violation_reason=reason,
        speed_mps_used=v,
        speed_adapted=speed_adapted,
    )


def joules_to_kwh(j: float) -> float:
    return j / J_PER_KWH


def kwh_to_joules(kwh: float) -> float:
    return kwh * J_PER_KWH
