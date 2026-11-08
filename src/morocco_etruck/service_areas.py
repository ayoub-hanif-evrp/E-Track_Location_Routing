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


MIN_ACCESS_PATH_M = 1.0  # reject zero-length / self-node "paths"
ACCESS_EDGE_TYPES = {"motorway", "motorway_link", "service"}
FACILITY_ATTACH_TYPES = {"motorway_link", "service"}


def local_access_subgraph(G: nx.Graph, seed_nodes: list[Any], max_hops: int = 8) -> nx.DiGraph:
    """Undirected BFS neighbourhood for access probing (motorway/link/service)."""
    allowed = ACCESS_EDGE_TYPES
    visited: set[Any] = set(seed_nodes)
    frontier = list(seed_nodes)
    for _ in range(max_hops):
        nxt = []
        for n in frontier:
            for nbr in set(G.successors(n)) | set(G.predecessors(n)):
                keep = False
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
        for v, key, d in _out_edges(G, u):
            if v in visited and str(d.get("highway", "")) in allowed:
                payload = dict(d)
                payload["edge_key"] = key
                if H.has_edge(u, v):
                    if float(d.get("length_m") or 0) < float(H.edges[u, v].get("length_m") or 0):
                        H.edges[u, v].update(payload)
                else:
                    H.add_edge(u, v, **payload)
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


def path_length_and_edges(G: nx.Graph, path: list[Any]) -> tuple[float, list[str]]:
    length = 0.0
    edge_ids: list[str] = []
    for u, v in zip(path[:-1], path[1:]):
        data = G.edges[u, v]
        length += float(data.get("length_m") or 0.0)
        wid = data.get("osm_way_id", "")
        key = data.get("edge_key", "")
        edge_ids.append(f"{u}->{v}:{wid}:{key}")
    return length, edge_ids


def incident_highways(G: nx.Graph, n: Any) -> set[str]:
    hw: set[str] = set()
    for _, _, d in _out_edges(G, n):
        hw.add(str(d.get("highway", "") or ""))
    for _, _, d in _in_edges(G, n):
        hw.add(str(d.get("highway", "") or ""))
    return hw


def is_facility_attachment_node(G: nx.Graph, n: Any, carriageway_nodes: set[Any]) -> bool:
    """
    Facility attachment must be independently identifiable from access roads.

    Pure carriageway motorway nodes are never valid facility endpoints — this
    rejects the Task 01B zero-length self-path false positive.
    """
    hw = incident_highways(G, n)
    if hw & FACILITY_ATTACH_TYPES:
        return True
    # Allow non-carriageway nodes that only appear via service/link neighbourhood
    if n in carriageway_nodes and hw <= {"motorway", ""}:
        return False
    if "motorway" in hw and not (hw & FACILITY_ATTACH_TYPES):
        return False
    return False


def _valid_access_path(
    H: nx.DiGraph,
    source: Any,
    target: Any,
    *,
    max_path_length_m: float,
) -> tuple[float, list[Any], list[str]] | None:
    """Return positive-length path with ≥1 edge, else None."""
    if source == target:
        return None
    if source not in H or target not in H:
        return None
    if not nx.has_path(H, source, target):
        return None
    path = nx.shortest_path(H, source, target, weight="length_m")
    if len(path) < 2:
        return None
    length, edge_ids = path_length_and_edges(H, path)
    if length < MIN_ACCESS_PATH_M or length > max_path_length_m:
        return None
    return length, path, edge_ids


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
    Probe directed entrance/exit using motorway, motorway_link, and service edges.

    Rules:
    - Facility attachment ≠ carriageway attach node
    - Paths must traverse real edges with length ≥ MIN_ACCESS_PATH_M
    - Proximity alone never yields entrance_and_exit
    """
    result = {
        "directed_access_status": "unresolved",
        "entrance_node_id": None,
        "exit_node_id": None,
        "carriageway_attach_node_id": None,
        "entrance_path_m": None,
        "exit_path_m": None,
        "entrance_edge_ids": "",
        "exit_edge_ids": "",
        "hgv_access_status": "unknown",
        "access_evidence": "",
    }
    dir_nodes = motorway_nodes_for_direction(G, travel_direction, bearing_tol)
    opp_nodes = opposite_motorway_nodes(G, travel_direction, bearing_tol)
    near = [(n, d) for n, d in nearest_nodes(G, facility_lon, facility_lat, k=40) if d <= max_facility_node_dist_m]
    if not near:
        result["access_evidence"] = "No graph nodes within facility search radius"
        return result

    facility_nodes = [
        n for n, _ in near if is_facility_attachment_node(G, n, dir_nodes | opp_nodes)
    ]
    if not facility_nodes:
        # Location may be near motorway only — not an access demonstration
        result["directed_access_status"] = "proximity_only"
        result["access_evidence"] = (
            "Nearby nodes are carriageway-only; no motorway_link/service attachment "
            "node found for the facility (zero-length self-paths rejected)"
        )
        return result

    seeds = list({n for n, _ in near} | set(facility_nodes))
    seeds += [n for n, d in nearest_nodes(G, facility_lon, facility_lat, k=100) if d <= max_facility_node_dist_m * 3]
    H = local_access_subgraph(G, seeds, max_hops=12)

    fac_set = [n for n in facility_nodes if n in H]
    dir_in_H = [n for n in dir_nodes if n in H]
    opp_in_H = [n for n in opp_nodes if n in H]

    best_in: tuple[float, Any, Any, list[Any], list[str]] | None = None
    best_out: tuple[float, Any, Any, list[Any], list[str]] | None = None

    for c in dir_in_H:
        for f in fac_set:
            if c == f:
                continue
            got = _valid_access_path(H, c, f, max_path_length_m=max_path_length_m)
            if got and (best_in is None or got[0] < best_in[0]):
                length, path, eids = got
                best_in = (length, c, f, path, eids)
            got = _valid_access_path(H, f, c, max_path_length_m=max_path_length_m)
            if got and (best_out is None or got[0] < best_out[0]):
                length, path, eids = got
                best_out = (length, f, c, path, eids)

    opp_touch = False
    for c in opp_in_H:
        for f in fac_set:
            if c == f:
                continue
            if _valid_access_path(H, c, f, max_path_length_m=max_path_length_m) or _valid_access_path(
                H, f, c, max_path_length_m=max_path_length_m
            ):
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
                "entrance_edge_ids": "|".join(best_in[4]),
                "exit_edge_ids": "|".join(best_out[4]),
                "hgv_access_status": hgv,
                "access_evidence": (
                    f"Positive-length directed paths: carriageway {best_in[1]} → "
                    f"facility attach {best_in[2]} ({best_in[0]:.1f} m, edges={len(best_in[4])}); "
                    f"return {best_out[1]} → {best_out[2]} ({best_out[0]:.1f} m, edges={len(best_out[4])}). "
                    f"HGV aggregate='{hgv}'. OSM topology ≠ legal truck certification."
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
                "entrance_edge_ids": "|".join(best_in[4]),
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
                "exit_edge_ids": "|".join(best_out[4]),
                "hgv_access_status": path_hgv_status(H, best_out[3]),
                "access_evidence": "Exit/return path found; no directed entrance within limits",
            }
        )
        return result

    if opp_touch:
        result["directed_access_status"] = "opposite_carriageway_only"
        result["access_evidence"] = (
            "Facility attaches only to opposite carriageway topology; "
            "refusing opposite-direction snap"
        )
        return result

    result["directed_access_status"] = "proximity_only"
    result["access_evidence"] = (
        "Facility attachment candidates exist nearby, but no valid positive-length "
        "directed entrance/exit to the required carriageway was found"
    )
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


def _rank_service_pois(hits: pd.DataFrame) -> pd.DataFrame:
    hits = hits.copy()
    name_l = hits["name"].astype(str).str.lower()
    hwy = hits["highway"].astype(str).str.lower()
    amen = hits["amenity"].astype(str).str.lower()
    hits["_is_aire"] = name_l.str.contains(
        r"aire\s+de\s+service|rest\s*area|aire\s+de\s+repos", regex=True
    )
    hits["_is_services_tag"] = hwy.isin(["services", "rest_area"]) | amen.isin(
        ["fuel", "charging_station"]
    )
    hits["_rank"] = hits["_is_aire"].astype(int) * 3 + hits["_is_services_tag"].astype(int)
    return hits[hits["_rank"] > 0].sort_values("_rank", ascending=False)


def _name_side_affinity(name: str, travel_direction: str) -> float:
    """Soft prior from est/ouest naming (not alone sufficient for access)."""
    n = normalize_token(name)
    # On A3, dual aires are often named est/ouest for opposite sides.
    if "ouest" in n or "west" in n:
        return 1.0 if travel_direction == DIR_CASA_AGADIR else 0.3
    if "est" in n or "east" in n:
        return 1.0 if travel_direction == DIR_AGADIR_CASA else 0.3
    return 0.5


def _access_score(status: str) -> float:
    return {
        "entrance_and_exit": 4.0,
        "entrance_only": 2.0,
        "exit_only": 2.0,
        "opposite_carriageway_only": 0.2,
        "proximity_only": 0.1,
        "unresolved": 0.0,
    }.get(status, 0.0)


def _empty_candidate_row(candidate: AdmCandidate) -> dict[str, Any]:
    return {
        "official_name": candidate.official_name,
        "partner": candidate.partner,
        "travel_direction": candidate.travel_direction,
        "name_token": candidate.name_token,
        "source": candidate.source_url,
        "lat": None,
        "lon": None,
        "osm_id": None,
        "osm_object_type": None,
        "location_match_status": "unmatched",
        "location_match_confidence": "none",
        "directed_access_status": "unresolved",
        "hgv_access_status": "unknown",
        "connected_node_id": None,
        "connection_distance_m": None,
        "entrance_node_id": None,
        "exit_node_id": None,
        "entrance_path_m": None,
        "exit_path_m": None,
        "entrance_edge_ids": "",
        "exit_edge_ids": "",
        "requires_manual_review": True,
        "evidence": "",
        "match_status": "unresolved",
    }


def match_candidate_to_graph(
    candidate: AdmCandidate,
    pois: pd.DataFrame,
    access_G: nx.Graph,
    max_match_distance_m: float,
    max_connection_distance_m: float,
    bearing_tol: float,
    *,
    reserved_osm_ids: set[Any] | None = None,
) -> dict[str, Any]:
    """
    Evaluate all plausible OSM features for one ADM directional entry.

    Does not invent coordinates. Does not accept zero-length self-paths.
    Prefer features with positive-length directed access for this travel direction.
    Avoid silently reusing an OSM object already claimed by the opposite direction
    unless no alternative exists and access evidence is direction-specific.
    """
    base = _empty_candidate_row(candidate)
    reserved_osm_ids = reserved_osm_ids or set()

    if pois.empty:
        base["evidence"] = "No OSM service/fuel POIs available in extract for matching"
        return base

    hits = _rank_service_pois(pois[_poi_mask(pois, candidate.name_token)])
    if hits.empty:
        base["evidence"] = f"No OSM service-area POI matched token '{candidate.name_token}'"
        return base

    scored: list[tuple[float, dict[str, Any], dict[str, Any]]] = []
    for _, poi in hits.iterrows():
        lon, lat = float(poi["lon"]), float(poi["lat"])
        access = find_directed_access(
            access_G,
            lon,
            lat,
            candidate.travel_direction,
            max_facility_node_dist_m=max_match_distance_m,
            bearing_tol=bearing_tol,
            max_path_length_m=max(2500.0, max_connection_distance_m * 4),
        )
        osm_id = poi["osm_id"]
        score = (
            _access_score(access["directed_access_status"]) * 10.0
            + float(poi["_rank"])
            + _name_side_affinity(str(poi["name"]), candidate.travel_direction)
        )
        if osm_id in reserved_osm_ids:
            # Strong penalty: opposite direction already claimed this object
            score -= 50.0
        scored.append((score, poi.to_dict(), access))

    scored.sort(key=lambda x: x[0], reverse=True)
    best_score, poi, access = scored[0]

    # If best is reserved and score collapsed, prefer next unreserved with any access
    if poi["osm_id"] in reserved_osm_ids:
        alternatives = [s for s in scored if s[1]["osm_id"] not in reserved_osm_ids]
        if alternatives and alternatives[0][0] > best_score - 40:
            best_score, poi, access = alternatives[0]
        elif access["directed_access_status"] not in {"entrance_and_exit", "entrance_only", "exit_only"}:
            # Ambiguous shared object without independent access — leave unresolved location reuse
            base["evidence"] = (
                f"Only OSM feature osm_id={poi['osm_id']} matched token, but it is already "
                f"assigned to the opposite direction and lacks independent directed access "
                f"for {candidate.travel_direction}"
            )
            return base

    lon, lat = float(poi["lon"]), float(poi["lat"])
    osm_type = "way" if str(poi.get("highway", "")) else "node"
    conf = "high" if access["directed_access_status"] == "entrance_and_exit" else "medium"
    if access["directed_access_status"] in {"proximity_only", "unresolved"}:
        conf = "low"

    base.update(
        {
            "lat": lat,
            "lon": lon,
            "osm_id": poi["osm_id"],
            "osm_object_type": osm_type,
            "location_match_status": "matched_osm",
            "location_match_confidence": conf,
            "directed_access_status": access["directed_access_status"],
            "hgv_access_status": access["hgv_access_status"],
            "entrance_node_id": access.get("entrance_node_id"),
            "exit_node_id": access.get("exit_node_id"),
            "connected_node_id": access.get("carriageway_attach_node_id")
            or access.get("entrance_node_id")
            or access.get("exit_node_id"),
            "entrance_path_m": access.get("entrance_path_m"),
            "exit_path_m": access.get("exit_path_m"),
            "entrance_edge_ids": access.get("entrance_edge_ids", ""),
            "exit_edge_ids": access.get("exit_edge_ids", ""),
            "connection_distance_m": access.get("entrance_path_m") or access.get("exit_path_m"),
            "evidence": (
                f"OSM osm_id={poi['osm_id']} name='{poi['name']}' "
                f"(score={best_score:.2f}). {access.get('access_evidence', '')}"
            ),
        }
    )

    if access["directed_access_status"] == "entrance_and_exit":
        # Hard reject residual zero-length records
        if (access.get("entrance_path_m") or 0) < MIN_ACCESS_PATH_M or (
            access.get("exit_path_m") or 0
        ) < MIN_ACCESS_PATH_M:
            base["directed_access_status"] = "unresolved"
            base["match_status"] = "unresolved"
            base["evidence"] += " Rejected residual zero-length entrance/exit."
            return base
        base["match_status"] = "access_topology_ok"
        base["requires_manual_review"] = access["hgv_access_status"] != "permitted"
    elif access["directed_access_status"] in {
        "entrance_only",
        "exit_only",
        "proximity_only",
        "opposite_carriageway_only",
    }:
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
    access_G: nx.Graph | None = None,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    sa = config["service_areas"]
    url = sa["source_url"]
    meta: dict[str, Any] = {"adm_url": url}
    graph_for_access = access_G if access_G is not None else G

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
    meta["access_graph_nodes"] = graph_for_access.number_of_nodes()
    meta["access_graph_edges"] = graph_for_access.number_of_edges()

    # Match Casa→Agadir and Agadir→Casa independently; reserve OSM IDs after assignment
    reserved: set[Any] = set()
    # Process one direction family at a time so opposite entries compete fairly
    rows: list[dict[str, Any]] = []
    by_token: dict[str, list[AdmCandidate]] = {}
    for c in candidates:
        by_token.setdefault(c.name_token, []).append(c)

    for token, group in by_token.items():
        # Score each direction against all POIs without reservation first
        provisional: list[tuple[AdmCandidate, dict[str, Any]]] = []
        for c in group:
            row = match_candidate_to_graph(
                c,
                pois,
                graph_for_access,
                float(sa["max_match_distance_m"]),
                float(sa["max_connection_distance_m"]),
                float(sa["direction_bearing_tolerance_deg"]),
                reserved_osm_ids=set(),
            )
            provisional.append((c, row))

        # If both directions selected the same osm_id, keep the better access one;
        # re-match the other with that osm_id reserved.
        ids = [r.get("osm_id") for _, r in provisional if r.get("osm_id") is not None]
        if len(group) == 2 and len(set(map(str, ids))) == 1 and ids[0] is not None:
            provisional.sort(
                key=lambda cr: _access_score(cr[1].get("directed_access_status", "")),
                reverse=True,
            )
            keep_c, keep_row = provisional[0]
            other_c, _ = provisional[1]
            other_row = match_candidate_to_graph(
                other_c,
                pois,
                graph_for_access,
                float(sa["max_match_distance_m"]),
                float(sa["max_connection_distance_m"]),
                float(sa["direction_bearing_tolerance_deg"]),
                reserved_osm_ids={keep_row["osm_id"]},
            )
            rows.extend([keep_row, other_row])
            if keep_row.get("osm_id") is not None:
                reserved.add(keep_row["osm_id"])
            if other_row.get("osm_id") is not None:
                reserved.add(other_row["osm_id"])
        else:
            for _, row in provisional:
                rows.append(row)
                if row.get("osm_id") is not None:
                    reserved.add(row["osm_id"])

    # Restore ADM listing order
    order = {(c.official_name, c.travel_direction): i for i, c in enumerate(candidates)}
    rows.sort(key=lambda r: order.get((r["official_name"], r["travel_direction"]), 999))
    return pd.DataFrame(rows), meta


def write_candidate_sites(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False)
    logger.info("Wrote %s (%d candidates)", path, len(df))
