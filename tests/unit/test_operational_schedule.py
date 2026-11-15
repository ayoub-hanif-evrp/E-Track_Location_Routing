"""Unit tests for Moroccan driver-rest schedule validator."""

from __future__ import annotations

from morocco_etruck.optimization.operational_schedule import (
    REQUIRED_BREAK_MIN,
    MAX_CONTINUOUS_DRIVING_MIN,
    validate_operational_schedule,
)


def test_short_trip_no_break_required():
    # 2 h driving only
    actions = [{"type": "DRIVE", "dt_steps": 24}]  # 24*5 = 120 min
    res = validate_operational_schedule(actions, time_step_min=5)
    assert res.ok
    assert res.driving_min == 120.0
    assert res.extra_rest_beyond_charge_min == 0.0
    assert res.continuous_driving_max_min == 120.0


def test_long_drive_without_break_is_violation():
    # 5 h continuous driving, no stop
    actions = [{"type": "DRIVE", "dt_steps": 60}]  # 300 min
    res = validate_operational_schedule(actions, time_step_min=5)
    assert res.ok is False
    assert "continuous_driving" in (res.violation or "")
    assert res.driving_min == 300.0
    assert res.extra_rest_beyond_charge_min >= REQUIRED_BREAK_MIN - 1e-9


def test_charge_overlapping_qualifying_break_resets_clock():
    # 4.5 h drive + 45 min charge + 1 h drive
    actions = [
        {"type": "DRIVE", "dt_steps": 54},  # 270 min
        {"type": "CHARGE", "steps": 9, "delta_e_kwh": 50},  # 45 min
        {"type": "DRIVE", "dt_steps": 12},  # 60 min
    ]
    res = validate_operational_schedule(actions, time_step_min=5)
    assert res.ok
    assert res.charging_rest_overlap_min >= REQUIRED_BREAK_MIN - 1e-9
    assert res.extra_rest_beyond_charge_min == 0.0
    assert abs(res.continuous_driving_max_min - MAX_CONTINUOUS_DRIVING_MIN) < 1e-9


def test_short_charge_after_limit_needs_extra_rest():
    actions = [
        {"type": "DRIVE", "dt_steps": 54},  # 270
        {"type": "CHARGE", "steps": 2, "delta_e_kwh": 10},  # 10 min < 45
        {"type": "DRIVE", "dt_steps": 6},
    ]
    res = validate_operational_schedule(actions, time_step_min=5)
    assert res.ok is False
    assert "break_too_short" in (res.violation or "")
    assert res.extra_rest_beyond_charge_min >= 35.0 - 1e-9


def test_wait_plus_charge_can_form_qualifying_break():
    actions = [
        {"type": "DRIVE", "dt_steps": 54},
        {"type": "CHARGE", "steps": 4, "delta_e_kwh": 20},  # 20 min
        {"type": "WAIT", "steps": 5},  # 25 min → total 45
        {"type": "DRIVE", "dt_steps": 6},
    ]
    res = validate_operational_schedule(actions, time_step_min=5)
    assert res.ok
    assert res.charging_rest_overlap_min == 20.0
    assert res.extra_rest_beyond_charge_min == 0.0


def test_physical_dt_s_preferred_over_discrete_steps():
    # Discrete overstates first leg (54*5=270) vs physical 240 min.
    actions = [
        {"type": "DRIVE", "dt_steps": 54, "dt_s": 240 * 60.0},
        {"type": "CHARGE", "steps": 9, "dt_s": 45 * 60.0, "delta_e_kwh": 50},
        {"type": "DRIVE", "dt_steps": 12, "dt_s": 50 * 60.0},
    ]
    disc = validate_operational_schedule(actions, time_step_min=5)
    phys = validate_operational_schedule(
        actions, time_step_min=5, use_physical_times=True
    )
    assert abs(disc.driving_min - 330.0) < 1e-9  # 54*5 + 12*5
    assert abs(phys.driving_min - 290.0) < 1e-9  # 240 + 50
    assert phys.time_basis == "physical_dt_s"
    assert phys.physical_vs_discrete_drive_delta_min is not None
    assert abs(phys.physical_vs_discrete_drive_delta_min - (-40.0)) < 1e-9
    assert phys.ok
    assert disc.ok
