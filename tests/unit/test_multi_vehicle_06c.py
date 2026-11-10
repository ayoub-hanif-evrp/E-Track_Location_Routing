"""Task 06C — multi-vehicle loading, energy bounds, CCS, certification taxonomy."""

from __future__ import annotations

from pathlib import Path

import pytest

from morocco_etruck.energy.battery_bounds import derive_discrete_energy_bounds
from morocco_etruck.energy.vehicle import effective_charge_power_kw, load_vehicle
from morocco_etruck.optimization.label_setting import SolverStatus, solve_mrls
from morocco_etruck.optimization.placement_certification import (
    OptimalityStatus,
    portfolio_optimality_status,
)
from morocco_etruck.optimization.problem import ArcData, RoutingInstance
from morocco_etruck.optimization.reference_solver import solve_reference

ROOT = Path(__file__).resolve().parents[2]
EACTROS = ROOT / "configs/vehicles/eactros_600.yaml"
VOLVO475 = ROOT / "configs/vehicles/volvo_fh_electric_4x2_540kwh.yaml"
VOLVO460 = ROOT / "configs/vehicles/volvo_fh_electric_4x2_540kwh_usable460.yaml"


def test_load_eactros_and_volvo_distinct():
    e = load_vehicle(EACTROS)
    v475 = load_vehicle(VOLVO475)
    v460 = load_vehicle(VOLVO460)
    assert e.usable_kwh == 600.0
    assert v475.usable_kwh == 475.0
    assert v460.usable_kwh == 460.0
    assert v475.vehicle_id != e.vehicle_id
    assert v475.ccs_max_charge_kw == 350.0
    assert e.ccs_max_charge_kw is None


def test_derive_energy_bounds_never_exceeds_usable():
    v = load_vehicle(VOLVO475)
    emin, einit, ecap, notes = derive_discrete_energy_bounds(v, energy_quantum_kwh=10)
    assert ecap == 470  # floor_q(475)
    assert emin == 50  # ceil_q(47.5)
    assert einit == 470
    assert ecap <= v.usable_kwh
    assert "capacity_quantize" in notes


def test_derive_rejects_init_above_usable():
    v = load_vehicle(VOLVO460)
    with pytest.raises(ValueError, match="INVALID_INPUT"):
        derive_discrete_energy_bounds(v, energy_quantum_kwh=10, E_truck_init_kwh=500)


def test_effective_charge_power_caps_at_ccs():
    v = load_vehicle(VOLVO475)
    assert effective_charge_power_kw(v, 400.0) == 350.0
    assert effective_charge_power_kw(v, 200.0) == 200.0
    e = load_vehicle(EACTROS)
    assert effective_charge_power_kw(e, 400.0) == 400.0


def test_portfolio_cert_downgrade_on_limit_reached():
    svc = {"M1": "serviceable", "M2": "limit_reached"}
    assert (
        portfolio_optimality_status(
            core_status=OptimalityStatus.CERTIFIED_OPTIMAL, serviceability=svc
        )
        == OptimalityStatus.CONDITIONAL_RESTRICTED_PORTFOLIO
    )
    assert (
        portfolio_optimality_status(
            core_status=OptimalityStatus.CERTIFIED_OPTIMAL,
            serviceability={"M1": "serviceable"},
        )
        == OptimalityStatus.CERTIFIED_OPTIMAL
    )


def test_volvo_synthetic_mrls_matches_reference():
    """Small discrete instance with Volvo-scale energies; MRLS ≡ reference."""
    arcs = [
        ArcData("O", "D", 1, 40, 0, road_cost=100, arc_id="od"),
    ]
    inst = RoutingInstance(
        name="volvo_toy",
        nodes=["O", "D"],
        arcs=arcs,
        origin="O",
        destination="D",
        deadline_steps=20,
        E_truck_cap=470,
        E_truck_min=50,
        E_truck_init=470,
        E_trailer_cap=None,
        E_trailer_min=None,
        E_trailer_init=None,
        stations={},
        active_stations=set(),
        power_source="A",
        refrigeration_on=False,
        wait_max_steps=0,
        energy_quantum_kwh=10,
        objective_mode="enroute_incremental_cost",
    )
    r = solve_mrls(inst)
    ref = solve_reference(inst)
    assert r.status == SolverStatus.OPTIMAL
    assert ref.objective == r.objective == 100


def test_road_cost_cents_convention_documented():
    """100 cents/km ⇒ 10 km segment costs 1000 cents before currency conversion."""
    from morocco_etruck.optimization.arc_preprocessing import allocate_road_cost_units

    assert allocate_road_cost_units(10_000.0, road_cost_per_km=100.0) == 1000
    assert allocate_road_cost_units(10_000.0, road_cost_per_km=1.0) == 10
