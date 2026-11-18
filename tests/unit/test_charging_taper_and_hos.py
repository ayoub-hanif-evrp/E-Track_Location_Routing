"""Unit tests for CCS taper envelope and HOS rest-pad proposal."""

from __future__ import annotations

from pathlib import Path

from morocco_etruck.energy.vehicle import (
    conservative_ccs_taper_factor,
    effective_charge_power_kw_with_taper,
    load_vehicle,
    tapered_battery_charge_minutes,
)
from morocco_etruck.optimization.operational_schedule import (
    propose_hos_rest_adjustment_with_usable,
    validate_schedule_from_replay_trace,
)
from morocco_etruck.optimization.problem import RoutingInstance, StationData
from morocco_etruck.optimization.resource_transitions import Label, apply_charge

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


def test_high_soc_charge_takes_longer_than_low_soc():
    kwargs = dict(
        nameplate_power_kw=350.0,
        eta=0.95,
        delta_e_batt_kwh=50.0,
        usable_kwh=600.0,
        apply_taper=True,
    )
    low = tapered_battery_charge_minutes(soc_start=0.20, **kwargs)
    high = tapered_battery_charge_minutes(soc_start=0.85, **kwargs)
    assert high > low * 1.2


def test_apply_charge_uses_taper_and_provenance_flag():
    inst = RoutingInstance(
        name="t",
        nodes=["S"],
        arcs=[],
        origin="S",
        destination="S",
        deadline_steps=500,
        E_truck_cap=600,
        E_truck_min=60,
        E_truck_init=510,
        E_trailer_cap=None,
        E_trailer_min=None,
        E_trailer_init=None,
        stations={
            "S": StationData(
                node="S",
                power_kw=350.0,
                eta=0.95,
                price_cents_per_grid_kwh=20,
            )
        },
        active_stations={"S"},
        power_source="A",
        refrigeration_on=False,
        time_step_min=5,
        energy_quantum_kwh=10,
    )
    lab = Label(
        node="S",
        t=0,
        E_truck=510,
        E_trailer=None,
        cost=0,
        pred_id=None,
        action={"type": "START"},
        label_id=0,
        can_charge=True,
    )
    # 510/600 = 0.85 SOC → taper active vs constant power from SOC 0
    res = apply_charge(inst, lab, delta_e=50, new_id=1)
    assert res.ok and res.label is not None
    assert res.label.action.get("charging_model") == "ccs_soc_taper_research_envelope"
    steps_taper = res.label.action["steps"]
    steps_const = inst.charge_duration_steps(
        inst.stations["S"], 50, soc_start=510 / 600, apply_taper=False
    )
    assert steps_taper > steps_const


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
