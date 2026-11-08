"""Synthetic tests for topology conversion and facility access validation."""

from __future__ import annotations

import json
from pathlib import Path

import networkx as nx
import pandas as pd
import pytest
from shapely.geometry import LineString

from morocco_etruck.baseline_routing import path_to_geojson, shortest_path_length_m
from morocco_etruck.data_sources import ensure_geofabrik_pbf, relpath_posix, write_json
from morocco_etruck.road_network import (
    build_multidigraph_from_directed_edges,
    path_edge_geometries,
)
from morocco_etruck.service_areas import (
    AdmCandidate,
    DIR_AGADIR_CASA,
    DIR_CASA_AGADIR,
    find_directed_access,
    match_candidate_to_graph,
)


def _nodes_frame(ids_lon_lat):
    return pd.DataFrame([{"id": i, "lon": lon, "lat": lat} for i, lon, lat in ids_lon_lat])


def _edge_row(u, v, *, highway="motorway", oneway="yes", length=100.0, hgv=None, coords=None, **extra):
    if coords is None:
        coords = [(-8.0, 33.0), (-8.0, 32.9)]
    row = {
        "u": u,
        "v": v,
        "id": extra.pop("osm_way_id", 1),
        "highway": highway,
        "oneway": oneway,
        "length": length,
        "hgv": hgv,
        "access": extra.pop("access", None),
        "goods": None,
        "name": extra.pop("name", ""),
        "ref": extra.pop("ref", "A3"),
        "maxspeed": None,
        "geometry": LineString(coords),
    }
    row.update(extra)
    return row


def test_forward_reverse_and_bidirectional_pre_expanded():
    nodes = _nodes_frame([(1, -8.0, 33.0), (2, -8.0, 32.9), (3, -8.1, 33.0)])
    edges = pd.DataFrame(
        [
            _edge_row(1, 2, oneway="yes", osm_way_id=10, coords=[(-8.0, 33.0), (-8.0, 32.9)]),
            _edge_row(1, 2, oneway="-1", osm_way_id=11, coords=[(-8.0, 33.0), (-8.0, 32.9)]),
            _edge_row(1, 3, oneway="no", osm_way_id=12, coords=[(-8.0, 33.0), (-8.1, 33.0)]),
            _edge_row(3, 1, oneway="no", osm_way_id=12, coords=[(-8.1, 33.0), (-8.0, 33.0)]),
        ]
    )
    G, audit = build_multidigraph_from_directed_edges(nodes, edges, assume_pyrosm_pre_expanded=True)
    assert G.has_edge(1, 2)
    assert G.has_edge(2, 1)
    assert G.has_edge(1, 3) and G.has_edge(3, 1)
    assert G.number_of_edges() == 4
    assert audit["assume_pyrosm_pre_expanded"] is True


def test_parallel_directed_edges_preserved():
    nodes = _nodes_frame([(1, -8.0, 33.0), (2, -8.0, 32.9)])
    edges = pd.DataFrame(
        [
            _edge_row(1, 2, length=100, osm_way_id=1, coords=[(-8.0, 33.0), (-8.0, 32.9)]),
            _edge_row(1, 2, length=120, osm_way_id=2, coords=[(-8.01, 33.0), (-8.01, 32.9)]),
        ]
    )
    G, audit = build_multidigraph_from_directed_edges(nodes, edges)
    assert G.number_of_edges() == 2
    assert audit["parallel_uv_collisions_if_digraph"] == 1


def test_zero_length_self_path_not_entrance_and_exit():
    """Regression: motorway node matching itself must NOT count as access."""
    G = nx.MultiDiGraph()
    G.add_node(1, lon=-8.0, lat=33.0)
    G.add_node(2, lon=-8.0, lat=32.9)
    G.add_edge(1, 2, highway="motorway", length_m=500, bearing_deg=210, hgv_access="unknown", geometry_wkt="")
    access = find_directed_access(
        G, -8.0, 33.0, DIR_CASA_AGADIR, max_facility_node_dist_m=50, bearing_tol=90
    )
    assert access["directed_access_status"] != "entrance_and_exit"
    assert access.get("entrance_path_m") in (None, 0) or access["directed_access_status"] != "entrance_and_exit"
    assert access["directed_access_status"] in {"proximity_only", "unresolved"}


def test_poi_near_motorway_without_connecting_road_unresolved_or_proximity():
    G = nx.MultiDiGraph()
    G.add_node(1, lon=-8.0, lat=33.0)
    G.add_node(2, lon=-8.0, lat=32.8)
    G.add_node(99, lon=-7.5, lat=33.0)
    G.add_edge(1, 2, highway="motorway", length_m=1000, bearing_deg=180, hgv_access="unknown", geometry_wkt="")
    # Isolated service stub not connected to motorway
    G.add_node(98, lon=-7.5001, lat=33.0)
    G.add_edge(99, 98, highway="service", length_m=20, bearing_deg=90, hgv_access="unknown", geometry_wkt="")
    access = find_directed_access(
        G, -7.5, 33.0, DIR_CASA_AGADIR, max_facility_node_dist_m=200, bearing_tol=90
    )
    assert access["directed_access_status"] in {"unresolved", "proximity_only"}
    assert access["directed_access_status"] != "entrance_and_exit"


def test_opposite_carriageway_only():
    G = nx.MultiDiGraph()
    # Northbound carriageway (~10°) near facility with link; requested direction is southbound
    G.add_node(1, lon=-8.0, lat=32.9)
    G.add_node(2, lon=-8.0, lat=33.0)
    G.add_node(3, lon=-8.001, lat=32.95)
    G.add_edge(1, 2, highway="motorway", length_m=500, bearing_deg=10, hgv_access="unknown", geometry_wkt="")
    G.add_edge(1, 3, highway="motorway_link", length_m=50, bearing_deg=10, hgv_access="unknown", geometry_wkt="")
    G.add_edge(3, 1, highway="motorway_link", length_m=50, bearing_deg=190, hgv_access="unknown", geometry_wkt="")
    access = find_directed_access(
        G, -8.001, 32.95, DIR_CASA_AGADIR, max_facility_node_dist_m=500, bearing_tol=60
    )
    assert access["directed_access_status"] != "entrance_and_exit"
    assert access["directed_access_status"] in {
        "opposite_carriageway_only",
        "unresolved",
        "proximity_only",
    }


def test_valid_entrance_service_and_exit():
    G = nx.MultiDiGraph()
    G.add_node(10, lon=-8.0, lat=33.1)
    G.add_node(20, lon=-8.05, lat=32.9)
    G.add_node(30, lon=-8.02, lat=33.0)  # ramp
    G.add_node(40, lon=-8.021, lat=33.001)  # service / facility
    G.add_edge(10, 20, highway="motorway", length_m=2000, bearing_deg=210, hgv_access="unknown", geometry_wkt="")
    G.add_edge(10, 30, highway="motorway_link", length_m=200, bearing_deg=200, hgv_access="unknown", geometry_wkt="")
    G.add_edge(30, 20, highway="motorway_link", length_m=200, bearing_deg=220, hgv_access="unknown", geometry_wkt="")
    G.add_edge(30, 40, highway="service", length_m=40, bearing_deg=90, hgv_access="unknown", geometry_wkt="")
    G.add_edge(40, 30, highway="service", length_m=40, bearing_deg=270, hgv_access="unknown", geometry_wkt="")
    access = find_directed_access(
        G, -8.021, 33.001, DIR_CASA_AGADIR, max_facility_node_dist_m=500, bearing_tol=90
    )
    assert access["directed_access_status"] == "entrance_and_exit"
    assert access["entrance_path_m"] >= 1.0
    assert access["exit_path_m"] >= 1.0
    assert access["entrance_node_id"] != access["carriageway_attach_node_id"]


def test_entrance_only_not_fully_accessible():
    G = nx.MultiDiGraph()
    G.add_node(10, lon=-8.0, lat=33.1)
    G.add_node(20, lon=-8.05, lat=32.9)
    G.add_node(30, lon=-8.02, lat=33.0)
    G.add_edge(10, 20, highway="motorway", length_m=2000, bearing_deg=210, hgv_access="unknown", geometry_wkt="")
    G.add_edge(10, 30, highway="motorway_link", length_m=150, bearing_deg=210, hgv_access="unknown", geometry_wkt="")
    # No return edge from 30 to carriageway
    access = find_directed_access(
        G, -8.02, 33.0, DIR_CASA_AGADIR, max_facility_node_dist_m=400, bearing_tol=90
    )
    assert access["directed_access_status"] in {"entrance_only", "unresolved", "proximity_only"}
    assert access["directed_access_status"] != "entrance_and_exit"


def test_opposite_directions_not_silently_same_osm():
    G = nx.MultiDiGraph()
    # Two carriageways + two link/service attachments
    for n, lon, lat in [
        (1, -8.00, 33.10),
        (2, -8.05, 32.90),
        (3, -8.00, 32.90),
        (4, -8.05, 33.10),
        (11, -8.01, 33.00),
        (12, -8.04, 33.00),
    ]:
        G.add_node(n, lon=lon, lat=lat)
    G.add_edge(1, 2, highway="motorway", length_m=2000, bearing_deg=210, hgv_access="unknown", geometry_wkt="")
    G.add_edge(3, 4, highway="motorway", length_m=2000, bearing_deg=30, hgv_access="unknown", geometry_wkt="")
    G.add_edge(1, 11, highway="motorway_link", length_m=100, bearing_deg=210, hgv_access="unknown", geometry_wkt="")
    G.add_edge(11, 2, highway="motorway_link", length_m=100, bearing_deg=210, hgv_access="unknown", geometry_wkt="")
    G.add_edge(3, 12, highway="motorway_link", length_m=100, bearing_deg=30, hgv_access="unknown", geometry_wkt="")
    G.add_edge(12, 4, highway="motorway_link", length_m=100, bearing_deg=30, hgv_access="unknown", geometry_wkt="")
    G.add_edge(11, 11, highway="service", length_m=1, bearing_deg=0, hgv_access="unknown", geometry_wkt="")  # noop-ish
    # Service stubs at each facility
    G.add_node(21, lon=-8.011, lat=33.001)
    G.add_node(22, lon=-8.041, lat=33.001)
    G.add_edge(11, 21, highway="service", length_m=30, bearing_deg=90, hgv_access="unknown", geometry_wkt="")
    G.add_edge(21, 11, highway="service", length_m=30, bearing_deg=270, hgv_access="unknown", geometry_wkt="")
    G.add_edge(12, 22, highway="service", length_m=30, bearing_deg=90, hgv_access="unknown", geometry_wkt="")
    G.add_edge(22, 12, highway="service", length_m=30, bearing_deg=270, hgv_access="unknown", geometry_wkt="")

    pois = pd.DataFrame(
        [
            {
                "osm_id": 100,
                "lon": -8.011,
                "lat": 33.001,
                "name": "Aire de Service de Settat ouest",
                "brand": "",
                "highway": "services",
                "amenity": "",
                "name_norm": "aire de service de settat ouest",
            },
            {
                "osm_id": 200,
                "lon": -8.041,
                "lat": 33.001,
                "name": "Aire de Service de Settat est",
                "brand": "",
                "highway": "services",
                "amenity": "",
                "name_norm": "aire de service de settat est",
            },
        ]
    )
    c1 = AdmCandidate("ADS SETTAT de Casablanca --> Agadir", "A", DIR_CASA_AGADIR, "settat", "u")
    c2 = AdmCandidate("ADS SETTAT de Agadir --> Casablanca", "B", DIR_AGADIR_CASA, "settat", "u")
    r1 = match_candidate_to_graph(c1, pois, G, 500, 400, 90, reserved_osm_ids=set())
    r2 = match_candidate_to_graph(c2, pois, G, 500, 400, 90, reserved_osm_ids={r1["osm_id"]})
    assert r1["osm_id"] != r2["osm_id"]


def test_restricted_vs_unknown_hgv():
    G = nx.MultiDiGraph()
    G.add_node(10, lon=-8.0, lat=33.1)
    G.add_node(20, lon=-8.05, lat=32.9)
    G.add_node(30, lon=-8.02, lat=33.0)
    G.add_edge(10, 20, highway="motorway", length_m=2000, bearing_deg=210, hgv_access="yes", geometry_wkt="")
    G.add_edge(10, 30, highway="motorway_link", length_m=100, bearing_deg=210, hgv_access="no", geometry_wkt="")
    G.add_edge(30, 20, highway="motorway_link", length_m=100, bearing_deg=210, hgv_access="unknown", geometry_wkt="")
    access = find_directed_access(
        G, -8.02, 33.0, DIR_CASA_AGADIR, max_facility_node_dist_m=400, bearing_tol=90
    )
    if access["directed_access_status"] == "entrance_and_exit":
        assert access["hgv_access_status"] == "restricted"
    # unknown must remain distinct from permitted when tags are missing
    G2 = nx.MultiDiGraph()
    for n, lon, lat in [(10, -8.0, 33.1), (20, -8.05, 32.9), (30, -8.02, 33.0)]:
        G2.add_node(n, lon=lon, lat=lat)
    G2.add_edge(10, 20, highway="motorway", length_m=2000, bearing_deg=210, hgv_access="unknown", geometry_wkt="")
    G2.add_edge(10, 30, highway="motorway_link", length_m=100, bearing_deg=210, hgv_access="unknown", geometry_wkt="")
    G2.add_edge(30, 20, highway="motorway_link", length_m=100, bearing_deg=210, hgv_access="unknown", geometry_wkt="")
    a2 = find_directed_access(G2, -8.02, 33.0, DIR_CASA_AGADIR, max_facility_node_dist_m=400, bearing_tol=90)
    if a2["directed_access_status"] == "entrance_and_exit":
        assert a2["hgv_access_status"] == "unknown"
        assert a2["hgv_access_status"] != "permitted"


def test_match_proximity_alone_never_entrance_and_exit():
    G = nx.MultiDiGraph()
    G.add_node(1, lon=-8.0, lat=33.0)
    G.add_node(2, lon=-8.0, lat=32.9)
    G.add_edge(1, 2, highway="motorway", length_m=500, bearing_deg=180, hgv_access="unknown", geometry_wkt="")
    pois = pd.DataFrame(
        [
            {
                "osm_id": 99,
                "lon": -8.0,
                "lat": 33.0,
                "name": "Aire de Service de Settat est",
                "brand": "",
                "highway": "services",
                "amenity": "",
                "name_norm": "aire de service de settat est",
            }
        ]
    )
    cand = AdmCandidate(
        "ADS SETTAT de Casablanca --> Agadir",
        "X",
        DIR_CASA_AGADIR,
        "settat",
        "https://example.test",
    )
    row = match_candidate_to_graph(cand, pois, G, 1500, 800, 90)
    assert row["location_match_status"] == "matched_osm"
    assert row["match_status"] != "verified"
    assert row["directed_access_status"] != "entrance_and_exit"
    assert (row.get("entrance_path_m") in (None, 0)) or row["directed_access_status"] != "entrance_and_exit"


def test_curved_edge_geometry_route_reconstruction():
    G = nx.DiGraph()
    G.add_node("A", lon=0.0, lat=0.0)
    G.add_node("B", lon=1.0, lat=0.0)
    curve = LineString([(0.0, 0.0), (0.3, 0.2), (0.7, -0.1), (1.0, 0.0)])
    G.add_edge("A", "B", length_m=1000, geometry_wkt=curve.wkt)
    coords = path_edge_geometries(G, ["A", "B"])
    assert len(coords) == 4
    feat = path_to_geojson(G, ["A", "B"], {"route": "test"})
    assert feat["geometry"]["coordinates"][1] == [0.3, 0.2]


def test_offline_skip_download_raises_without_cache(tmp_path: Path):
    cfg = {
        "osm": {
            "download_url": "https://example.test/file.pbf",
            "md5_url": None,
            "filename": "missing.osm.pbf",
            "snapshot_label": "x",
        },
        "paths": {"raw_dir": "data/raw"},
    }
    (tmp_path / "data" / "raw").mkdir(parents=True)
    with pytest.raises(FileNotFoundError):
        ensure_geofabrik_pbf(cfg, tmp_path, skip_download=True)


def test_portable_manifest_relative_paths(tmp_path: Path):
    root = tmp_path
    abs_path = root / "configs" / "pilot_corridor.yaml"
    abs_path.parent.mkdir(parents=True)
    abs_path.write_text("x: 1\n", encoding="utf-8")
    rel = relpath_posix(abs_path, root)
    assert rel == "configs/pilot_corridor.yaml"
    out = root / "data" / "metadata" / "build_manifest.json"
    write_json(out, {"config": rel})
    data = json.loads(out.read_text(encoding="utf-8"))
    assert not data["config"].startswith("C:")
    assert "\\" not in data["config"]
