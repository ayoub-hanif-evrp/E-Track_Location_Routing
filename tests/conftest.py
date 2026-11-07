from __future__ import annotations

import json
from pathlib import Path

import networkx as nx
import pandas as pd
import pytest

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def synthetic_digraph() -> nx.DiGraph:
    """Small directed graph with known shortest path A→C = 5 via B? Wait: A-B 2, B-C 3 → 5; A-C direct 10."""
    G = nx.DiGraph()
    coords = {
        "A": (-7.6, 33.5),
        "B": (-7.7, 33.0),
        "C": (-7.8, 32.5),
        "D": (-7.5, 33.2),
    }
    for n, (lon, lat) in coords.items():
        G.add_node(n, lon=lon, lat=lat, osm_node_id=n, crs_epsg=4326)
    # Directed one-way corridor A→B→C and a longer A→C
    G.add_edge("A", "B", length_m=2.0, highway="motorway", oneway="yes", hgv_access="unknown")
    G.add_edge("B", "C", length_m=3.0, highway="motorway", oneway="yes", hgv_access="unknown")
    G.add_edge("A", "C", length_m=10.0, highway="motorway", oneway="yes", hgv_access="unknown")
    # Opposite direction only C→B→A (no A←C shortcut the other way through A-C reverse)
    G.add_edge("C", "B", length_m=3.0, highway="motorway", oneway="yes", hgv_access="unknown")
    G.add_edge("B", "A", length_m=2.0, highway="motorway", oneway="yes", hgv_access="unknown")
    # D is a dead-end spur from A (one-way out) to test one-way restrictions
    G.add_edge("A", "D", length_m=1.0, highway="motorway_link", oneway="yes", hgv_access="unknown")
    return G


@pytest.fixture
def nodes_edges_frames(synthetic_digraph: nx.DiGraph) -> tuple[pd.DataFrame, pd.DataFrame]:
    nodes = pd.DataFrame(
        [
            {"node_id": n, "osm_node_id": n, "lon": d["lon"], "lat": d["lat"], "crs_epsg": 4326}
            for n, d in synthetic_digraph.nodes(data=True)
        ]
    )
    edges = pd.DataFrame(
        [
            {"u": u, "v": v, "length_m": d["length_m"], "highway": d["highway"], "oneway": d["oneway"]}
            for u, v, d in synthetic_digraph.edges(data=True)
        ]
    )
    return nodes, edges


@pytest.fixture
def candidate_sites_frame() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "official_name": "ADS SETTAT de Casablanca --> Agadir",
                "partner": "AFRIQUIA SMDC",
                "travel_direction": "Casablanca→Agadir",
                "lat": 32.9,
                "lon": -7.67,
                "osm_id": 123,
                "match_status": "probable",
                "requires_manual_review": True,
            },
            {
                "official_name": "ADS AMSKROUD de Casablanca --> Agadir",
                "partner": "VIVO ENERGY MAROC",
                "travel_direction": "Casablanca→Agadir",
                "lat": None,
                "lon": None,
                "osm_id": None,
                "match_status": "unresolved",
                "requires_manual_review": True,
            },
        ]
    )
