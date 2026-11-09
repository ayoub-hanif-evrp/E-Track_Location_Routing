"""Task 05C — fixed-graph station activation monotonicity + DEM after split."""

from __future__ import annotations

from pathlib import Path

import networkx as nx
import pytest
from shapely.geometry import LineString

from morocco_etruck.energy.terrain import TerrainSample, save_profile
from morocco_etruck.energy.vehicle import load_vehicle
from morocco_etruck.energy.refrigeration import load_refrigeration
from morocco_etruck.energy.weather import CorridorWeatherDay, WeatherPointDay
from morocco_etruck.optimization.label_setting import SolverStatus, solve_mrls
from morocco_etruck.optimization.multiroute_adapter import clone_physics_instance_for_subset
from morocco_etruck.optimization.multiroute_charging import (
    GroundedCharger,
    split_arcs_at_charger_nodes,
)
from morocco_etruck.optimization.multiroute_physics import (
    build_macro_with_terrain,
    build_path_union_routing_instance,
)
from morocco_etruck.optimization.problem import StationData
from morocco_etruck.optimization.route_choice_graph import DecisionArc, make_arc_id

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
                wind_speed_mean_mps=1.0,
                wind_dir_mean_deg=0.0,
                pressure_mean_hpa=1013.0,
            )
        },
    )


def _line_graph() -> tuple[nx.DiGraph, DecisionArc]:
    G = nx.DiGraph()
    coords = {1: (-8.00, 32.00), 2: (-7.95, 32.00), 3: (-7.90, 32.00)}
    for nid, (lon, lat) in coords.items():
        G.add_node(nid, lon=lon, lat=lat)
    for u, v in ((1, 2), (2, 3)):
        G.add_edge(
            u,
            v,
            length_m=5000.0,
            highway="motorway",
            hgv_access="unknown",
            geometry_wkt=LineString([coords[u], coords[v]]).wkt,
        )
    pairs = [(1, 2), (2, 3)]
    arc = DecisionArc(
        u="O",
        v="D",
        path_nodes=[1, 2, 3],
        osm_edge_pairs=pairs,
        length_m=10000.0,
        scenario_speed_kmh=80.0,
        arc_id=make_arc_id(pairs),
    )
    return G, arc


def test_split_preserves_parent_arc_id_and_s0():
    G, arc = _line_graph()
    chargers = [
        GroundedCharger(
            key="S",
            node="S",
            osm_node_id=2,
            official_name="S",
            osm_id="1",
            lat=32.0,
            lon=-7.95,
            snap_distance_m=0.0,
            hgv_status="unknown",
            travel_direction="Casablanca→Agadir",
            access_class="topology_verified",
        )
    ]
    new_arcs, nodes, _ = split_arcs_at_charger_nodes(
        [arc], chargers=chargers, decision_nodes={"O": 1, "D": 3}, G=G
    )
    assert nodes["S"] == 2
    children = [a for a in new_arcs if a.parent_arc_id == arc.arc_id]
    assert len(children) == 2
    assert any(a.u == "O" and a.v == "S" and a.macro_s0_m == pytest.approx(0.0) for a in children)
    assert any(
        a.u == "S" and a.v == "D" and a.macro_s0_m == pytest.approx(5000.0) for a in children
    )


def test_dem_parent_slice_after_split(tmp_path: Path):
    G, arc = _line_graph()
    # Parent DEM profile covering full 10 km
    elev_dir = tmp_path / "elevation"
    elev_dir.mkdir()
    parent = TerrainSample(
        distances_m=[0.0, 5000.0, 10000.0],
        elevations_m=[100.0, 150.0, 120.0],
        source="synthetic_parent",
        meta={"step_m": 5000.0},
        valid_mask=[True, True, True],
    )
    save_profile(elev_dir / f"arc_{arc.arc_id}.json", parent)

    chargers = [
        GroundedCharger(
            key="S",
            node="S",
            osm_node_id=2,
            official_name="S",
            osm_id="1",
            lat=32.0,
            lon=-7.95,
            snap_distance_m=0.0,
            hgv_status="unknown",
            travel_direction="Casablanca→Agadir",
            access_class="topology_verified",
        )
    ]
    new_arcs, _, _ = split_arcs_at_charger_nodes(
        [arc], chargers=chargers, decision_nodes={"O": 1, "D": 3}, G=G
    )
    notes = []
    for child in new_arcs:
        _macro, note, dem_ok = build_macro_with_terrain(
            G, child, terrain_mode="dem", elevation_dir=elev_dir, road_cost_per_km=1.0
        )
        notes.append(note)
        assert dem_ok is True
        assert note in {"dem_parent_slice", "dem_per_arc"}
        assert not note.startswith("dem_unavailable")
    assert "dem_parent_slice" in notes


def test_dem_mode_marks_unavailable_without_silent_dem_label(tmp_path: Path):
    G, arc = _line_graph()
    elev_dir = tmp_path / "elevation"
    elev_dir.mkdir()
    # Split without writing parent DEM
    chargers = [
        GroundedCharger(
            key="S",
            node="S",
            osm_node_id=2,
            official_name="S",
            osm_id="1",
            lat=32.0,
            lon=-7.95,
            snap_distance_m=0.0,
            hgv_status="unknown",
            travel_direction="Casablanca→Agadir",
            access_class="topology_verified",
        )
    ]
    new_arcs, _, _ = split_arcs_at_charger_nodes(
        [arc], chargers=chargers, decision_nodes={"O": 1, "D": 3}, G=G
    )
    for child in new_arcs:
        _macro, note, dem_ok = build_macro_with_terrain(
            G, child, terrain_mode="dem", elevation_dir=elev_dir, road_cost_per_km=1.0
        )
        assert dem_ok is False
        assert note == "dem_unavailable"


def test_fixed_graph_activation_monotonicity_drive_only():
    """A ⊂ B ⇒ DRIVE-only feasible under A remains feasible under B (same arcs/tables)."""
    G, arc = _line_graph()
    chargers = [
        GroundedCharger(
            key="S",
            node="S",
            osm_node_id=2,
            official_name="S",
            osm_id="1",
            lat=32.0,
            lon=-7.95,
            snap_distance_m=0.0,
            hgv_status="unknown",
            travel_direction="Casablanca→Agadir",
            access_class="topology_verified",
        )
    ]
    arcs, nodes, _ = split_arcs_at_charger_nodes(
        [arc], chargers=chargers, decision_nodes={"O": 1, "D": 3}, G=G
    )
    vehicle = load_vehicle(ROOT / "configs/vehicles/eactros_600.yaml")
    fridge = load_refrigeration(ROOT / "configs/energy/refrigeration_approx.yaml")
    stations = {
        "S": StationData("S", 350.0, 0.95, 20, True, hypothetical_access=True),
    }
    template, ctx = build_path_union_routing_instance(
        G=G,
        dec={},
        path_rows=[],
        od_id="toy",
        vehicle=vehicle,
        fridge=fridge,
        weather=_weather(),
        vehicle_yaml=ROOT / "configs/vehicles/eactros_600.yaml",
        fridge_yaml=ROOT / "configs/energy/refrigeration_approx.yaml",
        gcm_kg=25000.0,
        refrigeration_on=False,
        power_source="A",
        terrain_mode="flat",
        elevation_dir=ROOT / "data/processed/multiroute/elevation",
        cache_dir=None,
        time_step_min=5,
        energy_quantum_kwh=10,
        deadline_steps=200,
        E_truck_init=600,
        E_truck_cap=600,
        E_truck_min=60,
        stations=stations,
        active_stations=set(),
        decision_arcs=arcs,
        origin="O",
        destination="D",
        decision_nodes=nodes,
    )
    empty = clone_physics_instance_for_subset(template, active_stations=set())
    full = clone_physics_instance_for_subset(template, active_stations={"S"})
    # Same physical arcs / drive tables
    assert len(empty.arcs) == len(full.arcs)
    assert [a.arc_id for a in empty.arcs] == [a.arc_id for a in full.arcs]
    for a0, a1 in zip(empty.arcs, full.arcs):
        assert a0.drive_table is a1.drive_table

    r0 = solve_mrls(empty, max_seconds=30.0)
    r1 = solve_mrls(full, max_seconds=30.0)
    assert r0.status == SolverStatus.OPTIMAL
    assert r1.status == SolverStatus.OPTIMAL
    # DRIVE-only journey under A remains feasible under B (objective not worse for optional charge)
    assert r1.objective is not None and r0.objective is not None
    assert r1.objective <= r0.objective
