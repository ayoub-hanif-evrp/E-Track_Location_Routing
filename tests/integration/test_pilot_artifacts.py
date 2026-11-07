from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from morocco_etruck.baseline_routing import run_baseline_routes
from morocco_etruck.data_sources import load_config
from morocco_etruck.road_network import load_graph_from_csv
from morocco_etruck.validation import (
    assert_directed_graph,
    assert_edges_reference_nodes,
    assert_positive_finite_lengths,
    assert_valid_coordinates,
    candidate_coord_honesty,
    network_summary,
)

ROOT = Path(__file__).resolve().parents[2]
PROCESSED = ROOT / "data" / "processed"


def _artifacts_ready() -> bool:
    required = [
        PROCESSED / "road_nodes.csv",
        PROCESSED / "road_edges.csv",
        PROCESSED / "candidate_sites.csv",
    ]
    return all(p.exists() and p.stat().st_size > 0 for p in required)


pytestmark = pytest.mark.integration


@pytest.mark.skipif(not _artifacts_ready(), reason="Pilot artifacts not built yet")
def test_pilot_network_integrity_and_schema():
    nodes = pd.read_csv(PROCESSED / "road_nodes.csv")
    edges = pd.read_csv(PROCESSED / "road_edges.csv")
    sites = pd.read_csv(PROCESSED / "candidate_sites.csv")
    assert_valid_coordinates(nodes)
    assert_positive_finite_lengths(edges)
    assert_edges_reference_nodes(nodes, edges)
    assert "edge_key" in edges.columns
    G = load_graph_from_csv(PROCESSED / "road_nodes.csv", PROCESSED / "road_edges.csv")
    assert_directed_graph(G)
    summary = network_summary(G)
    assert summary["n_nodes"] > 0 and summary["n_edges"] > 0
    candidate_coord_honesty(sites)
    for col in (
        "location_match_status",
        "directed_access_status",
        "hgv_access_status",
        "travel_direction",
        "evidence",
    ):
        assert col in sites.columns
    assert (sites["match_status"] != "verified").all()
    assert len(sites) <= 20


@pytest.mark.skipif(not _artifacts_ready(), reason="Pilot artifacts not built yet")
def test_baseline_both_directions_regression():
    config = load_config(ROOT / "configs" / "pilot_corridor.yaml")
    G = load_graph_from_csv(PROCESSED / "road_nodes.csv", PROCESSED / "road_edges.csv")
    baseline = run_baseline_routes(G, config)
    c2a = baseline["routes"]["casablanca_to_agadir"]
    a2c = baseline["routes"]["agadir_to_casablanca"]
    assert c2a["ok"] and a2c["ok"]
    assert 350 < c2a["distance_km"] < 500
    assert 350 < a2c["distance_km"] < 500
    # Edge-geometry routes should have more than 2 coordinates
    for feat in baseline["geojson"]["features"]:
        assert len(feat["geometry"]["coordinates"]) > 2
