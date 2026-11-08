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
    """Required wheel power at the commanded speed (uncapped)."""
    P_batt_required_w: float
    """Battery traction power required to deliver P_wheel through eta_prop (discharge >0)."""
    P_batt_trac_w: float
    """Battery power used for energy accounting (regen may be capped; propulsion NOT silently capped)."""
    E_batt_trac_j: float
    dt_s: float
    power_feasible_peak: bool
    """False if required wheel power exceeds manufacturer peak motor rating at this speed."""
    power_feasible_continuous: bool
    """False if required wheel power exceeds continuous motor rating (informational / soft)."""
    regen_capped_power: bool
    """True if ideal regen charge power exceeded peak regen capability."""
    regen_rejected_soc: bool
    """True if regen was zeroed because SOC has no headroom."""
    E_regen_ideal_j: float
    """Ideal regen energy into battery before caps (≤0 means charge magnitude as negative energy)."""
    E_regen_accepted_j: float
    """Regen energy actually accepted after power/SOC caps (≤0)."""


def grade_angle_rad(dz_m: float, length_m: float) -> float:
    """Grade angle from elevation change over path length."""
    if length_m <= 0:
        raise ValueError("length_m must be positive for grade_angle_rad")
    if not math.isfinite(dz_m):
        raise ValueError("dz_m must be finite for grade_angle_rad")
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
    F_aero = 0.5 * rho_kg_m3 * vehicle.CdA_m2 * (v_air_mps**2) * math.copysign(
        1.0, v_air_mps if v_air_mps != 0 else 1.0
    )
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


def map_wheel_to_battery_power(
    P_wheel_w: float,
    vehicle: VehicleParams,
    *,
    soc: float,
) -> tuple[float, float, bool, bool, bool, bool]:
    """
    Map required wheel power to battery power without silently capping propulsion energy.

    Manufacturer continuous/peak ratings (400/600 kW) are treated as **motor output**
    (wheel-side capability), not battery DC input. Propulsion feasibility is therefore
    checked on P_wheel against those limits. Battery discharge power is P_wheel/eta_prop
    and is **not** clipped for energy accounting.

    Returns:
        P_batt_required_w,
        P_batt_used_w (regen may be capped; propulsion equals required),
        power_feasible_peak,
        power_feasible_continuous,
        regen_capped_power,
        regen_rejected_soc,
    """
    if P_wheel_w >= 0:
        p_batt = P_wheel_w / vehicle.eta_prop
        peak_ok = P_wheel_w <= vehicle.peak_power_w + 1e-6
        cont_ok = P_wheel_w <= vehicle.continuous_power_w + 1e-6
        return p_batt, p_batt, peak_ok, cont_ok, False, False

    # Regenerative braking: P_wheel < 0 → battery charge (negative battery power)
    p_regen_ideal = vehicle.eta_regen * P_wheel_w
    max_charge_w = vehicle.peak_regen_power_w
    p_capped = max(p_regen_ideal, -max_charge_w)
    regen_capped = p_capped > p_regen_ideal + 1e-9

    headroom_frac = max(0.0, vehicle.soc_max - soc)
    if headroom_frac <= 0:
        return p_regen_ideal, 0.0, True, True, regen_capped, True

    return p_regen_ideal, p_capped, True, True, regen_capped, False


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
    (
        p_batt_req,
        p_batt_used,
        peak_ok,
        cont_ok,
        regen_cap,
        regen_soc,
    ) = map_wheel_to_battery_power(P_wheel, vehicle, soc=soc)

    dt = length_m / v_mps
    e_used = p_batt_used * dt
    e_ideal_regen = min(0.0, p_batt_req * dt)  # only meaningful for regen (≤0)
    e_accepted_regen = min(0.0, e_used)

    return SegmentTractionEnergy(
        forces=forces,
        P_wheel_w=P_wheel,
        P_batt_required_w=p_batt_req,
        P_batt_trac_w=p_batt_used,
        E_batt_trac_j=e_used,
        dt_s=dt,
        power_feasible_peak=peak_ok,
        power_feasible_continuous=cont_ok,
        regen_capped_power=regen_cap,
        regen_rejected_soc=regen_soc,
        E_regen_ideal_j=e_ideal_regen,
        E_regen_accepted_j=e_accepted_regen,
    )


# Backwards-compatible alias used by older tests (regen path only semantics changed).
def battery_traction_power_w(
    P_wheel_w: float,
    vehicle: VehicleParams,
    *,
    soc: float,
    usable_j: float | None = None,
) -> tuple[float, bool]:
    """Legacy helper: returns (P_batt_used_w, regen_or_propulsion_issue_flag)."""
    _ = usable_j
    _req, used, peak_ok, _cont, regen_cap, regen_soc = map_wheel_to_battery_power(
        P_wheel_w, vehicle, soc=soc
    )
    flagged = (not peak_ok) or regen_cap or regen_soc
    return used, flagged
