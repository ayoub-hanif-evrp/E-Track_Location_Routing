"""Task 06D — GCM immutability, fair-mass helpers, certification unresolved classes."""

from __future__ import annotations

from pathlib import Path

import pytest

from morocco_etruck.energy.vehicle import (
    cargo_payload_kg,
    gcm_from_payload,
    load_vehicle,
    validate_gcm,
)
from morocco_etruck.optimization.multiroute_adapter import load_multiroute_pilot_config
from morocco_etruck.optimization.multiroute_placement_evaluation import (
    resolve_mission_gcm_kg,
)
from morocco_etruck.optimization.multiroute_placement import MultiroutePlacementMission
from morocco_etruck.optimization.placement_certification import (
    OptimalityStatus,
    portfolio_optimality_status,
)

ROOT = Path(__file__).resolve().parents[2]
EACTROS = ROOT / "configs/vehicles/eactros_600.yaml"
VOLVO = ROOT / "configs/vehicles/volvo_fh_electric_4x2_540kwh.yaml"


def test_frozen_light_heavy_independent_of_cfg_mutation():
    cfg = load_multiroute_pilot_config(
        ROOT / "configs/optimization/multiroute_pilot.yaml", root=ROOT
    )
    light_m = MultiroutePlacementMission(
        id="L", od_id="casa_marrakech", weight=1.0, E_truck_init=200, gcm="light"
    )
    heavy_m = MultiroutePlacementMission(
        id="H", od_id="casa_marrakech", weight=1.0, E_truck_init=200, gcm="heavy"
    )
    assert resolve_mission_gcm_kg(light_m, cfg) == 25000.0
    assert resolve_mission_gcm_kg(heavy_m, cfg) == 40000.0
    # Mutating shared cfg must NOT change resolve_mission_gcm_kg light value
    cfg.gcm_kg = 40000.0
    assert resolve_mission_gcm_kg(light_m, cfg) == 25000.0
    assert resolve_mission_gcm_kg(heavy_m, cfg) == 40000.0


def test_fixed_payload_gcm_differs_by_curb():
    e = load_vehicle(EACTROS)
    v = load_vehicle(VOLVO)
    payload = 5300.0
    ge = gcm_from_payload(payload, e)
    gv = gcm_from_payload(payload, v)
    validate_gcm(ge, e)
    validate_gcm(gv, v)
    assert abs(ge - 25000.0) < 1e-6  # 11700+8000+5300
    assert abs(gv - 25300.0) < 1e-6  # 12000+8000+5300
    assert cargo_payload_kg(ge, e) == pytest.approx(payload)
    assert abs(gv - ge - (v.unladen_tractor_kg - e.unladen_tractor_kg)) < 1e-6


def test_portfolio_cert_downgrade_on_replay_invalid():
    svc = {"M1": "serviceable", "M2": "replay_invalid"}
    assert (
        portfolio_optimality_status(
            core_status=OptimalityStatus.CERTIFIED_OPTIMAL, serviceability=svc
        )
        == OptimalityStatus.CONDITIONAL_RESTRICTED_PORTFOLIO
    )
    svc2 = {"M1": "prep_failed"}
    assert (
        portfolio_optimality_status(
            core_status=OptimalityStatus.INCUMBENT_UNPROVED, serviceability=svc2
        )
        == OptimalityStatus.UNRESOLVED_SERVICEABILITY
    )


def test_build_physics_od_uses_explicit_gcm_without_mutating_cfg():
    """Integration-lite: builder accepts gcm_kg and leaves cfg.gcm_kg untouched."""
    pytest.importorskip("networkx")
    from morocco_etruck.optimization.multiroute_adapter import build_physics_od_instance
    import pandas as pd

    cfg = load_multiroute_pilot_config(
        ROOT / "configs/optimization/multiroute_pilot.yaml", root=ROOT
    )
    path_csv = cfg.path_alternatives_csv
    if not Path(path_csv).exists():
        pytest.skip("multiroute path alternatives missing")
    path_rows = pd.read_csv(path_csv).to_dict(orient="records")
    before = float(cfg.gcm_kg)
    inst, ctx, notes = build_physics_od_instance(
        cfg=cfg,
        root=ROOT,
        od_id="casa_marrakech",
        path_rows=path_rows,
        E_truck_init=None,  # derive from vehicle usable
        refrigeration_on=False,
        weather_id="cool",
        with_chargers=False,
        energy_quantum_kwh=10,
        terrain_mode="flat",
        objective_mode="enroute_incremental_cost",
        vehicle_yaml=EACTROS,
        gcm_kg=40000.0,
        attach_candidate_chargers=False,
    )
    assert float(cfg.gcm_kg) == before
    assert ctx.gcm_kg == 40000.0
    assert any(n.startswith("gcm_realized_kg=40000") for n in notes)
    # Second call with light must not inherit 40 t via cfg
    inst2, ctx2, notes2 = build_physics_od_instance(
        cfg=cfg,
        root=ROOT,
        od_id="casa_marrakech",
        path_rows=path_rows,
        E_truck_init=None,
        refrigeration_on=False,
        weather_id="cool",
        with_chargers=False,
        energy_quantum_kwh=10,
        terrain_mode="flat",
        objective_mode="enroute_incremental_cost",
        vehicle_yaml=VOLVO,
        gcm_kg=25000.0,
        attach_candidate_chargers=False,
    )
    assert float(cfg.gcm_kg) == before
    assert ctx2.gcm_kg == 25000.0
    assert inst2.E_truck_cap <= 475
