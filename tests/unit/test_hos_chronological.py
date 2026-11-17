"""Chronological HOS: extend stop before continuous-driving limit."""

from __future__ import annotations

from morocco_etruck.optimization.hos_adjustment import (
    inject_wait_into_solver_actions,
    propose_chronological_hos_plan,
)
from morocco_etruck.optimization.operational_schedule import (
    validate_schedule_from_replay_trace,
)


def test_extend_benguerir_like_30min_charge_before_limit():
    # 211.7 min drive, 30 min charge, then more driving that would exceed 270
    # without a qualifying break at the charge stop.
    actions = [
        {"action_type": "DRIVE", "dt_s": 211.7 * 60.0},
        {"action_type": "CHARGE", "dt_s": 30.0 * 60.0, "node": "benguerir_ac", "charge_kwh": 165},
        {"action_type": "DRIVE", "dt_s": 110.4 * 60.0},
    ]
    assert validate_schedule_from_replay_trace(actions).ok is False
    plan = propose_chronological_hos_plan(actions, refrigeration_on=False, P_aux_w=2500.0)
    assert plan.needed is True
    assert plan.pad_location == "benguerir_ac"
    assert abs(plan.pad_duration_min - 15.0) < 1e-6
    assert plan.ok is True
    assert plan.independent_rest is False
    assert validate_schedule_from_replay_trace(plan.adjusted_trace).ok is True


def test_no_stop_before_limit_cannot_invent_site():
    actions = [
        {"action_type": "DRIVE", "dt_s": 300.0 * 60.0},
        {"action_type": "CHARGE", "dt_s": 45.0 * 60.0, "node": "late_stop"},
    ]
    plan = propose_chronological_hos_plan(actions, refrigeration_on=False)
    assert plan.ok is False
    assert "no_verified_stop_before_continuous_limit" in plan.notes


def test_independent_rest_at_verified_pass_through_node():
    # Energy-optimal no-charge path still traverses benguerir_ac before 4.5 h.
    actions = [
        {"action_type": "DRIVE", "dt_s": 211.7 * 60.0, "u": "O", "v": "benguerir_ac"},
        {"action_type": "DRIVE", "dt_s": 110.4 * 60.0, "u": "benguerir_ac", "v": "D"},
    ]
    assert validate_schedule_from_replay_trace(actions).ok is False
    plan = propose_chronological_hos_plan(
        actions,
        refrigeration_on=False,
        P_aux_w=2500.0,
        verified_rest_nodes={"benguerir_ac", "settat_ac"},
    )
    assert plan.ok is True
    assert plan.independent_rest is True
    assert plan.pad_location == "benguerir_ac"
    assert abs(plan.pad_duration_min - 45.0) < 1e-6
    assert plan.aux_energy_kwh > 0.0
    assert validate_schedule_from_replay_trace(plan.adjusted_trace).ok is True


def test_inject_wait_after_drive_arrival_for_independent_rest():
    actions = [
        {"type": "DRIVE", "u": "O", "v": "benguerir_ac", "dt_steps": 42},
        {"type": "DRIVE", "u": "benguerir_ac", "v": "D", "dt_steps": 22},
    ]
    out = inject_wait_into_solver_actions(
        actions, station_node="benguerir_ac", pad_duration_min=45.0, time_step_min=5
    )
    assert any(a.get("type") == "WAIT" and a.get("node") == "benguerir_ac" for a in out)
    assert out[1]["type"] == "WAIT"
    assert out[1].get("hos_independent_rest") is True
