"""Discrete DRIVE/CHARGE/WAIT and incremental physics adapter tests."""

from __future__ import annotations

from pathlib import Path

import pytest
from shapely.geometry import LineString

from morocco_etruck.energy.refrigeration import load_refrigeration
from morocco_etruck.energy.simulator import EdgeInput
from morocco_etruck.energy.terrain import flat_profile
from morocco_etruck.energy.transitions import EnergyState, apply_drive
from morocco_etruck.energy.vehicle import load_vehicle
from morocco_etruck.energy.weather import CorridorWeatherDay, WeatherPointDay
from morocco_etruck.optimization.instances import load_synthetic_instances
from morocco_etruck.optimization.problem import ArcData
from morocco_etruck.optimization.resource_transitions import (
    Label,
    apply_charge,
    apply_drive as disc_drive,
    apply_wait,
)

ROOT = Path(__file__).resolve().parents[2]
INST = load_synthetic_instances(ROOT / "configs/optimization/synthetic_instances.yaml")
BY = {i.name: i for i in INST}


def test_drive_rejects_power_infeasible():
    inst = BY["A_no_charge"]
    lab = Label("O", 0, 100, None, 0, None, {"type": "START"}, 0, True)
    arc = ArcData("O", "D", 2, 5, 0, 10, power_ok=False)
    r = disc_drive(inst, lab, arc, 1)
    assert not r.ok
    assert r.reason == "peak_motor_power_exceeded"


def test_charge_only_at_active_station():
    inst = BY["B_charge_required"]
    lab = Label("S", 2, 10, None, 5, None, {"type": "DRIVE"}, 0, True)
    ok = apply_charge(inst, lab, 40, 1)
    assert ok.ok
    bad = BY["C_station_unavailable"]
    lab2 = Label("S", 2, 10, None, 5, None, {"type": "DRIVE"}, 0, True)
    r = apply_charge(bad, lab2, 40, 1)
    assert not r.ok


def test_no_recharge_without_leaving():
    inst = BY["B_charge_required"]
    lab = Label("S", 2, 10, None, 5, None, {"type": "DRIVE"}, 0, True)
    r1 = apply_charge(inst, lab, 10, 1)
    assert r1.ok and r1.label is not None
    assert r1.label.can_charge is False
    r2 = apply_charge(inst, r1.label, 10, 2)
    assert not r2.ok


def test_wait_consumes_tru_config_b():
    inst = BY["F_refrigeration_trailer"]
    lab = Label("S", 0, 50, 3, 0, None, {"type": "START"}, 0, True)
    # Force wait_max temporarily via applying wait of 3 steps
    inst.wait_max_steps = 6
    r = apply_wait(inst, lab, 3, 1)
    assert not r.ok  # trailer 3 - 3*1 = 0 < min 1


def test_soc_floor_on_drive():
    inst = BY["G_soc_boundary"]
    lab = Label("O", 0, 45, None, 0, None, {"type": "START"}, 0, True)
    arc = inst.arcs[0]
    r = disc_drive(inst, lab, arc, 1)
    assert not r.ok
    assert r.reason == "tractor_soc_floor"


def test_physics_apply_drive_uses_incoming_soc():
    vehicle = load_vehicle(ROOT / "configs/vehicles/eactros_600.yaml")
    fridge = load_refrigeration(ROOT / "configs/energy/refrigeration_approx.yaml")
    weather = CorridorWeatherDay(
        day_id="t",
        date="2025-01-01",
        points={
            "p": WeatherPointDay("p", 32.0, -8.0, "2025-01-01", 20.0, 0.0, 0.0, 1013.25)
        },
    )
    geom = LineString([(-8.0, 32.0), (-7.9, 32.0)])
    edge = EdgeInput(geometry=geom, length_m=10_000.0)
    terrain = flat_profile(geom)
    low = apply_drive(
        EnergyState(soc=0.5, trailer_soc=None),
        edge,
        vehicle=vehicle,
        weather=weather,
        fridge_cfg=fridge,
        gcm_kg=25000.0,
        refrigeration_on=False,
        power_source="A",
        terrain=terrain,
        s_cursor_m=0.0,
    )
    high = apply_drive(
        EnergyState(soc=1.0, trailer_soc=None),
        edge,
        vehicle=vehicle,
        weather=weather,
        fridge_cfg=fridge,
        gcm_kg=25000.0,
        refrigeration_on=False,
        power_source="A",
        terrain=terrain,
        s_cursor_m=0.0,
    )
    assert low.next_state.soc < 0.5
    assert high.next_state.soc < 1.0
    assert high.next_state.soc > low.next_state.soc
