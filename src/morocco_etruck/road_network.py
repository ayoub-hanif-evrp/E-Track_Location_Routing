"""Build a directed motorway graph from an OSM extract."""

from __future__ import annotations

import json
import logging
import math
from pathlib import Path
from typing import Any

import networkx as nx
import pandas as pd
from pyproj import Geod
from shapely import wkt
from shapely.geometry import LineString, mapping, shape

logger = logging.getLogger(__name__)
GEOD = Geod(ellps="WGS84")

HIGHWAY_MOTORWAY = {"motorway", "motorway_link"}


class RoadNetworkError(Exception):
    """Raised when the road network cannot be constructed."""


def geodesic_length_m(coords: list[tuple[float, float]]) -> float:
    """Length in metres along WGS84 geodesic. coords are (lon, lat)."""
    if len(coords) < 2:
        return 0.0
    lons = [c[0] for c in coords]
    lats = [c[1] for c in coords]
    # Geometry length via pairwise inverse
    total = 0.0
    for i in range(len(coords) - 1):
        _, _, dist = GEOD.inv(lons[i], lats[i], lons[i + 1], lats[i + 1])
        total += abs(dist)
    return float(total)


def parse_maxspeed(raw: Any) -> float | None:
    if raw is None or (isinstance(raw, float) and math.isnan(raw)):
        return None
    text = str(raw).strip().lower()
    if not text or text in {"none", "signals", "variable"}:
        return None
    text = text.replace("km/h", "").replace("kmh", "").strip()
    if text.endswith("mph"):
        try:
            return float(text.replace("mph", "").strip()) * 1.60934
        except ValueError:
            return None
    try:
        return float(text.split()[0])
    except ValueError:
        return None


def classify_hgv_access(tags: dict[str, Any]) -> str:
    """Return yes / no / unknown without inventing legal access."""
    for key in ("hgv", "goods", "access"):
        val = tags.get(key)
        if val is None:
            continue
        v = str(val).lower()
        if v in {"no", "private", "agricultural", "forestry", "delivery"}:
            if key == "access" and v == "delivery":
                return "unknown"
            if key in {"hgv", "goods"} or v == "no":
                return "no"
        if key in {"hgv", "goods"} and v in {"yes", "designated", "permissive"}:
            return "yes"
    return "unknown"


def _edge_direction_mode(oneway: Any, highway: str) -> str:
    """Return 'forward', 'both', or 'reverse' based on OSM oneway conventions."""
    if oneway is None or (isinstance(oneway, float) and math.isnan(oneway)):
        # Motorways are typically oneway in OSM; if unset, treat as forward-only
        # but record uncertainty via attribute rather than inventing reverse edges.
        if highway in HIGHWAY_MOTORWAY:
            return "forward"
        return "both"
    v = str(oneway).strip().lower()
    if v in {"yes", "true", "1"}:
        return "forward"
    if v in {"-1", "reverse"}:
        return "reverse"
    if v in {"no", "false", "0"}:
        return "both"
    return "forward"


def bearing_deg(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    az, _, _ = GEOD.inv(lon1, lat1, lon2, lat2)
    return (az + 360.0) % 360.0


def load_network_tables_pyrosm(
    pbf_path: Path,
    bbox: list[float],
    highway_classes: list[str],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Load driving network edges/nodes clipped to bbox using pyrosm."""
    try:
        from pyrosm import OSM
    except ImportError as exc:
        raise RoadNetworkError(
            "pyrosm is required on this platform to parse OSM PBF without osmium bindings"
        ) from exc

    logger.info("Reading OSM via pyrosm from %s bbox=%s", pbf_path, bbox)
    osm = OSM(str(pbf_path), bounding_box=bbox)
    nodes, edges = osm.get_network(nodes=True, network_type="driving")
    if edges is None or edges.empty:
        raise RoadNetworkError("pyrosm returned no driving edges for bbox")
    # Filter highway classes
    edges = edges[edges["highway"].isin(highway_classes)].copy()
    if edges.empty:
        raise RoadNetworkError(
            f"No edges with highway in {highway_classes} inside bbox"
        )
    # Keep only nodes referenced by retained edges
    used = set(edges["u"].tolist()) | set(edges["v"].tolist())
    if nodes is not None and not nodes.empty:
        id_col = "id" if "id" in nodes.columns else "osmid"
        nodes = nodes[nodes[id_col].isin(used)].copy()
    else:
        # Reconstruct minimal nodes from edge endpoints if needed
        raise RoadNetworkError("pyrosm returned edges without nodes")
    return nodes, edges


def _coords_from_geometry(geom: Any) -> list[tuple[float, float]]:
    if geom is None:
        return []
    if isinstance(geom, str):
        geom = wkt.loads(geom)
    if geom.geom_type == "LineString":
        return list(geom.coords)
    if geom.geom_type == "MultiLineString":
        coords: list[tuple[float, float]] = []
        for part in geom.geoms:
            coords.extend(list(part.coords))
        return coords
    return []


def build_digraph_from_pyrosm(
    nodes: pd.DataFrame,
    edges: pd.DataFrame,
) -> nx.DiGraph:
    G = nx.DiGraph()
    id_col = "id" if "id" in nodes.columns else "osmid"
    for _, row in nodes.iterrows():
        nid = int(row[id_col])
        lon = float(row["lon"] if "lon" in row.index else row.geometry.x)
        lat = float(row["lat"] if "lat" in row.index else row.geometry.y)
        G.add_node(
            nid,
            osm_node_id=nid,
            lon=lon,
            lat=lat,
            x=lon,
            y=lat,
            crs_epsg=4326,
        )

    for idx, row in edges.iterrows():
        u = int(row["u"])
        v = int(row["v"])
        if u not in G or v not in G:
            continue
        highway = str(row.get("highway", ""))
        oneway = row.get("oneway")
        tags = {
            "highway": highway,
            "oneway": oneway,
            "maxspeed": row.get("maxspeed"),
            "access": row.get("access"),
            "hgv": row.get("hgv"),
            "goods": row.get("goods"),
            "name": row.get("name"),
            "ref": row.get("ref"),
        }
        # Drop NaNs from tags
        tags = {k: v for k, v in tags.items() if v is not None and not (isinstance(v, float) and math.isnan(v))}

        coords = _coords_from_geometry(row.geometry if hasattr(row, "geometry") else row.get("geometry"))
        length_m = geodesic_length_m(coords) if coords else float(row.get("length", 0.0) or 0.0)
        if length_m <= 0 and coords:
            length_m = geodesic_length_m(coords)
        # pyrosm length is often in metres already when present
        if length_m <= 0 and "length" in row.index and pd.notna(row["length"]):
            length_m = float(row["length"])

        osm_way_id = row.get("id", row.get("osmid", idx))
        try:
            osm_way_id = int(osm_way_id) if not isinstance(osm_way_id, list) else int(osm_way_id[0])
        except (TypeError, ValueError):
            osm_way_id = str(osm_way_id)

        hgv = classify_hgv_access(tags)
        maxspeed_raw = tags.get("maxspeed")
        maxspeed_kmh = parse_maxspeed(maxspeed_raw)
        mode = _edge_direction_mode(oneway, highway)

        def add_directed(a: int, b: int, reversed_flag: bool) -> None:
            edge_coords = list(reversed(coords)) if reversed_flag and coords else coords
            brg = None
            if len(edge_coords) >= 2:
                brg = bearing_deg(edge_coords[0][0], edge_coords[0][1], edge_coords[-1][0], edge_coords[-1][1])
            G.add_edge(
                a,
                b,
                osm_way_id=osm_way_id,
                length_m=float(length_m),
                highway=highway,
                oneway=str(oneway) if oneway is not None else "",
                maxspeed_raw=str(maxspeed_raw) if maxspeed_raw is not None else "",
                maxspeed_kmh=maxspeed_kmh if maxspeed_kmh is not None else "",
                access=str(tags.get("access", "")),
                hgv_tag=str(tags.get("hgv", "")),
                goods_tag=str(tags.get("goods", "")),
                hgv_access=hgv,
                name=str(tags.get("name", "")),
                ref=str(tags.get("ref", "")),
                geometry_wkt=LineString(edge_coords).wkt if len(edge_coords) >= 2 else "",
                bearing_deg=brg if brg is not None else "",
                crs_epsg=4326,
            )

        if mode == "forward":
            add_directed(u, v, False)
        elif mode == "reverse":
            add_directed(v, u, True)
        else:
            add_directed(u, v, False)
            add_directed(v, u, True)

    return G


def resolve_extract_input(raw_dir: Path, extract_info: dict[str, Any], national_pbf: Path) -> tuple[Path, list[float]]:
    """Return the PBF path to read and bbox for Python-side filtering."""
    if extract_info.get("tool") == "osmium-extract":
        out = Path(extract_info["output"])
        return out, extract_info["bbox"]
    if extract_info.get("tool") == "pyrosm-python-bbox-filter":
        marker = Path(extract_info["marker"])
        data = json.loads(marker.read_text(encoding="utf-8"))
        return Path(data["source_pbf"]), list(data["bbox"])
    # Default
    return national_pbf, extract_info.get("bbox", [])


def build_pilot_graph(
    national_pbf: Path,
    extract_info: dict[str, Any],
    config: dict[str, Any],
) -> nx.DiGraph:
    raw_dir = Path(national_pbf).parent
    pbf_path, bbox = resolve_extract_input(raw_dir, extract_info, national_pbf)
    highway_classes = list(config["osm"]["highway_classes"])
    nodes, edges = load_network_tables_pyrosm(pbf_path, bbox, highway_classes)
    G = build_digraph_from_pyrosm(nodes, edges)
    if G.number_of_edges() == 0:
        raise RoadNetworkError("Directed graph has zero edges after filtering")
    logger.info(
        "Built digraph: %d nodes, %d edges",
        G.number_of_nodes(),
        G.number_of_edges(),
    )
    return G


def export_graph_artifacts(G: nx.DiGraph, processed_dir: Path) -> dict[str, Path]:
    processed_dir.mkdir(parents=True, exist_ok=True)
    nodes_path = processed_dir / "road_nodes.csv"
    edges_path = processed_dir / "road_edges.csv"
    graphml_path = processed_dir / "pilot_network.graphml"
    geojson_path = processed_dir / "pilot_network.geojson"

    node_rows = []
    for nid, data in G.nodes(data=True):
        node_rows.append(
            {
                "node_id": nid,
                "osm_node_id": data.get("osm_node_id", nid),
                "lon": data.get("lon"),
                "lat": data.get("lat"),
                "crs_epsg": data.get("crs_epsg", 4326),
            }
        )
    pd.DataFrame(node_rows).to_csv(nodes_path, index=False)

    edge_rows = []
    features = []
    for u, v, data in G.edges(data=True):
        edge_rows.append(
            {
                "u": u,
                "v": v,
                "osm_way_id": data.get("osm_way_id"),
                "length_m": data.get("length_m"),
                "highway": data.get("highway"),
                "oneway": data.get("oneway"),
                "maxspeed_raw": data.get("maxspeed_raw"),
                "maxspeed_kmh": data.get("maxspeed_kmh"),
                "access": data.get("access"),
                "hgv_tag": data.get("hgv_tag"),
                "goods_tag": data.get("goods_tag"),
                "hgv_access": data.get("hgv_access"),
                "name": data.get("name"),
                "ref": data.get("ref"),
                "bearing_deg": data.get("bearing_deg"),
                "geometry_wkt": data.get("geometry_wkt"),
                "crs_epsg": data.get("crs_epsg", 4326),
            }
        )
        wkt_s = data.get("geometry_wkt") or ""
        if wkt_s:
            geom = wkt.loads(wkt_s)
            props = {k: ("" if v is None else v) for k, v in edge_rows[-1].items() if k != "geometry_wkt"}
            features.append({"type": "Feature", "geometry": mapping(geom), "properties": props})

    pd.DataFrame(edge_rows).to_csv(edges_path, index=False)

    # GraphML cannot store complex types cleanly; stringify Nones
    H = nx.DiGraph()
    for nid, data in G.nodes(data=True):
        H.add_node(nid, **{k: ("" if v is None else v) for k, v in data.items()})
    for u, v, data in G.edges(data=True):
        H.add_edge(u, v, **{k: ("" if v is None else v) for k, v in data.items()})
    nx.write_graphml(H, graphml_path)

    fc = {
        "type": "FeatureCollection",
        "crs": {"type": "name", "properties": {"name": "EPSG:4326"}},
        "features": features,
    }
    geojson_path.write_text(json.dumps(fc), encoding="utf-8")

    logger.info("Exported graph artifacts to %s", processed_dir)
    return {
        "road_nodes": nodes_path,
        "road_edges": edges_path,
        "graphml": graphml_path,
        "geojson": geojson_path,
    }


def load_graph_from_csv(nodes_csv: Path, edges_csv: Path) -> nx.DiGraph:
    nodes = pd.read_csv(nodes_csv)
    edges = pd.read_csv(edges_csv)
    G = nx.DiGraph()
    for _, row in nodes.iterrows():
        G.add_node(
            int(row["node_id"]),
            osm_node_id=int(row["osm_node_id"]),
            lon=float(row["lon"]),
            lat=float(row["lat"]),
            crs_epsg=int(row.get("crs_epsg", 4326)),
        )
    for _, row in edges.iterrows():
        attrs = row.to_dict()
        u = int(attrs.pop("u"))
        v = int(attrs.pop("v"))
        G.add_edge(u, v, **attrs)
    return G
