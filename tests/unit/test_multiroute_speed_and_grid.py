"""Task 06A — speed propagation, cache fingerprint, E_init validation, road-cost invariance."""

from __future__ import annotations

from pathlib import Path

import networkx as nx
import pytest
from shapely.geometry import LineString

from morocco_etruck.energy.refrigeration import load_refrigeration
from morocco_etruck.energy.terrain import flat_profile
from morocco_etruck.energy.vehicle import load_vehicle
from morocco_etruck.energy.weather import CorridorWeatherDay, WeatherPointDay
from morocco_etruck.optimization.arc_preprocessing import (
    allocate_path_road_costs,
    build_macro_arc,
    build_micro_edges_from_path,
    simulate_drive_from_soc,
)
from morocco_etruck.optimization.drive_table_cache import (
    DRIVE_TABLE_CACHE_VERSION,
    build_drive_table_fingerprint,
    speed_schedule_hash,
)
from morocco_etruck.optimization.multiroute_adapter import (
    build_physics_od_instance,
    load_multiroute_pilot_config,
)
from morocco_etruck.energy.simulator import EdgeInput

ROOT = Path(__file__).resolve().parents[2]


def _weather() -> CorridorWeatherDay:
    return CorridorWeatherDay(
        day_id="cool",
        date="2020-01-01",
        points={
            "m": WeatherPointDay(
                point_id="m",
                lat=32.0,
                lon=-8.0,
                date="2020-01-01",
                T_mean_c=20.0,
                wind_speed_mean_mps=0.0,
                wind_dir_mean_deg=0.0,
                pressure_mean_hpa=1013.0,
            )
        },
    )


def test_edge_speed_affects_duration_and_energy():
    vehicle = load_vehicle(ROOT / "configs/vehicles/eactros_600.yaml")
    fridge = load_refrigeration(ROOT / "configs/energy/refrigeration_approx.yaml")
    weather = _weather()
    L = 10000.0
    geom = LineString([(-8.0, 32.0), (-7.9, 32.0)])
    terrain = flat_profile(geom)
    common = dict(
        terrain=terrain,
        soc0=1.0,
        trailer_soc0=None,
        vehicle=vehicle,
        weather=weather,
        fridge_cfg=fridge,
        gcm_kg=25000.0,
        refrigeration_on=False,
        power_source="A",
    )
    fast = [EdgeInput(geometry=geom, length_m=L, speed_mps=80.0 / 3.6, speed_source="test")]
    slow = [EdgeInput(geometry=geom, length_m=L, speed_mps=40.0 / 3.6, speed_source="test")]
    ok_f, dt_f, soc_f, _, _, _ = simulate_drive_from_soc(fast, **common)
    ok_s, dt_s, soc_s, _, _, _ = simulate_drive_from_soc(slow, **common)
    assert ok_f and ok_s
    assert dt_s == pytest.approx(2.0 * dt_f, rel=0.02)
    # Slower: less aero drag → higher remaining SOC (lower energy use)
    assert soc_s > soc_f + 1e-5


def test_micro_edges_inherit_class_default_speed():
    G = nx.DiGraph()
    G.add_node(1, lon=-8.0, lat=32.0)
    G.add_node(2, lon=-7.9, lat=32.0)
    G.add_edge(
        1,
        2,
        length_m=5000.0,
        highway="primary",
        maxspeed_kmh="",
        geometry_wkt=LineString([(-8.0, 32.0), (-7.9, 32.0)]).wkt,
    )
    policy = {
        "use_osm_maxspeed": True,
        "class_defaults_kmh": {"primary": 60, "default": 50},
        "maxspeed_sane_min_kmh": 30,
        "maxspeed_sane_max_kmh": 120,
    }
    _geom, _L, micro, _pairs = build_micro_edges_from_path(
        G, [1, 2], speed_policy=policy, max_edge_m=10000.0
    )
    assert len(micro) >= 1
    assert all(m.speed_mps == pytest.approx(60.0 / 3.6) for m in micro)
    assert all(m.speed_source == "class_default" for m in micro)
    assert all(m.highway == "primary" for m in micro)


def test_speed_schedule_changes_fingerprint():
    assert DRIVE_TABLE_CACHE_VERSION.startswith("06")
    veh = ROOT / "configs/vehicles/eactros_600.yaml"
    fr = ROOT / "configs/energy/refrigeration_approx.yaml"
    base = dict(
        vehicle_yaml=veh,
        fridge_yaml=fr,
        weather_points={},
        terrain_mode="flat",
        terrain_source="flat",
        terrain_hash="t",
        macro_u="O",
        macro_v="D",
        edge_pairs=[(1, 2)],
        length_m=1000.0,
        gcm_kg=25000.0,
        refrigeration_on=False,
        power_source="A",
        energy_quantum_kwh=10,
        time_step_min=5,
        E_truck_min=60,
        E_truck_cap=600,
        E_trailer_min=None,
        E_trailer_cap=None,
        speed_policy={"class_defaults_kmh": {"motorway": 80}},
    )
    fp1 = build_drive_table_fingerprint(speed_schedule=[80 / 3.6], **base)
    fp2 = build_drive_table_fingerprint(speed_schedule=[50 / 3.6], **base)
    assert fp1 != fp2
    assert speed_schedule_hash([80 / 3.6]) != speed_schedule_hash([50 / 3.6])


def test_invalid_e_init_rejected(tmp_path: Path):
    cfg_path = ROOT / "configs/optimization/multiroute_pilot.yaml"
    if not (ROOT / "data/processed/multiroute/path_alternatives.csv").exists():
        pytest.skip("multiroute artifacts missing")
    cfg = load_multiroute_pilot_config(cfg_path, root=ROOT)
    import pandas as pd

    rows = pd.read_csv(cfg.path_alternatives_csv).to_dict(orient="records")
    with pytest.raises(ValueError, match="INVALID_INPUT"):
        build_physics_od_instance(
            cfg=cfg,
            root=ROOT,
            od_id="casa_marrakech",
            path_rows=rows,
            E_truck_init=10,
            E_truck_cap=600,
            E_truck_min=60,
            with_chargers=False,
            terrain_mode="flat",
            attach_candidate_chargers=False,
        )


def test_parent_total_units_split_sums_exactly():
    from morocco_etruck.optimization.arc_preprocessing import allocate_path_road_costs as alloc

    parent = alloc([10000.0], road_cost_per_km=1.0)[0]
    parts = alloc(
        [2500.0, 2500.0, 2500.0, 2500.0],
        road_cost_per_km=1.0,
        total_units=parent,
    )
    assert sum(parts) == parent


def test_path_road_cost_allocation_invariant_under_split():
    lengths = [10000.0]
    one = allocate_path_road_costs(lengths, road_cost_per_km=1.0)
    parts = allocate_path_road_costs([2500.0, 2500.0, 2500.0, 2500.0], road_cost_per_km=1.0)
    assert sum(one) == sum(parts)
    assert sum(one) == 10


def test_macro_split_road_cost_no_plus_one_inflation():
    G = nx.DiGraph()
    coords = {1: (-8.0, 32.0), 2: (-7.95, 32.0), 3: (-7.9, 32.0)}
    for nid, (lon, lat) in coords.items():
        G.add_node(nid, lon=lon, lat=lat)
    for u, v in ((1, 2), (2, 3)):
        G.add_edge(
            u,
            v,
            length_m=5000.0,
            highway="motorway",
            geometry_wkt=LineString([coords[u], coords[v]]).wkt,
        )
    policy = {"use_osm_maxspeed": False, "class_defaults_kmh": {"motorway": 80, "default": 80}}
    whole = build_macro_arc(
        G,
        u_name="O",
        v_name="D",
        path_nodes=[1, 2, 3],
        terrain_mode="flat",
        corridor_profile=None,
        macro_s0_m=0.0,
        road_cost_per_km=1.0,
        speed_policy=policy,
    )
    a = build_macro_arc(
        G,
        u_name="O",
        v_name="S",
        path_nodes=[1, 2],
        terrain_mode="flat",
        corridor_profile=None,
        macro_s0_m=0.0,
        road_cost_per_km=1.0,
        speed_policy=policy,
    )
    b = build_macro_arc(
        G,
        u_name="S",
        v_name="D",
        path_nodes=[2, 3],
        terrain_mode="flat",
        corridor_profile=None,
        macro_s0_m=5000.0,
        road_cost_per_km=1.0,
        speed_policy=policy,
    )
    # Largest-remainder path allocation matches unsplit total (no +1/macro inflation)
    allocated = allocate_path_road_costs([a.length_m, b.length_m], road_cost_per_km=1.0)
    assert sum(allocated) == allocate_path_road_costs([whole.length_m], road_cost_per_km=1.0)[0]
    # Independent per-macro rounding without max(1,…) stays near path total
    assert abs((a.road_cost + b.road_cost) - whole.road_cost) <= 1
