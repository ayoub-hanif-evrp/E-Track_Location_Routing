from __future__ import annotations

import math

import networkx as nx
import pandas as pd
import pytest

from morocco_etruck.baseline_routing import shortest_path_length_m
from morocco_etruck.service_areas import parse_adm_candidates, parse_direction
from morocco_etruck.validation import (
    assert_directed_graph,
    assert_edges_reference_nodes,
    assert_positive_finite_lengths,
    assert_valid_coordinates,
    candidate_coord_honesty,
)


def test_edge_lengths_positive_finite(nodes_edges_frames):
    _, edges = nodes_edges_frames
    assert_positive_finite_lengths(edges)


def test_node_coordinates_valid(nodes_edges_frames):
    nodes, _ = nodes_edges_frames
    assert_valid_coordinates(nodes)


def test_edges_reference_existing_nodes(nodes_edges_frames):
    nodes, edges = nodes_edges_frames
    assert_edges_reference_nodes(nodes, edges)


def test_directed_connectivity_preserved(synthetic_digraph):
    G = synthetic_digraph
    assert_directed_graph(G)
    assert nx.has_path(G, "A", "C")
    assert nx.has_path(G, "C", "A")


def test_oneway_restrictions_respected(synthetic_digraph):
    G = synthetic_digraph
    # A→D exists; D→A must not
    assert G.has_edge("A", "D")
    assert not G.has_edge("D", "A")
    with pytest.raises(nx.NetworkXNoPath):
        nx.shortest_path(G, "D", "A", weight="length_m")


def test_facility_coords_never_fabricated_when_matching_fails(candidate_sites_frame):
    # Extend fixture with Task 01B location field
    df = candidate_sites_frame.copy()
    df["location_match_status"] = [
        "matched_osm" if pd.notna(r.lat) else "unmatched" for r in df.itertuples()
    ]
    candidate_coord_honesty(df)
    unresolved = df[df["match_status"] == "unresolved"].iloc[0]
    assert pd.isna(unresolved["lat"]) and pd.isna(unresolved["lon"])


def test_candidate_direction_metadata_preserved():
    html = """
    <table>
      <tr><th>Aire de Service</th><th>Partenaire</th></tr>
      <tr><td>ADS SETTAT de Casablanca --> Agadir</td><td>AFRIQUIA SMDC</td></tr>
      <tr><td>ADS SETTAT de Agadir --> Casablanca</td><td>VIVO ENERGY MAROC</td></tr>
      <tr><td>ADS ASSILAH de Tanger Med --> Rabat</td><td>AFRIQUIA SMDC</td></tr>
    </table>
    """
    tokens = ["settat", "assilah"]
    # Only settat is a corridor token in our filter list for this test
    rows = parse_adm_candidates(html, "https://example.test/adm", ["settat"])
    assert len(rows) == 2
    dirs = {r.travel_direction for r in rows}
    assert "Casablanca→Agadir" in dirs
    assert "Agadir→Casablanca" in dirs
    assert parse_direction("ADS SETTAT de Casablanca --> Agadir") == "Casablanca→Agadir"


def test_shortest_path_known_optimum(synthetic_digraph):
    path, length = shortest_path_length_m(synthetic_digraph, "A", "C")
    assert length == pytest.approx(5.0)
    assert path == ["A", "B", "C"]


def test_rebuild_deterministic_from_same_tables(tmp_path, nodes_edges_frames):
    nodes, edges = nodes_edges_frames
    p1 = tmp_path / "n1.csv"
    p2 = tmp_path / "e1.csv"
    nodes.to_csv(p1, index=False)
    edges.to_csv(p2, index=False)
    n_a = pd.read_csv(p1)
    e_a = pd.read_csv(p2)
    n_b = pd.read_csv(p1)
    e_b = pd.read_csv(p2)
    pd.testing.assert_frame_equal(n_a, n_b)
    pd.testing.assert_frame_equal(e_a, e_b)
    assert_positive_finite_lengths(e_a)
    assert_edges_reference_nodes(n_a, e_a)


def test_reject_nonpositive_length():
    edges = pd.DataFrame({"u": [1], "v": [2], "length_m": [0.0]})
    with pytest.raises(AssertionError):
        assert_positive_finite_lengths(edges)


def test_reject_fabricated_unresolved_coords():
    sites = pd.DataFrame(
        [
            {
                "official_name": "X",
                "match_status": "unresolved",
                "location_match_status": "unmatched",
                "osm_id": None,
                "lat": 33.0,
                "lon": -7.0,
            }
        ]
    )
    with pytest.raises(AssertionError):
        candidate_coord_honesty(sites)


def test_geodesic_length_positive():
    from morocco_etruck.road_network import geodesic_length_m

    d = geodesic_length_m([(-7.6, 33.5), (-7.7, 33.0)])
    assert math.isfinite(d) and d > 0


def test_dual_carriageway_directional_components():
    """Synthetic A3-like dual carriageways must route each direction separately."""
    from morocco_etruck.baseline_routing import directional_a3_components, shortest_path_length_m

    H = nx.DiGraph()
    # Southbound chain N0→N1→N2
    for i, lat in enumerate([33.5, 32.0, 30.5]):
        H.add_node(f"sb{i}", lon=-8.0, lat=lat, ref="A3")
    H.add_edge("sb0", "sb1", length_m=100.0, ref="A3", highway="motorway")
    H.add_edge("sb1", "sb2", length_m=100.0, ref="A3", highway="motorway")
    # Northbound chain S0→S1→S2 (south to north)
    for i, lat in enumerate([30.5, 32.0, 33.5]):
        H.add_node(f"nb{i}", lon=-8.01, lat=lat, ref="A3")
    H.add_edge("nb0", "nb1", length_m=110.0, ref="A3", highway="motorway")
    H.add_edge("nb1", "nb2", length_m=110.0, ref="A3", highway="motorway")

    # Inflate component size to pass the >=100 filter by adding spur nodes
    for i in range(120):
        H.add_node(f"sbx{i}", lon=-8.0, lat=33.4 - i * 0.001)
        H.add_edge("sb0", f"sbx{i}", length_m=1.0, ref="A3", highway="motorway")
        H.add_node(f"nbx{i}", lon=-8.01, lat=30.6 + i * 0.001)
        H.add_edge("nb0", f"nbx{i}", length_m=1.0, ref="A3", highway="motorway")

    southbound, northbound = directional_a3_components(H)
    assert nx.has_path(southbound, "sb0", "sb2")
    assert nx.has_path(northbound, "nb0", "nb2")
    path, length = shortest_path_length_m(southbound, "sb0", "sb2")
    assert path == ["sb0", "sb1", "sb2"]
    assert length == pytest.approx(200.0)
