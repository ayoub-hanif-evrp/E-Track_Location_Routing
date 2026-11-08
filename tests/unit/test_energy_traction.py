"""Mathematical verification of traction / force / energy helpers."""

from __future__ import annotations

import math
from pathlib import Path

import pytest

from morocco_etruck.energy.traction import (
    battery_traction_power_w,
    compute_forces,
    grade_angle_rad,
    relative_air_speed_mps,
    segment_traction_energy,
)
from morocco_etruck.energy.vehicle import load_vehicle

ROOT = Path(__file__).resolve().parents[2]
VEHICLE = ROOT / "configs" / "vehicles" / "eactros_600.yaml"


@pytest.fixture(scope="module")
def vehicle():
    return load_vehicle(VEHICLE)


def test_crr_positive(vehicle):
    assert vehicle.Crr > 0


def test_grade_angle_flat():
    assert abs(grade_angle_rad(0.0, 100.0)) < 1e-12


def test_grade_uphill_positive():
    th = grade_angle_rad(10.0, 100.0)
    assert th > 0


def test_zero_length_raises(vehicle):
    with pytest.raises(ValueError, match="zero-length"):
        segment_traction_energy(
            length_m=0.0,
            dz_m=0.0,
            mass_kg=25000.0,
            v_mps=22.0,
            wind_along_travel_mps=0.0,
            rho_kg_m3=1.225,
            vehicle=vehicle,
            soc=1.0,
        )


def test_zero_speed_raises(vehicle):
    with pytest.raises(ValueError, match="positive"):
        segment_traction_energy(
            length_m=100.0,
            dz_m=0.0,
            mass_kg=25000.0,
            v_mps=0.0,
            wind_along_travel_mps=0.0,
            rho_kg_m3=1.225,
            vehicle=vehicle,
            soc=1.0,
        )


def test_flat_zero_wind_positive_roll(vehicle):
    forces = compute_forces(
        mass_kg=25000.0,
        theta_rad=0.0,
        v_mps=22.222,
        v_air_mps=22.222,
        rho_kg_m3=1.225,
        vehicle=vehicle,
        accel_mps2=0.0,
    )
    assert forces.F_roll_n > 0
    assert forces.F_grade_n == 0.0
    assert forces.F_trac_n > 0


def test_uphill_more_energy_than_downhill(vehicle):
    common = dict(
        length_m=1000.0,
        mass_kg=40000.0,
        v_mps=22.222,
        wind_along_travel_mps=0.0,
        rho_kg_m3=1.225,
        vehicle=vehicle,
        soc=1.0,
    )
    up = segment_traction_energy(dz_m=50.0, **common)
    down = segment_traction_energy(dz_m=-50.0, **common)
    assert up.E_batt_trac_j > down.E_batt_trac_j


def test_payload_monotonicity(vehicle):
    def e(mass):
        return segment_traction_energy(
            length_m=5000.0,
            dz_m=0.0,
            mass_kg=mass,
            v_mps=22.222,
            wind_along_travel_mps=0.0,
            rho_kg_m3=1.225,
            vehicle=vehicle,
            soc=1.0,
        ).E_batt_trac_j

    assert e(40000.0) > e(25000.0)


def test_headwind_vs_tailwind(vehicle):
    v = 22.222
    head = segment_traction_energy(
        length_m=2000.0,
        dz_m=0.0,
        mass_kg=30000.0,
        v_mps=v,
        wind_along_travel_mps=-5.0,  # headwind → higher v_air
        rho_kg_m3=1.225,
        vehicle=vehicle,
        soc=1.0,
    )
    tail = segment_traction_energy(
        length_m=2000.0,
        dz_m=0.0,
        mass_kg=30000.0,
        v_mps=v,
        wind_along_travel_mps=5.0,
        rho_kg_m3=1.225,
        vehicle=vehicle,
        soc=1.0,
    )
    assert head.E_batt_trac_j > tail.E_batt_trac_j
    assert relative_air_speed_mps(v, -5.0) > relative_air_speed_mps(v, 5.0)


def test_regen_cap(vehicle):
    # Large negative wheel power
    P_wheel = -1e9
    p, capped = battery_traction_power_w(P_wheel, vehicle, soc=0.5)
    assert capped
    assert p >= -vehicle.peak_regen_power_w
    # Full SOC: no regen charge
    p2, capped2 = battery_traction_power_w(-1e6, vehicle, soc=1.0)
    assert p2 == 0.0
    assert capped2


def test_propulsion_efficiency_increases_battery_draw(vehicle):
    forces = compute_forces(
        mass_kg=30000.0,
        theta_rad=0.0,
        v_mps=20.0,
        v_air_mps=20.0,
        rho_kg_m3=1.225,
        vehicle=vehicle,
    )
    P_w = forces.F_trac_n * 20.0
    p_batt, _ = battery_traction_power_w(P_w, vehicle, soc=0.8)
    assert p_batt == pytest.approx(P_w / vehicle.eta_prop)
    assert p_batt > P_w
