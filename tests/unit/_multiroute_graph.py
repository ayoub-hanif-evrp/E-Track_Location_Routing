"""Shared guard: skip multiroute physics tests when processed graph CSVs are absent."""

from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / "data" / "processed" / "multiroute"


def multiroute_graph_available() -> bool:
    nodes = BASE / "nodes.csv"
    edges = BASE / "edges.csv"
    road_n = BASE / "road_nodes.csv"
    road_e = BASE / "road_edges.csv"
    return (nodes.exists() and edges.exists()) or (road_n.exists() and road_e.exists())


def require_multiroute_graph() -> Path:
    if multiroute_graph_available():
        return BASE
    pytest.skip(
        "multiroute graph CSVs missing (nodes/edges or road_nodes/road_edges); "
        "restore from build_multiroute_pilot / local processed data for full nesting tests"
    )


skip_without_multiroute_graph = pytest.mark.skipif(
    not multiroute_graph_available(),
    reason="multiroute graph CSVs missing in checkout",
)
