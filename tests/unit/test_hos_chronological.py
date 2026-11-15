"""Chronological HOS: extend stop before continuous-driving limit."""

from __future__ import annotations

from morocco_etruck.optimization.hos_adjustment import propose_chronological_hos_plan
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
    assert validate_schedule_from_replay_trace(plan.adjusted_trace).ok is True


def test_no_stop_before_limit_cannot_invent_site():
    actions = [
        {"action_type": "DRIVE", "dt_s": 300.0 * 60.0},
        {"action_type": "CHARGE", "dt_s": 45.0 * 60.0, "node": "late_stop"},
    ]
    plan = propose_chronological_hos_plan(actions, refrigeration_on=False)
    assert plan.ok is False
    assert "no_verified_stop_before_continuous_limit" in plan.notes
