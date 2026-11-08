"""Longitudinal traction forces and segment energy (SI)."""

from __future__ import annotations

import math
from dataclasses import dataclass

from morocco_etruck.energy.vehicle import VehicleParams


@dataclass(frozen=True)
class SegmentForces:
    F_roll_n: float
    F_aero_n: float
    F_grade_n: float
    F_acc_n: float
    F_trac_n: float


@dataclass(frozen=True)
class SegmentTractionEnergy:
    forces: SegmentForces
    P_wheel_w: float
    P_batt_trac_w: float
    E_batt_trac_j: float
    dt_s: float
    regen_capped: bool


def grade_angle_rad(dz_m: float, length_m: float) -> float:
    """Grade angle from elevation change over path length."""
    if length_m <= 0:
        raise ValueError("length_m must be positive for grade_angle_rad")
    # Clamp sin argument for numerical safety on noisy DEM
    ratio = max(-1.0, min(1.0, dz_m / length_m))
    return math.asin(ratio)


def relative_air_speed_mps(v_mps: float, wind_along_travel_mps: float) -> float:
    """
    Air speed relative to vehicle along travel direction.

    wind_along_travel_mps > 0 means wind component in the travel direction (tailwind),
    so v_air = v - wind_along.
    """
    return v_mps - wind_along_travel_mps


def compute_forces(
    *,
    mass_kg: float,
    theta_rad: float,
    v_mps: float,
    v_air_mps: float,
    rho_kg_m3: float,
    vehicle: VehicleParams,
    accel_mps2: float = 0.0,
) -> SegmentForces:
    if mass_kg <= 0:
        raise ValueError("mass_kg must be positive")
    if vehicle.Crr <= 0:
        raise ValueError("Crr must be positive")
    g = vehicle.gravity_m_s2
    F_roll = vehicle.Crr * mass_kg * g * math.cos(theta_rad)
    F_aero = 0.5 * rho_kg_m3 * vehicle.CdA_m2 * (v_air_mps**2) * math.copysign(1.0, v_air_mps if v_air_mps != 0 else 1.0)
    if abs(v_air_mps) < 1e-12:
        F_aero = 0.0
    F_grade = mass_kg * g * math.sin(theta_rad)
    F_acc = mass_kg * accel_mps2
    F_trac = F_roll + F_aero + F_grade + F_acc
    return SegmentForces(
        F_roll_n=F_roll,
        F_aero_n=F_aero,
        F_grade_n=F_grade,
        F_acc_n=F_acc,
        F_trac_n=F_trac,
    )


def battery_traction_power_w(
    P_wheel_w: float,
    vehicle: VehicleParams,
    *,
    soc: float,
    usable_j: float | None = None,
) -> tuple[float, bool]:
    """
    Map wheel power to battery traction power with regen efficiency and caps.

    Returns (P_batt_trac_w, regen_capped).
    Negative battery power means regen charge into the pack.
    """
    usable = usable_j if usable_j is not None else vehicle.usable_j
    if P_wheel_w >= 0:
        # Discharge through propulsion chain; cap by peak power
        p = P_wheel_w / vehicle.eta_prop
        return min(p, vehicle.peak_power_w), False

    # Regenerative braking: P_wheel < 0
    p_regen_ideal = vehicle.eta_regen * P_wheel_w  # more negative = more charge
    # Cap magnitude by peak regen power
    max_charge_w = vehicle.peak_regen_power_w
    p_capped = max(p_regen_ideal, -max_charge_w)
    regen_capped = p_capped > p_regen_ideal + 1e-9  # less negative than ideal

    # SOC headroom: cannot charge above soc_max
    headroom_frac = max(0.0, vehicle.soc_max - soc)
    if headroom_frac <= 0:
        return 0.0, True
    # Instantaneous power still limited by peak; energy headroom applied at integration time
    # Keep power cap only here; energy clip in simulator.
    _ = usable  # usable capacity available for callers
    return p_capped, regen_capped


def segment_traction_energy(
    *,
    length_m: float,
    dz_m: float,
    mass_kg: float,
    v_mps: float,
    wind_along_travel_mps: float,
    rho_kg_m3: float,
    vehicle: VehicleParams,
    soc: float,
    accel_mps2: float = 0.0,
) -> SegmentTractionEnergy:
    if length_m < 0:
        raise ValueError("length_m must be non-negative")
    if length_m == 0:
        raise ValueError("zero-length segment is invalid for energy integration")
    if v_mps <= 0:
        raise ValueError("v_mps must be positive (zero speed is invalid under cruise policy)")

    theta = grade_angle_rad(dz_m, length_m)
    v_air = relative_air_speed_mps(v_mps, wind_along_travel_mps)
    forces = compute_forces(
        mass_kg=mass_kg,
        theta_rad=theta,
        v_mps=v_mps,
        v_air_mps=v_air,
        rho_kg_m3=rho_kg_m3,
        vehicle=vehicle,
        accel_mps2=accel_mps2,
    )
    P_wheel = forces.F_trac_n * v_mps
    P_batt, capped = battery_traction_power_w(P_wheel, vehicle, soc=soc)
    dt = length_m / v_mps
    return SegmentTractionEnergy(
        forces=forces,
        P_wheel_w=P_wheel,
        P_batt_trac_w=P_batt,
        E_batt_trac_j=P_batt * dt,
        dt_s=dt,
        regen_capped=capped,
    )
