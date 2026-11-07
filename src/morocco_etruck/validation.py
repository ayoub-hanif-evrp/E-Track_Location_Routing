"""Scientific validation helpers for the pilot network artifacts."""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import networkx as nx
import pandas as pd


def assert_positive_finite_lengths(edges: pd.DataFrame) -> None:
    lengths = edges["length_m"].astype(float)
    if not lengths.apply(lambda x: math.isfinite(x) and x > 0).all():
        bad = edges.loc[~lengths.apply(lambda x: math.isfinite(x) and x > 0)]
        raise AssertionError(f"Non-positive or non-finite edge lengths:\n{bad.head()}")


def assert_valid_coordinates(nodes: pd.DataFrame) -> None:
    lons = nodes["lon"].astype(float)
    lats = nodes["lat"].astype(float)
    if not ((lons >= -180) & (lons <= 180)).all():
        raise AssertionError("Invalid longitudes outside [-180, 180]")
    if not ((lats >= -90) & (lats <= 90)).all():
        raise AssertionError("Invalid latitudes outside [-90, 90]")
    if not lons.apply(math.isfinite).all() or not lats.apply(math.isfinite).all():
        raise AssertionError("Non-finite coordinates present")


def assert_edges_reference_nodes(nodes: pd.DataFrame, edges: pd.DataFrame) -> None:
    ids = set(nodes["node_id"].astype(str))
    missing_u = set(edges["u"].astype(str)) - ids
    missing_v = set(edges["v"].astype(str)) - ids
    if missing_u or missing_v:
        raise AssertionError(f"Edges reference missing nodes u={missing_u} v={missing_v}")


def assert_directed_graph(G: nx.Graph) -> None:
    if not G.is_directed():
        raise AssertionError("Graph must be directed")


def network_summary(G: nx.Graph) -> dict[str, Any]:
    und = G.to_undirected()
    return {
        "n_nodes": G.number_of_nodes(),
        "n_edges": G.number_of_edges(),
        "is_multigraph": bool(G.is_multigraph()),
        "weakly_connected_components": nx.number_weakly_connected_components(G),
        "strongly_connected_components": nx.number_strongly_connected_components(G),
        "undirected_connected_components": nx.number_connected_components(und),
    }


def candidate_coord_honesty(sites: pd.DataFrame) -> None:
    """Unmatched locations without OSM id must not invent coordinates."""
    for _, row in sites.iterrows():
        loc = str(row.get("location_match_status", row.get("match_status", "")))
        osm_id = row.get("osm_id")
        lat, lon = row.get("lat"), row.get("lon")
        has_coords = pd.notna(lat) and pd.notna(lon)
        missing_osm = (
            osm_id is None
            or (isinstance(osm_id, float) and math.isnan(osm_id))
            or str(osm_id).strip() == ""
        )
        if loc in {"unmatched", "unresolved"} and missing_osm and has_coords:
            raise AssertionError(
                f"Unmatched candidate without OSM id has fabricated coords: {row.get('official_name')}"
            )


def load_processed_tables(processed_dir: Path) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    nodes = pd.read_csv(processed_dir / "road_nodes.csv")
    edges = pd.read_csv(processed_dir / "road_edges.csv")
    sites = pd.read_csv(processed_dir / "candidate_sites.csv")
    return nodes, edges, sites
