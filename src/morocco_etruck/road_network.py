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
from shapely.geometry import LineString, mapping

logger = logging.getLogger(__name__)
GEOD = Geod(ellps="WGS84")

HIGHWAY_MOTORWAY = {"motorway", "motorway_link"}


class RoadNetworkError(Exception):
    """Raised when the road network cannot be constructed."""


def geodesic_length_m(coords: list[tuple[float, float]]) -> float:
    """Length in metres along WGS84 geodesic. coords are (lon, lat)."""
    if len(coords) < 2:
        return 0.0
    total = 0.0
    for i in range(len(coords) - 1):
        _, _, dist = GEOD.inv(coords[i][0], coords[i][1], coords[i + 1][0], coords[i + 1][1])
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
    edges = edges[edges["highway"].isin(highway_classes)].copy()
    if edges.empty:
        raise RoadNetworkError(f"No edges with highway in {highway_classes} inside bbox")
    used = set(edges["u"].tolist()) | set(edges["v"].tolist())
    if nodes is None or nodes.empty:
        raise RoadNetworkError("pyrosm returned edges without nodes")
    id_col = "id" if "id" in nodes.columns else "osmid"
    nodes = nodes[nodes[id_col].isin(used)].copy()
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


def _is_reverse_oneway(oneway: Any) -> bool:
    if oneway is None or (isinstance(oneway, float) and math.isnan(oneway)):
        return False
    return str(oneway).strip().lower() in {"-1", "reverse"}


def build_multidigraph_from_directed_edges(
    nodes: pd.DataFrame,
    edges: pd.DataFrame,
    *,
    assume_pyrosm_pre_expanded: bool = True,
) -> tuple[nx.MultiDiGraph, dict[str, Any]]:
    """
    Build a MultiDiGraph from edge rows that are already travel-directed.

    pyrosm ``get_network`` expands OSM ways into directed edge rows. Re-expanding
    ``oneway=no`` into both directions would duplicate bidirectional roads.
    When ``assume_pyrosm_pre_expanded`` is True (default), each row becomes exactly
    one directed edge; ``oneway=-1`` reverses orientation and geometry.
    """
    G = nx.MultiDiGraph()
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

    parallel_if_digraph = 0
    seen_uv: dict[tuple[int, int], int] = {}
    edges_added = 0

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
        tags = {
            k: v
            for k, v in tags.items()
            if v is not None and not (isinstance(v, float) and math.isnan(v))
        }

        coords = _coords_from_geometry(
            row.geometry if hasattr(row, "geometry") else row.get("geometry")
        )
        length_m = geodesic_length_m(coords) if coords else 0.0
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

        a, b, edge_coords = u, v, coords
        if _is_reverse_oneway(oneway):
            a, b = v, u
            edge_coords = list(reversed(coords)) if coords else coords

        # If not assuming pre-expansion and oneway explicitly allows both, add reverse too.
        directions = [(a, b, edge_coords)]
        if not assume_pyrosm_pre_expanded:
            ow = "" if oneway is None else str(oneway).strip().lower()
            if ow in {"no", "false", "0"} or (ow == "" and highway not in HIGHWAY_MOTORWAY):
                directions.append((b, a, list(reversed(edge_coords)) if edge_coords else edge_coords))

        for aa, bb, ecoords in directions:
            key = (aa, bb)
            seen_uv[key] = seen_uv.get(key, 0) + 1
            if seen_uv[key] > 1:
                parallel_if_digraph += 1
            brg = None
            if ecoords and len(ecoords) >= 2:
                brg = bearing_deg(ecoords[0][0], ecoords[0][1], ecoords[-1][0], ecoords[-1][1])
            G.add_edge(
                aa,
                bb,
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
                geometry_wkt=LineString(ecoords).wkt if ecoords and len(ecoords) >= 2 else "",
                bearing_deg=brg if brg is not None else "",
                crs_epsg=4326,
            )
            edges_added += 1

    audit = {
        "assume_pyrosm_pre_expanded": assume_pyrosm_pre_expanded,
        "n_nodes": G.number_of_nodes(),
        "n_edges_multidigraph": G.number_of_edges(),
        "parallel_uv_collisions_if_digraph": parallel_if_digraph,
        "unique_directed_uv_pairs": len(seen_uv),
        "note": (
            "parallel_uv_collisions_if_digraph counts additional edges that share the same "
            "(u,v) and would overwrite attributes in nx.DiGraph; MultiDiGraph preserves them."
        ),
    }
    logger.info(
        "Built MultiDiGraph: %d nodes, %d edges (%d parallel collisions vs DiGraph)",
        audit["n_nodes"],
        audit["n_edges_multidigraph"],
        parallel_if_digraph,
    )
    return G, audit


# Backward-compatible alias used in older call sites / tests
def build_digraph_from_pyrosm(
    nodes: pd.DataFrame,
    edges: pd.DataFrame,
) -> nx.MultiDiGraph:
    G, _ = build_multidigraph_from_directed_edges(nodes, edges)
    return G


def resolve_extract_input(
    raw_dir: Path,
    extract_info: dict[str, Any],
    national_pbf: Path,
    root: Path | None = None,
) -> tuple[Path, list[float]]:
    """Return the PBF path to read and bbox for Python-side filtering."""
    root = root or raw_dir.parent.parent

    def _abs(p: str | Path) -> Path:
        path = Path(p)
        if path.is_absolute():
            return path
        return (root / path).resolve()

    if extract_info.get("tool") == "osmium-extract":
        return _abs(extract_info["output"]), extract_info["bbox"]
    if extract_info.get("tool") == "pyrosm-python-bbox-filter":
        marker = _abs(extract_info["marker"])
        data = json.loads(marker.read_text(encoding="utf-8"))
        return _abs(data["source_pbf"]), list(data["bbox"])
    return national_pbf, extract_info.get("bbox", [])


def build_pilot_graph(
    national_pbf: Path,
    extract_info: dict[str, Any],
    config: dict[str, Any],
    root: Path | None = None,
) -> tuple[nx.MultiDiGraph, dict[str, Any]]:
    raw_dir = Path(national_pbf).parent
    pbf_path, bbox = resolve_extract_input(raw_dir, extract_info, national_pbf, root=root)
    highway_classes = list(config["osm"]["highway_classes"])
    nodes, edges = load_network_tables_pyrosm(pbf_path, bbox, highway_classes)
    G, audit = build_multidigraph_from_directed_edges(nodes, edges)
    if G.number_of_edges() == 0:
        raise RoadNetworkError("Directed graph has zero edges after filtering")
    return G, audit


def export_graph_artifacts(G: nx.MultiDiGraph | nx.DiGraph, processed_dir: Path) -> dict[str, Path]:
    processed_dir.mkdir(parents=True, exist_ok=True)
    nodes_path = processed_dir / "road_nodes.csv"
    edges_path = processed_dir / "road_edges.csv"
    graphml_path = processed_dir / "pilot_network.graphml"
    geojson_path = processed_dir / "pilot_network.geojson"

    node_rows = [
        {
            "node_id": nid,
            "osm_node_id": data.get("osm_node_id", nid),
            "lon": data.get("lon"),
            "lat": data.get("lat"),
            "crs_epsg": data.get("crs_epsg", 4326),
        }
        for nid, data in G.nodes(data=True)
    ]
    pd.DataFrame(node_rows).to_csv(nodes_path, index=False)

    edge_rows = []
    features = []
    # Support MultiDiGraph (u, v, key, data) and DiGraph (u, v, data)
    if G.is_multigraph():
        edge_iter = ((u, v, k, d) for u, v, k, d in G.edges(keys=True, data=True))
    else:
        edge_iter = ((u, v, 0, d) for u, v, d in G.edges(data=True))

    for u, v, key, data in edge_iter:
        row = {
            "u": u,
            "v": v,
            "edge_key": key,
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
        edge_rows.append(row)
        wkt_s = data.get("geometry_wkt") or ""
        if wkt_s:
            geom = wkt.loads(wkt_s)
            props = {k: ("" if val is None else val) for k, val in row.items() if k != "geometry_wkt"}
            features.append({"type": "Feature", "geometry": mapping(geom), "properties": props})

    pd.DataFrame(edge_rows).to_csv(edges_path, index=False)

    H = nx.MultiDiGraph() if G.is_multigraph() else nx.DiGraph()
    for nid, data in G.nodes(data=True):
        H.add_node(nid, **{k: ("" if val is None else val) for k, val in data.items()})
    if G.is_multigraph():
        for u, v, key, data in G.edges(keys=True, data=True):
            H.add_edge(u, v, key=key, **{k: ("" if val is None else val) for k, val in data.items()})
    else:
        for u, v, data in G.edges(data=True):
            H.add_edge(u, v, **{k: ("" if val is None else val) for k, val in data.items()})
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


def load_graph_from_csv(nodes_csv: Path, edges_csv: Path) -> nx.MultiDiGraph:
    nodes = pd.read_csv(nodes_csv)
    edges = pd.read_csv(edges_csv)
    G = nx.MultiDiGraph()
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
        key = int(attrs.pop("edge_key")) if "edge_key" in attrs and pd.notna(attrs.get("edge_key")) else 0
        # Clean NaN
        clean = {}
        for k, val in attrs.items():
            if isinstance(val, float) and math.isnan(val):
                clean[k] = ""
            else:
                clean[k] = val
        G.add_edge(u, v, key=key, **clean)
    return G


def path_edge_geometries(
    G: nx.Graph,
    path: list[Any],
) -> list[tuple[float, float]]:
    """Concatenate directed edge geometries along a node path (travel orientation)."""
    coords: list[tuple[float, float]] = []
    for u, v in zip(path[:-1], path[1:]):
        data = _best_edge_data(G, u, v)
        wkt_s = data.get("geometry_wkt") or ""
        if wkt_s:
            geom = wkt.loads(str(wkt_s))
            seg = list(geom.coords)
        else:
            seg = [(float(G.nodes[u]["lon"]), float(G.nodes[u]["lat"])),
                   (float(G.nodes[v]["lon"]), float(G.nodes[v]["lat"]))]
        if coords and seg and coords[-1] == seg[0]:
            coords.extend(seg[1:])
        else:
            coords.extend(seg)
    return coords


def _best_edge_data(G: nx.Graph, u: Any, v: Any) -> dict[str, Any]:
    if G.is_multigraph():
        edges = G.get_edge_data(u, v)
        if not edges:
            raise KeyError((u, v))
        # Prefer shortest length among parallel edges
        key = min(edges, key=lambda k: float(edges[k].get("length_m") or 0.0))
        return edges[key]
    return G.edges[u, v]
