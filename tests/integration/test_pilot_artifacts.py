from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

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
def test_pilot_network_integrity():
    nodes = pd.read_csv(PROCESSED / "road_nodes.csv")
    edges = pd.read_csv(PROCESSED / "road_edges.csv")
    sites = pd.read_csv(PROCESSED / "candidate_sites.csv")
    assert_valid_coordinates(nodes)
    assert_positive_finite_lengths(edges)
    assert_edges_reference_nodes(nodes, edges)
    G = load_graph_from_csv(PROCESSED / "road_nodes.csv", PROCESSED / "road_edges.csv")
    assert_directed_graph(G)
    summary = network_summary(G)
    assert summary["n_nodes"] > 0
    assert summary["n_edges"] > 0
    candidate_coord_honesty(sites)
    assert "travel_direction" in sites.columns
    # Corridor-only ADM set should be small
    assert len(sites) <= 20
