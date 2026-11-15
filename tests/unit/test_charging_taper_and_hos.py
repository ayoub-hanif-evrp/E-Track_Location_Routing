"""Unit tests for CCS taper envelope and HOS rest-pad proposal."""

from __future__ import annotations

from pathlib import Path

from morocco_etruck.energy.vehicle import (
    conservative_ccs_taper_factor,
    effective_charge_power_kw_with_taper,
    load_vehicle,
)
from morocco_etruck.optimization.operational_schedule import (
    propose_hos_rest_adjustment_with_usable,
    validate_schedule_from_replay_trace,
)

ROOT = Path(__file__).resolve().parents[2]


def test_taper_factors_monotone_and_bounds():
    assert conservative_ccs_taper_factor(0.5) == 1.0
    assert abs(conservative_ccs_taper_factor(0.8) - 0.70) < 1e-9
    assert abs(conservative_ccs_taper_factor(0.95) - 0.35) < 1e-9
    assert conservative_ccs_taper_factor(0.99) == 0.20
    assert conservative_ccs_taper_factor(0.7) > conservative_ccs_taper_factor(0.9)


def test_taper_caps_below_ccs_and_charger():
    v = load_vehicle(ROOT / "configs/vehicles/eactros_600.yaml")
    p = effective_charge_power_kw_with_taper(v, 350.0, soc=0.9, apply_taper=True)
    assert p < 350.0
    assert p <= float(v.ccs_max_charge_kw)


def test_hos_pad_not_needed_for_short_trip():
    actions = [
        {"action_type": "DRIVE", "dt_s": 120 * 60.0},
        {"action_type": "CHARGE", "dt_s": 20 * 60.0},
    ]
    hos = propose_hos_rest_adjustment_with_usable(
        actions, arrival_soc=0.4, usable_kwh=600.0, soc_min=0.1
    )
    assert hos.needed is False
    assert hos.ok_after_pad is True


def test_hos_pad_proposed_for_long_continuous_drive():
    actions = [
        {"action_type": "DRIVE", "dt_s": 300 * 60.0, "v": "dest"},
        {"action_type": "CHARGE", "dt_s": 10 * 60.0, "node": "stop_a"},
    ]
    base = validate_schedule_from_replay_trace(actions)
    assert base.ok is False
    hos = propose_hos_rest_adjustment_with_usable(
        actions,
        arrival_soc=0.5,
        usable_kwh=600.0,
        soc_min=0.1,
        P_aux_w=2500.0,
        refrigeration_on=False,
    )
    assert hos.needed is True
    assert hos.pad_duration_min >= 35.0 - 1e-9  # 45 - 10
    assert hos.total_stationary_energy_kwh > 0.0
    assert hos.arrival_soc_after_pad is not None
    assert hos.arrival_soc_after_pad < 0.5
