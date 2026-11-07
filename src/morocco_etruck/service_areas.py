"""ADM service-area candidates and scientifically cautious OSM access validation."""

from __future__ import annotations

import logging
import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import networkx as nx
import pandas as pd
import requests
from bs4 import BeautifulSoup

from morocco_etruck.road_network import bearing_deg, geodesic_length_m

logger = logging.getLogger(__name__)

DIR_CASA_AGADIR = "Casablanca→Agadir"
DIR_AGADIR_CASA = "Agadir→Casablanca"

# Field definitions (also documented in reports/task01b_scientific_audit.md):
# location_match_status: matched_osm | unmatched
# directed_access_status:
#   entrance_and_exit | entrance_only | exit_only | opposite_carriageway_only |
#   proximity_only | unresolved
# hgv_access_status: permitted | restricted | unknown
# proximity_only means near a motorway node but no directed motorway_link path found.


class ServiceAreaError(Exception):
    pass


@dataclass
class AdmCandidate:
    official_name: str
    partner: str
    travel_direction: str
    name_token: str
    source_url: str


def normalize_token(text: str) -> str:
    t = text.lower()
    t = t.replace("é", "e").replace("è", "e").replace("ê", "e")
    t = re.sub(r"[^a-z0-9]+", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def parse_direction(name: str) -> str | None:
    n = name.lower()
    if "casablanca" in n and "agadir" in n:
        i_casa = n.find("casablanca")
        i_aga = n.find("agadir")
        if i_casa < i_aga:
            return DIR_CASA_AGADIR
        return DIR_AGADIR_CASA
    return None


def corridor_token_match(name: str, tokens: list[str]) -> str | None:
    norm = normalize_token(name)
    for tok in tokens:
        if normalize_token(tok) in norm:
            return normalize_token(tok)
    return None


def fetch_adm_directory(url: str, timeout: int = 60) -> str:
    headers = {
        "User-Agent": "morocco-etruck-research/0.1 (PhD pilot dataset; academic use)",
        "Accept": "text/html",
    }
    resp = requests.get(url, headers=headers, timeout=timeout)
    resp.raise_for_status()
    return resp.text


def parse_adm_candidates(html: str, source_url: str, tokens: list[str]) -> list[AdmCandidate]:
    soup = BeautifulSoup(html, "lxml")
    table = soup.find("table")
    if table is None:
        raise ServiceAreaError("ADM page has no HTML table of service areas")
    rows = []
    for tr in table.find_all("tr"):
        cells = [c.get_text(" ", strip=True) for c in tr.find_all(["td", "th"])]
        if len(cells) < 2:
            continue
        if cells[0].lower().startswith("aire"):
            continue
        name, partner = cells[0], cells[1]
        token = corridor_token_match(name, tokens)
        if token is None:
            continue
        direction = parse_direction(name)
        if direction is None:
            logger.warning("Could not parse travel direction for %s", name)
            continue
        rows.append(
            AdmCandidate(
                official_name=name,
                partner=partner,
                travel_direction=direction,
                name_token=token,
                source_url=source_url,
            )
        )
    logger.info("Parsed %d ADM corridor candidate rows", len(rows))
    return rows


def probe_adm_trafic() -> dict[str, Any]:
    url = "https://m.admtrafic.ma/ajax/stationservice"
    try:
        resp = requests.get(
            url,
            headers={"User-Agent": "morocco-etruck-research/0.1", "Accept": "application/json"},
            timeout=30,
        )
        return {
            "url": url,
            "status_code": resp.status_code,
            "ok": resp.ok,
            "bytes": len(resp.content) if resp.ok else 0,
            "note": "Accessible" if resp.ok else "Blocked or unavailable; not used as coordinate source",
        }
    except requests.RequestException as exc:
        return {
            "url": url,
            "status_code": None,
            "ok": False,
            "bytes": 0,
            "note": f"Request failed: {exc}",
        }


def _expected_bearing_for_direction(direction: str) -> float:
    if direction == DIR_CASA_AGADIR:
        return 210.0
    return 30.0


def _bearing_difference(a: float, b: float) -> float:
    d = abs(a - b) % 360.0
    return min(d, 360.0 - d)


def collect_osm_service_pois_pyrosm(pbf_path: Path, bbox: list[float]) -> pd.DataFrame:
    try:
        from pyrosm import OSM
    except ImportError as exc:
        raise ServiceAreaError("pyrosm required for OSM facility extraction") from exc

    osm = OSM(str(pbf_path), bounding_box=bbox)
    custom = {
        "highway": ["services", "rest_area"],
        "amenity": ["fuel", "charging_station"],
    }
    try:
        gdf = osm.get_data_by_custom_criteria(custom_filter=custom, filter_type="keep")
    except Exception as exc:  # noqa: BLE001
        logger.warning("pyrosm custom POI extract failed: %s", exc)
        return pd.DataFrame()

    if gdf is None or gdf.empty:
        logger.warning("No OSM service/fuel features found in bbox")
        return pd.DataFrame()

    rows = []
    for _, row in gdf.iterrows():
        geom = row.geometry
        if geom is None or geom.is_empty:
            continue
        if geom.geom_type == "Point":
            lon, lat = float(geom.x), float(geom.y)
        else:
            c = geom.centroid
            lon, lat = float(c.x), float(c.y)
        name = str(row.get("name", "") or "")
        brand = str(row.get("brand", "") or "")
        osm_id = row.get("id", row.get("osmid", ""))
        rows.append(
            {
                "osm_id": osm_id,
                "lon": lon,
                "lat": lat,
                "name": name,
                "brand": brand,
                "highway": str(row.get("highway", "") or ""),
                "amenity": str(row.get("amenity", "") or ""),
                "name_norm": normalize_token(f"{name} {brand}"),
            }
        )
    return pd.DataFrame(rows)


def nearest_nodes(G: nx.Graph, lon: float, lat: float, k: int = 25) -> list[tuple[Any, float]]:
    scored: list[tuple[Any, float]] = []
    for nid, data in G.nodes(data=True):
        d = geodesic_length_m([(lon, lat), (float(data["lon"]), float(data["lat"]))])
        scored.append((nid, d))
    scored.sort(key=lambda x: x[1])
    return scored[:k]


def edge_bearing(G: nx.Graph, u: Any, v: Any, data: dict[str, Any]) -> float:
    brg = data.get("bearing_deg")
    if brg not in ("", None) and not (isinstance(brg, float) and math.isnan(brg)):
        try:
            return float(brg)
        except (TypeError, ValueError):
            pass
    return bearing_deg(
        float(G.nodes[u]["lon"]),
        float(G.nodes[u]["lat"]),
        float(G.nodes[v]["lon"]),
        float(G.nodes[v]["lat"]),
    )


def motorway_nodes_for_direction(
    G: nx.Graph,
    travel_direction: str,
    bearing_tol: float,
) -> set[Any]:
    """Nodes incident to motorway edges whose bearing matches travel direction."""
    expected = _expected_bearing_for_direction(travel_direction)
    nodes: set[Any] = set()
    edge_iter = G.edges(keys=True, data=True) if G.is_multigraph() else ((u, v, 0, d) for u, v, d in G.edges(data=True))
    for u, v, _k, data in edge_iter:
        if str(data.get("highway", "")) != "motorway":
            continue
        if _bearing_difference(edge_bearing(G, u, v, data), expected) <= bearing_tol:
            nodes.add(u)
            nodes.add(v)
    return nodes


def opposite_motorway_nodes(
    G: nx.Graph,
    travel_direction: str,
    bearing_tol: float,
) -> set[Any]:
    opposite = DIR_AGADIR_CASA if travel_direction == DIR_CASA_AGADIR else DIR_CASA_AGADIR
    return motorway_nodes_for_direction(G, opposite, bearing_tol)


def _out_edges(G: nx.Graph, u: Any):
    if G.is_multigraph():
        for _, v, k, d in G.out_edges(u, keys=True, data=True):
            yield v, k, d
    else:
        for _, v, d in G.out_edges(u, data=True):
            yield v, 0, d


def _in_edges(G: nx.Graph, v: Any):
    if G.is_multigraph():
        for u, _, k, d in G.in_edges(v, keys=True, data=True):
            yield u, k, d
    else:
        for u, _, d in G.in_edges(v, data=True):
            yield u, 0, d


def local_access_subgraph(G: nx.Graph, seed_nodes: list[Any], max_hops: int = 8) -> nx.DiGraph:
    """Undirected BFS neighbourhood, returned as DiGraph preserving original directions."""
    allowed = {"motorway", "motorway_link"}
    visited: set[Any] = set(seed_nodes)
    frontier = list(seed_nodes)
    for _ in range(max_hops):
        nxt = []
        for n in frontier:
            for nbr in set(G.successors(n)) | set(G.predecessors(n)):
                # Keep neighbour if any connecting edge is motorway/link
                keep = False
                for _, _, d in list(_out_edges(G, n)) + list(_out_edges(G, nbr)):
                    pass
                for vv, _, d in _out_edges(G, n):
                    if vv == nbr and str(d.get("highway", "")) in allowed:
                        keep = True
                for uu, _, d in _in_edges(G, n):
                    if uu == nbr and str(d.get("highway", "")) in allowed:
                        keep = True
                if keep and nbr not in visited:
                    visited.add(nbr)
                    nxt.append(nbr)
        frontier = nxt
        if not frontier:
            break
    H = nx.DiGraph()
    for n in visited:
        H.add_node(n, **G.nodes[n])
    for u in visited:
        for v, _, d in _out_edges(G, u):
            if v in visited and str(d.get("highway", "")) in allowed:
                # Collapse parallel edges to shortest for access probe
                if H.has_edge(u, v):
                    if float(d.get("length_m") or 0) < float(H.edges[u, v].get("length_m") or 0):
                        H.edges[u, v].update(d)
                else:
                    H.add_edge(u, v, **d)
    return H


def path_hgv_status(G: nx.Graph, path: list[Any]) -> str:
    """Aggregate HGV status along a node path. restricted > unknown > permitted."""
    statuses = []
    for u, v in zip(path[:-1], path[1:]):
        if G.is_multigraph():
            edges = G.get_edge_data(u, v) or {}
            datas = list(edges.values())
        else:
            datas = [G.edges[u, v]]
        for d in datas:
            statuses.append(str(d.get("hgv_access", "unknown") or "unknown"))
    if any(s == "no" for s in statuses):
        return "restricted"
    if statuses and all(s == "yes" for s in statuses):
        return "permitted"
    return "unknown"


def find_directed_access(
    G: nx.Graph,
    facility_lon: float,
    facility_lat: float,
    travel_direction: str,
    *,
    max_facility_node_dist_m: float,
    bearing_tol: float,
    max_path_length_m: float = 2500.0,
) -> dict[str, Any]:
    """
    Probe directed entrance/exit via motorway / motorway_link topology.

    Proximity to a motorway node is never treated as confirmed access.
    """
    result = {
        "directed_access_status": "unresolved",
        "entrance_node_id": None,
        "exit_node_id": None,
        "carriageway_attach_node_id": None,
        "entrance_path_m": None,
        "exit_path_m": None,
        "hgv_access_status": "unknown",
        "access_evidence": "",
    }
    dir_nodes = motorway_nodes_for_direction(G, travel_direction, bearing_tol)
    opp_nodes = opposite_motorway_nodes(G, travel_direction, bearing_tol)
    near = nearest_nodes(G, facility_lon, facility_lat, k=30)
    near = [(n, d) for n, d in near if d <= max_facility_node_dist_m]
    if not near:
        result["directed_access_status"] = "unresolved"
        result["access_evidence"] = "No graph nodes within facility search radius"
        return result

    facility_nodes = [n for n, _ in near]
    # Build local subgraph around facility + nearby carriageway nodes
    seeds = facility_nodes + [n for n, d in nearest_nodes(G, facility_lon, facility_lat, k=80) if d <= max_facility_node_dist_m * 3]
    H = local_access_subgraph(G, seeds, max_hops=10)

    fac_set = set(facility_nodes)
    dir_in_H = [n for n in dir_nodes if n in H]
    opp_in_H = [n for n in opp_nodes if n in H]

    best_in: tuple[float, Any, Any, list[Any]] | None = None
    best_out: tuple[float, Any, Any, list[Any]] | None = None

    for c in dir_in_H:
        for f in fac_set:
            if f not in H or c not in H:
                continue
            if nx.has_path(H, c, f):
                path = nx.shortest_path(H, c, f, weight="length_m")
                length = sum(float(H.edges[a, b]["length_m"]) for a, b in zip(path[:-1], path[1:]))
                if length <= max_path_length_m and (best_in is None or length < best_in[0]):
                    best_in = (length, c, f, path)
            if nx.has_path(H, f, c):
                path = nx.shortest_path(H, f, c, weight="length_m")
                length = sum(float(H.edges[a, b]["length_m"]) for a, b in zip(path[:-1], path[1:]))
                if length <= max_path_length_m and (best_out is None or length < best_out[0]):
                    best_out = (length, f, c, path)

    # Opposite carriageway probe (must not be accepted as valid for this direction)
    opp_touch = False
    for c in opp_in_H:
        for f in fac_set:
            if f in H and c in H and (nx.has_path(H, c, f) or nx.has_path(H, f, c)):
                opp_touch = True
                break
        if opp_touch:
            break

    if best_in and best_out:
        hgv_in = path_hgv_status(H, best_in[3])
        hgv_out = path_hgv_status(H, best_out[3])
        if "restricted" in (hgv_in, hgv_out):
            hgv = "restricted"
        elif hgv_in == "permitted" and hgv_out == "permitted":
            hgv = "permitted"
        else:
            hgv = "unknown"
        result.update(
            {
                "directed_access_status": "entrance_and_exit",
                "entrance_node_id": best_in[2],
                "exit_node_id": best_out[1],
                "carriageway_attach_node_id": best_in[1],
                "entrance_path_m": round(best_in[0], 2),
                "exit_path_m": round(best_out[0], 2),
                "hgv_access_status": hgv,
                "access_evidence": (
                    f"Directed motorway/link path from carriageway node {best_in[1]} "
                    f"to facility node {best_in[2]} ({best_in[0]:.1f} m) and return "
                    f"from {best_out[1]} to {best_out[2]} ({best_out[0]:.1f} m). "
                    f"HGV tags along paths aggregate to '{hgv}'. "
                    "OSM topology ≠ verified legal truck access."
                ),
            }
        )
        return result

    if best_in and not best_out:
        result.update(
            {
                "directed_access_status": "entrance_only",
                "entrance_node_id": best_in[2],
                "carriageway_attach_node_id": best_in[1],
                "entrance_path_m": round(best_in[0], 2),
                "hgv_access_status": path_hgv_status(H, best_in[3]),
                "access_evidence": "Entrance path found; no directed return/exit within limits",
            }
        )
        return result

    if best_out and not best_in:
        result.update(
            {
                "directed_access_status": "exit_only",
                "exit_node_id": best_out[1],
                "carriageway_attach_node_id": best_out[2],
                "exit_path_m": round(best_out[0], 2),
                "hgv_access_status": path_hgv_status(H, best_out[3]),
                "access_evidence": "Exit/return path found; no directed entrance within limits",
            }
        )
        return result

    if opp_touch and not best_in and not best_out:
        result["directed_access_status"] = "opposite_carriageway_only"
        result["access_evidence"] = (
            "Facility touches opposite carriageway topology only; "
            "refusing opposite-direction snap for this ADM travel direction"
        )
        return result

    # Near motorway but no link paths
    near_mw = any(
        any(str(d.get("highway", "")) == "motorway" for _, _, d in _out_edges(G, n))
        or any(str(d.get("highway", "")) == "motorway" for _, _, d in _in_edges(G, n))
        for n, _ in near
    )
    if near_mw:
        result["directed_access_status"] = "proximity_only"
        result["access_evidence"] = (
            "Facility is geometrically near motorway nodes, but no directed "
            "motorway_link entrance/exit path was established"
        )
        return result

    result["access_evidence"] = "No directed access evidence found"
    return result


def _poi_mask(pois: pd.DataFrame, token: str) -> pd.Series:
    mask = pois["name_norm"].str.contains(re.escape(token), na=False)
    if token in {"berrchid", "berrechid"}:
        mask = pois["name_norm"].str.contains(r"berr?echid|berrchid", na=False, regex=True)
    if token in {"oum rbii", "oum rbia"}:
        mask = pois["name_norm"].str.contains(r"oum\s*rb", na=False, regex=True)
    if token == "benguerir":
        mask = pois["name_norm"].str.contains(r"ben\s*guerir|benguerir", na=False, regex=True)
    return mask


def match_candidate_to_graph(
    candidate: AdmCandidate,
    pois: pd.DataFrame,
    G: nx.Graph,
    max_match_distance_m: float,
    max_connection_distance_m: float,
    bearing_tol: float,
) -> dict[str, Any]:
    """Validate location and directed access. Never invents coordinates."""
    base: dict[str, Any] = {
        "official_name": candidate.official_name,
        "partner": candidate.partner,
        "travel_direction": candidate.travel_direction,
        "name_token": candidate.name_token,
        "source": candidate.source_url,
        "lat": None,
        "lon": None,
        "osm_id": None,
        "location_match_status": "unmatched",
        "directed_access_status": "unresolved",
        "hgv_access_status": "unknown",
        "connected_node_id": None,
        "connection_distance_m": None,
        "entrance_node_id": None,
        "exit_node_id": None,
        "entrance_path_m": None,
        "exit_path_m": None,
        "requires_manual_review": True,
        "evidence": "",
        # Deprecated Task 01 field retained for schema continuity (never 'verified' by proximity alone)
        "match_status": "unresolved",
    }

    if pois.empty:
        base["evidence"] = "No OSM service/fuel POIs available in extract for matching"
        return base

    hits = pois[_poi_mask(pois, candidate.name_token)]
    if hits.empty:
        base["evidence"] = f"No OSM POI name matched token '{candidate.name_token}'"
        return base

    # Prefer genuine service-area / rest-area / fuel features; reject weak name collisions
    # (e.g. "Chambre de commerce ... Settat" must not count as ADS Settat).
    hits = hits.copy()
    name_l = hits["name"].astype(str).str.lower()
    hwy = hits["highway"].astype(str).str.lower()
    amen = hits["amenity"].astype(str).str.lower()
    hits["_is_aire"] = name_l.str.contains(r"aire\s+de\s+service|rest\s*area|aire\s+de\s+repos", regex=True)
    hits["_is_services_tag"] = hwy.isin(["services", "rest_area"]) | amen.isin(["fuel", "charging_station"])
    hits["_rank"] = hits["_is_aire"].astype(int) * 3 + hits["_is_services_tag"].astype(int)
    hits = hits.sort_values("_rank", ascending=False)
    best_rank = int(hits.iloc[0]["_rank"])
    if best_rank <= 0:
        base["evidence"] = (
            f"OSM name token '{candidate.name_token}' matched only non-service features "
            f"(e.g. '{hits.iloc[0]['name']}'); refusing false-positive location match"
        )
        return base

    poi = hits.iloc[0]
    lon, lat = float(poi["lon"]), float(poi["lat"])
    base.update(
        {
            "lat": lat,
            "lon": lon,
            "osm_id": poi["osm_id"],
            "location_match_status": "matched_osm",
        }
    )

    access = find_directed_access(
        G,
        lon,
        lat,
        candidate.travel_direction,
        max_facility_node_dist_m=max_match_distance_m,
        bearing_tol=bearing_tol,
        max_path_length_m=max(2500.0, max_connection_distance_m * 4),
    )
    base.update(
        {
            "directed_access_status": access["directed_access_status"],
            "hgv_access_status": access["hgv_access_status"],
            "entrance_node_id": access.get("entrance_node_id"),
            "exit_node_id": access.get("exit_node_id"),
            "connected_node_id": access.get("carriageway_attach_node_id")
            or access.get("entrance_node_id")
            or access.get("exit_node_id"),
            "entrance_path_m": access.get("entrance_path_m"),
            "exit_path_m": access.get("exit_path_m"),
            "connection_distance_m": access.get("entrance_path_m") or access.get("exit_path_m"),
            "evidence": (
                f"OSM location osm_id={poi['osm_id']} name='{poi['name']}'. "
                f"{access.get('access_evidence', '')}"
            ),
        }
    )

    # Conservative legacy match_status for continuity
    if access["directed_access_status"] == "entrance_and_exit":
        base["match_status"] = "access_topology_ok"
        # Still require manual review unless HGV explicitly permitted
        base["requires_manual_review"] = access["hgv_access_status"] != "permitted"
    elif access["directed_access_status"] in {"entrance_only", "exit_only", "proximity_only", "opposite_carriageway_only"}:
        base["match_status"] = "partial_access"
        base["requires_manual_review"] = True
    else:
        base["match_status"] = "unresolved"
        base["requires_manual_review"] = True

    return base


def build_candidate_sites(
    config: dict[str, Any],
    G: nx.Graph,
    pbf_path: Path,
    bbox: list[float],
    adm_html_cache: Path | None = None,
    *,
    allow_network: bool = True,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    sa = config["service_areas"]
    url = sa["source_url"]
    meta: dict[str, Any] = {"adm_url": url}

    if adm_html_cache and adm_html_cache.exists():
        html = adm_html_cache.read_text(encoding="utf-8")
        meta["adm_html_source"] = str(adm_html_cache)
        meta["adm_fetched"] = False
    else:
        if not allow_network:
            raise ServiceAreaError("ADM HTML cache missing and network disallowed")
        html = fetch_adm_directory(url)
        if adm_html_cache:
            adm_html_cache.parent.mkdir(parents=True, exist_ok=True)
            adm_html_cache.write_text(html, encoding="utf-8")
            meta["adm_html_source"] = str(adm_html_cache)
        meta["adm_fetched"] = True

    if allow_network:
        meta["adm_trafic"] = probe_adm_trafic()
    else:
        meta["adm_trafic"] = {"ok": False, "note": "Skipped (offline rebuild)"}

    candidates = parse_adm_candidates(html, url, sa["corridor_name_tokens"])
    pois = collect_osm_service_pois_pyrosm(pbf_path, bbox)
    meta["osm_poi_count"] = int(len(pois))

    rows = [
        match_candidate_to_graph(
            c,
            pois,
            G,
            float(sa["max_match_distance_m"]),
            float(sa["max_connection_distance_m"]),
            float(sa["direction_bearing_tolerance_deg"]),
        )
        for c in candidates
    ]
    return pd.DataFrame(rows), meta


def write_candidate_sites(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False)
    logger.info("Wrote %s (%d candidates)", path, len(df))
