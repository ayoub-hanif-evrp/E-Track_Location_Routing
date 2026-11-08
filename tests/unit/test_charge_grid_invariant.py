"""Task 04A: charging-grid membership and action-level stationary drains."""

from __future__ import annotations

import math
from pathlib import Path

import pytest

from morocco_etruck.optimization.drive_table_cache import (
    DRIVE_TABLE_CACHE_VERSION,
    build_drive_table_fingerprint,
    fingerprint_payload,
    terrain_sample_hash,
)
from morocco_etruck.optimization.label_setting import SolverStatus, solve_mrls
from morocco_etruck.optimization.problem import ArcData, DriveTableEntry, RoutingInstance, StationData
from morocco_etruck.optimization.replay import replay_solution
from morocco_etruck.optimization.resource_transitions import (
    Label,
    apply_charge,
    apply_drive,
    stationary_drain_kwh,
)

ROOT = Path(__file__).resolve().parents[2]


def _inst_watt(
    *,
    q: int = 5,
    aux_w: float = 2500.0,
    tru_mean_w: float = 0.0,
    power_source: str = "A",
    refrigeration_on: bool = False,
    E_init: int = 100,
    E_cap: int = 200,
    E_min: int = 10,
    trailer: bool = False,
) -> RoutingInstance:
    # Build a 2-hop drive table that accepts any on-grid start >= E_min
    table: dict[tuple[int, int | None], DriveTableEntry] = {}
    El_vals: list[int | None] = [None]
    if trailer:
        El_vals = list(range(5, 35, q))
    for Et in range(E_min, E_cap + 1, q):
        for El in El_vals:
            # Consume 20 kWh truck (floor already on grid)
            e_end = Et - 20
            el_end = None if El is None else max(5, El - 5)
            feas = e_end >= E_min and (El is None or el_end >= 5)
            table[(Et, El)] = DriveTableEntry(
                feasible=feas,
                dt_steps=2,
                E_end_truck=e_end if feas else 0,
                E_end_trailer=el_end if feas else None,
                reason=None if feas else "floor",
            )
    stations = {"S": StationData("S", power_kw=60.0, eta=1.0, price_cents_per_grid_kwh=1)}
    return RoutingInstance(
        name="grid_toy",
        nodes=["O", "S", "D"],
        arcs=[
            ArcData("O", "S", 1, 0, 0, road_cost=0, drive_table={
                (E_init, 30 if trailer else None): DriveTableEntry(
                    True, 1, E_init, 30 if trailer else None
                )
            }),
            ArcData("S", "D", 1, 0, 0, road_cost=0, drive_table=table),
        ],
        origin="O",
        destination="D",
        deadline_steps=40,
        E_truck_cap=E_cap,
        E_truck_min=E_min,
        E_truck_init=E_init,
        E_trailer_cap=30 if trailer else None,
        E_trailer_min=5 if trailer else None,
        E_trailer_init=30 if trailer else None,
        stations=stations,
        active_stations={"S"},
        power_source=power_source,  # type: ignore[arg-type]
        refrigeration_on=refrigeration_on,
        aux_w=aux_w,
        tru_mean_w=tru_mean_w,
        aux_kwh_per_step=0,
        tru_kwh_per_step=0,
        wait_max_steps=0,
        time_step_min=5,
        energy_quantum_kwh=q,
    )


def test_action_level_aux_not_per_step_ceil():
    """2.5 kW × 25 min = 1.0417 kWh; old ceil-per-step drained 5 kWh."""
    inst = _inst_watt(aux_w=2500.0)
    drain_tr, _ = stationary_drain_kwh(inst, 5)
    assert abs(drain_tr - (2.5 * 25 / 60)) < 1e-9
    assert drain_tr < 1.05
    # Old model would have used 1 kWh/step × 5 = 5
    assert drain_tr < 5.0


@pytest.mark.parametrize("steps", [1, 2, 3, 4, 5])
def test_charge_keeps_energy_on_quantum(steps):
    # Force charge duration by choosing delta that needs exactly `steps` at 60 kW * 1.0
    # per_step = 60 * 5/60 = 5 kWh/step → delta = steps * 5
    inst = _inst_watt(E_init=100, E_cap=200, aux_w=2500.0)
    lab = Label("S", 0, 100, None, 0, None, {"type": "START"}, 0, can_charge=True)
    delta = steps * 5
    r = apply_charge(inst, lab, delta, 1)
    assert r.ok and r.label is not None
    assert r.label.t == steps
    assert r.label.E_truck % inst.energy_quantum_kwh == 0
    # Continuous net then floor: 100 + delta - 2.5*(5*steps)/60
    cont = 100 + delta - 2.5 * (5 * steps) / 60.0
    expected = int(math.floor(cont / 5) * 5)
    assert r.label.E_truck == expected


def test_small_charge_no_longer_lands_off_grid():
    """Previously ΔE=5, 1 step, drain=1 → E+4 off grid; now floors onto lattice."""
    inst = _inst_watt(E_init=75, aux_w=2500.0)
    lab = Label("S", 0, 75, None, 0, None, {"type": "START"}, 0, can_charge=True)
    r = apply_charge(inst, lab, 5, 1)
    assert r.ok and r.label is not None
    assert r.label.E_truck % 5 == 0
    # Old ending would be 75+5-1=79; new: floor(80 - 0.2083)=floor(79.7917)=75
    assert r.label.E_truck == 75


def test_charge_then_drive_table_lookup():
    inst = _inst_watt(E_init=100, E_cap=200, aux_w=2500.0)
    lab = Label("S", 0, 100, None, 0, None, {"type": "START"}, 0, can_charge=True)
    # Charge 50 kWh → 10 steps at 5 kWh/step; remains on quantum after snap
    r = apply_charge(inst, lab, 50, 1)
    assert r.ok and r.label is not None
    assert r.label.E_truck % 5 == 0
    arc = inst.arcs[1]  # S->D
    d = apply_drive(inst, r.label, arc, 2)
    assert d.ok, d.reason


def test_trailer_tru_config_b():
    inst = _inst_watt(
        aux_w=2500.0,
        tru_mean_w=1000.0,
        power_source="B",
        refrigeration_on=True,
        trailer=True,
        E_init=100,
    )
    lab = Label("S", 0, 100, 30, 0, None, {"type": "START"}, 0, can_charge=True)
    r = apply_charge(inst, lab, 20, 1)
    assert r.ok and r.label is not None
    assert r.label.E_truck % 5 == 0
    assert r.label.E_trailer is not None and r.label.E_trailer % 5 == 0
    # Trailer drained by TRU only
    assert r.label.E_trailer < 30


def test_near_headroom_charge_on_grid():
    inst = _inst_watt(E_init=190, E_cap=200, aux_w=2500.0)
    lab = Label("S", 0, 190, None, 0, None, {"type": "START"}, 0, can_charge=True)
    r = apply_charge(inst, lab, 10, 1)
    assert r.ok and r.label is not None
    assert r.label.E_truck % 5 == 0
    assert r.label.E_truck <= 200


def test_legacy_integer_drain_unchanged_for_synthetics():
    inst = RoutingInstance(
        name="legacy",
        nodes=["O", "S"],
        arcs=[],
        origin="O",
        destination="S",
        deadline_steps=20,
        E_truck_cap=100,
        E_truck_min=10,
        E_truck_init=50,
        E_trailer_cap=None,
        E_trailer_min=None,
        E_trailer_init=None,
        stations={"S": StationData("S", 60, 1.0, 1)},
        active_stations={"S"},
        power_source="A",
        refrigeration_on=False,
        aux_kwh_per_step=0,
        tru_kwh_per_step=0,
        aux_w=0.0,
        tru_mean_w=0.0,
        wait_max_steps=0,
        time_step_min=5,
        energy_quantum_kwh=1,
    )
    d_tr, d_tl = stationary_drain_kwh(inst, 3)
    assert (d_tr, d_tl) == (0.0, 0.0)


def test_fingerprint_changes_with_weather():
    base = dict(
        vehicle_yaml=ROOT / "configs/vehicles/eactros_600.yaml",
        fridge_yaml=ROOT / "configs/energy/refrigeration_approx.yaml",
        weather_points={"mid": {"T_mean_c": 15.0}},
        terrain_mode="flat",
        terrain_source="flat",
        terrain_hash="abc",
        macro_u="O",
        macro_v="D",
        edge_pairs=[(1, 2)],
        length_m=1000.0,
        gcm_kg=25000.0,
        refrigeration_on=False,
        power_source="A",
        energy_quantum_kwh=5,
        time_step_min=5,
        E_truck_min=60,
        E_truck_cap=600,
        E_trailer_min=None,
        E_trailer_cap=None,
    )
    fp1 = build_drive_table_fingerprint(**base)
    base2 = dict(base)
    base2["weather_points"] = {"mid": {"T_mean_c": 35.0}}
    fp2 = build_drive_table_fingerprint(**base2)
    assert fp1 != fp2
    assert isinstance(DRIVE_TABLE_CACHE_VERSION, str) and len(DRIVE_TABLE_CACHE_VERSION) > 0
    assert fingerprint_payload({"a": 1}) != fingerprint_payload({"a": 2})


def test_terrain_hash_detects_interior_elevation_change():
    """Head/tail unchanged but interior elevation mutates ⇒ fingerprint miss."""
    n = 20
    distances = [float(i) * 100.0 for i in range(n)]
    elevations = [10.0 + 0.1 * i for i in range(n)]
    mask = [True] * n
    h1 = terrain_sample_hash(distances, elevations, "dem", valid_mask=mask)
    elevations2 = list(elevations)
    elevations2[n // 2] += 25.0  # interior only
    # First/last five unchanged
    assert elevations2[:5] == elevations[:5]
    assert elevations2[-5:] == elevations[-5:]
    h2 = terrain_sample_hash(distances, elevations2, "dem", valid_mask=mask)
    assert h1 != h2
    # Cache fingerprint must also diverge when terrain_hash changes
    base = dict(
        vehicle_yaml=ROOT / "configs/vehicles/eactros_600.yaml",
        fridge_yaml=ROOT / "configs/energy/refrigeration_approx.yaml",
        weather_points={"mid": {"T_mean_c": 15.0}},
        terrain_mode="dem",
        terrain_source="dem",
        terrain_hash=h1,
        macro_u="O",
        macro_v="D",
        edge_pairs=[(1, 2)],
        length_m=1000.0,
        gcm_kg=25000.0,
        refrigeration_on=False,
        power_source="A",
        energy_quantum_kwh=5,
        time_step_min=5,
        E_truck_min=60,
        E_truck_cap=600,
        E_trailer_min=None,
        E_trailer_cap=None,
    )
    fp1 = build_drive_table_fingerprint(**base)
    base["terrain_hash"] = h2
    fp2 = build_drive_table_fingerprint(**base)
    assert fp1 != fp2


def test_mrls_synthetic_still_optimal():
    from morocco_etruck.optimization.instances import load_synthetic_instances

    insts = load_synthetic_instances(ROOT / "configs/optimization/synthetic_instances.yaml")
    a = next(i for i in insts if i.name == "A_no_charge")
    r = solve_mrls(a)
    assert r.status == SolverStatus.OPTIMAL
    assert r.objective == 10
    rep = replay_solution(a, r.actions, expected_cost=r.objective)
    assert rep.ok
