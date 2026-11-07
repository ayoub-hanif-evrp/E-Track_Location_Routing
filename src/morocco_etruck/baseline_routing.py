"""Minimal shortest-distance baseline on the directed pilot network."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import networkx as nx

from morocco_etruck.road_network import geodesic_length_m

logger = logging.getLogger(__name__)


class RoutingError(Exception):
    pass


def nearest_node(G: nx.DiGraph, lon: float, lat: float, max_radius_m: float) -> int:
    best_id = None
    best_d = float("inf")
    for nid, data in G.nodes(data=True):
        d = geodesic_length_m([(lon, lat), (float(data["lon"]), float(data["lat"]))])
        if d < best_d:
            best_d = d
            best_id = nid
    if best_id is None or best_d > max_radius_m:
        raise RoutingError(
            f"No graph node within {max_radius_m} m of ({lon}, {lat}); nearest={best_d}"
        )
    return int(best_id)


def a3_motorway_subgraph(G: nx.DiGraph) -> nx.DiGraph:
    """Directed subgraph of edges tagged ref=A3 and highway=motorway."""
    H = nx.DiGraph()
    for u, v, data in G.edges(data=True):
        ref = str(data.get("ref", "") or "")
        highway = str(data.get("highway", "") or "")
        if ref == "A3" and highway == "motorway":
            H.add_node(u, **G.nodes[u])
            H.add_node(v, **G.nodes[v])
            H.add_edge(u, v, **data)
    if H.number_of_edges() == 0:
        raise RoutingError("No A3 motorway edges found for baseline routing")
    return H


def directional_a3_components(H: nx.DiGraph) -> tuple[nx.DiGraph, nx.DiGraph]:
    """
    Split A3 into the two directed carriageway components.

    Moroccan A3 is dual carriageway: OSM encodes each direction as a separate
    weakly connected digraph component. Identify southbound (Casa→Agadir) as the
    component where a northern node can reach a southern node.
    """
    components = [H.subgraph(c).copy() for c in nx.weakly_connected_components(H)]
    components = [c for c in components if c.number_of_nodes() >= 100]
    if len(components) < 2:
        raise RoutingError(
            f"Expected two large A3 carriageway components; found {len(components)}"
        )

    def north_south(comp: nx.DiGraph) -> tuple[int, int]:
        nodes = list(comp.nodes())
        north = max(nodes, key=lambda n: float(comp.nodes[n]["lat"]))
        south = min(nodes, key=lambda n: float(comp.nodes[n]["lat"]))
        return north, south

    southbound = None
    northbound = None
    ranked = sorted(components, key=lambda c: c.number_of_nodes(), reverse=True)
    for comp in ranked[:4]:
        north, south = north_south(comp)
        if nx.has_path(comp, north, south):
            southbound = comp
        if nx.has_path(comp, south, north):
            northbound = comp

    if southbound is None or northbound is None:
        raise RoutingError(
            "Could not identify both A3 travel directions from weakly connected components"
        )
    return southbound, northbound


def nearest_node_in_graph(G: nx.DiGraph, lon: float, lat: float) -> tuple[int, float]:
    best_id = None
    best_d = float("inf")
    for nid, data in G.nodes(data=True):
        d = geodesic_length_m([(lon, lat), (float(data["lon"]), float(data["lat"]))])
        if d < best_d:
            best_d = d
            best_id = nid
    if best_id is None:
        raise RoutingError("Empty graph when selecting anchor")
    return int(best_id), float(best_d)


def shortest_path_length_m(G: nx.DiGraph, source: int, target: int) -> tuple[list[int], float]:
    path = nx.shortest_path(G, source=source, target=target, weight="length_m")
    length = 0.0
    for u, v in zip(path[:-1], path[1:]):
        length += float(G.edges[u, v]["length_m"])
    return path, length


def path_to_geojson(G: nx.DiGraph, path: list[int], properties: dict[str, Any]) -> dict[str, Any]:
    coords = []
    for nid in path:
        coords.append([float(G.nodes[nid]["lon"]), float(G.nodes[nid]["lat"])])
    return {
        "type": "Feature",
        "geometry": {"type": "LineString", "coordinates": coords},
        "properties": properties,
    }


def run_baseline_routes(G: nx.DiGraph, config: dict[str, Any]) -> dict[str, Any]:
    """
    Run Casablanca↔Agadir shortest-distance baselines on directed A3 carriageways.

    Dual-carriageway motorways are not strongly connected as a whole; each travel
    direction is routed on its own A3 component.
    """
    anchors = config["anchors"]
    casa_lon = float(anchors["casablanca"]["lon"])
    casa_lat = float(anchors["casablanca"]["lat"])
    aga_lon = float(anchors["agadir"]["lon"])
    aga_lat = float(anchors["agadir"]["lat"])

    H = a3_motorway_subgraph(G)
    southbound, northbound = directional_a3_components(H)

    casa_sb, d_casa_sb = nearest_node_in_graph(southbound, casa_lon, casa_lat)
    aga_sb, d_aga_sb = nearest_node_in_graph(southbound, aga_lon, aga_lat)
    aga_nb, d_aga_nb = nearest_node_in_graph(northbound, aga_lon, aga_lat)
    casa_nb, d_casa_nb = nearest_node_in_graph(northbound, casa_lon, casa_lat)

    results: dict[str, Any] = {
        "disclaimer": (
            "Shortest-distance paths on directed OSM A3 motorway carriageways for "
            "connectivity validation only. Dual carriageways are separate directed "
            "components. Not certified for heavy-goods vehicles; HGV access tags are "
            "often unknown."
        ),
        "method": "A3_ref_motorway_directional_components",
        "anchors": {
            "casablanca_to_agadir": {
                "source": casa_sb,
                "target": aga_sb,
                "source_distance_to_search_m": d_casa_sb,
                "target_distance_to_search_m": d_aga_sb,
            },
            "agadir_to_casablanca": {
                "source": aga_nb,
                "target": casa_nb,
                "source_distance_to_search_m": d_aga_nb,
                "target_distance_to_search_m": d_casa_nb,
            },
        },
        "routes": {},
    }

    features = []
    jobs = [
        (
            "casablanca_to_agadir",
            southbound,
            casa_sb,
            aga_sb,
            "Casablanca→Agadir",
        ),
        (
            "agadir_to_casablanca",
            northbound,
            aga_nb,
            casa_nb,
            "Agadir→Casablanca",
        ),
    ]

    for key, graph, src, tgt, label in jobs:
        try:
            path, length_m = shortest_path_length_m(graph, src, tgt)
            entry = {
                "label": label,
                "source": src,
                "target": tgt,
                "n_nodes": len(path),
                "n_edges": max(0, len(path) - 1),
                "distance_m": length_m,
                "distance_km": length_m / 1000.0,
                "ok": True,
                "error": None,
            }
            features.append(
                path_to_geojson(
                    graph,
                    path,
                    {
                        "route": key,
                        "label": label,
                        "distance_km": round(length_m / 1000.0, 3),
                    },
                )
            )
            logger.info("%s: %.2f km (%d nodes)", label, length_m / 1000.0, len(path))
        except (nx.NetworkXNoPath, nx.NodeNotFound, RoutingError) as exc:
            entry = {
                "label": label,
                "source": src,
                "target": tgt,
                "n_nodes": 0,
                "n_edges": 0,
                "distance_m": None,
                "distance_km": None,
                "ok": False,
                "error": str(exc),
            }
            logger.error("Route %s failed: %s", label, exc)
        results["routes"][key] = entry

    c2a = results["routes"]["casablanca_to_agadir"].get("distance_km")
    a2c = results["routes"]["agadir_to_casablanca"].get("distance_km")
    if c2a is not None and a2c is not None:
        results["direction_asymmetry_km"] = abs(c2a - a2c)
    else:
        results["direction_asymmetry_km"] = None

    results["geojson"] = {"type": "FeatureCollection", "features": features}
    return results


def write_baseline_results(results: dict[str, Any], results_dir: Path) -> None:
    results_dir.mkdir(parents=True, exist_ok=True)
    summary = {k: v for k, v in results.items() if k != "geojson"}
    (results_dir / "baseline_routes.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )
    (results_dir / "baseline_routes.geojson").write_text(
        json.dumps(results["geojson"]), encoding="utf-8"
    )
    logger.info("Wrote baseline routing results to %s", results_dir)
