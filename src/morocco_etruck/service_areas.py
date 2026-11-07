"""ADM service-area candidates and direction-aware OSM matching."""

from __future__ import annotations

import logging
import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import networkx as nx
import pandas as pd
import requests
from bs4 import BeautifulSoup
from pyproj import Geod

from morocco_etruck.road_network import bearing_deg, geodesic_length_m

logger = logging.getLogger(__name__)
GEOD = Geod(ellps="WGS84")

DIR_CASA_AGADIR = "Casablanca→Agadir"
DIR_AGADIR_CASA = "Agadir→Casablanca"


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
    # ADM uses "Casablanca --> Agadir" style arrows
    if "casablanca" in n and "agadir" in n:
        # Find order of appearance
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
            # Amskroud row includes direction in name on ADM page
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
    """Optional secondary coordinate source; may be blocked (403)."""
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
    # A3 Casa→Agadir is broadly SW (~210°); reverse NE (~30°)
    if direction == DIR_CASA_AGADIR:
        return 210.0
    return 30.0


def _bearing_difference(a: float, b: float) -> float:
    d = abs(a - b) % 360.0
    return min(d, 360.0 - d)


def collect_osm_service_pois_pyrosm(pbf_path: Path, bbox: list[float]) -> pd.DataFrame:
    """Extract highway=services / amenity=fuel POIs from OSM via pyrosm custom filter."""
    try:
        from pyrosm import OSM
    except ImportError as exc:
        raise ServiceAreaError("pyrosm required for OSM facility extraction") from exc

    osm = OSM(str(pbf_path), bounding_box=bbox)
    # Custom filter for service areas and fuel
    custom = {
        "highway": ["services", "rest_area"],
        "amenity": ["fuel", "charging_station"],
    }
    try:
        gdf = osm.get_data_by_custom_criteria(
            custom_filter=custom,
            # Keep nodes and ways/polygons where possible
            filter_type="keep",
        )
    except Exception as exc:  # noqa: BLE001 — pyrosm raises varied errors
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


def nearest_nodes(G: nx.DiGraph, lon: float, lat: float, k: int = 15) -> list[tuple[int, float]]:
    scored: list[tuple[int, float]] = []
    for nid, data in G.nodes(data=True):
        d = geodesic_length_m([(lon, lat), (float(data["lon"]), float(data["lat"]))])
        scored.append((nid, d))
    scored.sort(key=lambda x: x[1])
    return scored[:k]


def edge_compatible_with_direction(
    G: nx.DiGraph,
    u: int,
    v: int,
    travel_direction: str,
    tolerance_deg: float,
) -> bool:
    data = G.edges[u, v]
    brg = data.get("bearing_deg")
    if brg == "" or brg is None:
        # Infer from node coordinates
        brg = bearing_deg(G.nodes[u]["lon"], G.nodes[u]["lat"], G.nodes[v]["lon"], G.nodes[v]["lat"])
    else:
        brg = float(brg)
    expected = _expected_bearing_for_direction(travel_direction)
    return _bearing_difference(brg, expected) <= tolerance_deg


def match_candidate_to_graph(
    candidate: AdmCandidate,
    pois: pd.DataFrame,
    G: nx.DiGraph,
    max_match_distance_m: float,
    max_connection_distance_m: float,
    bearing_tol: float,
) -> dict[str, Any]:
    """Match one ADM candidate. Never invents coordinates on failure."""
    base = {
        "official_name": candidate.official_name,
        "partner": candidate.partner,
        "travel_direction": candidate.travel_direction,
        "name_token": candidate.name_token,
        "source": candidate.source_url,
        "lat": None,
        "lon": None,
        "osm_id": None,
        "connected_node_id": None,
        "connection_distance_m": None,
        "match_status": "unresolved",
        "requires_manual_review": True,
        "evidence": "",
    }

    if pois.empty:
        base["evidence"] = "No OSM service/fuel POIs available in extract for matching"
        return base

    token = candidate.name_token
    # Prefer name contains token
    mask = pois["name_norm"].str.contains(re.escape(token), na=False)
    # Berrechid spelling variants
    if token in {"berrchid", "berrechid"}:
        mask = pois["name_norm"].str.contains(r"berr?echid|berrchid", na=False, regex=True)
    if token in {"oum rbii", "oum rbia"}:
        mask = pois["name_norm"].str.contains(r"oum\s*rb", na=False, regex=True)
    if token == "benguerir":
        mask = pois["name_norm"].str.contains(r"ben\s*guerir|benguerir", na=False, regex=True)

    hits = pois[mask]
    if hits.empty:
        base["evidence"] = f"No OSM POI name matched token '{token}'"
        return base

    # Evaluate each hit for direction-compatible motorway connection
    best: dict[str, Any] | None = None
    for _, poi in hits.iterrows():
        lon, lat = float(poi["lon"]), float(poi["lat"])
        candidates_nodes = nearest_nodes(G, lon, lat, k=20)
        for nid, dist_m in candidates_nodes:
            if dist_m > max_match_distance_m:
                break
            # Look at outgoing edges from this node (or incoming for reverse)
            for _, v, edata in G.out_edges(nid, data=True):
                if edata.get("highway") not in {"motorway", "motorway_link"}:
                    continue
                if not edge_compatible_with_direction(G, nid, v, candidate.travel_direction, bearing_tol):
                    continue
                if dist_m > max_connection_distance_m:
                    # Within match radius but beyond preferred connection distance
                    status = "probable"
                else:
                    status = "verified" if token in normalize_token(str(poi["name"])) else "probable"
                proposal = {
                    "lat": lat,
                    "lon": lon,
                    "osm_id": poi["osm_id"],
                    "connected_node_id": nid,
                    "connection_distance_m": round(dist_m, 2),
                    "match_status": status,
                    "requires_manual_review": status != "verified",
                    "evidence": (
                        f"OSM feature osm_id={poi['osm_id']} name='{poi['name']}' "
                        f"matched token '{token}'; connected to directed motorway node {nid} "
                        f"at {dist_m:.1f} m; bearing-compatible with {candidate.travel_direction}"
                    ),
                }
                if best is None or proposal["connection_distance_m"] < best["connection_distance_m"]:
                    best = proposal
                break  # first compatible edge for this node
            if best and best.get("match_status") == "verified" and best["connection_distance_m"] < 100:
                break

    if best is None:
        # Name matched but no direction-compatible connection — do not snap to opposite carriageway
        # Still record coordinates of the OSM feature as location evidence, but mark unresolved for routing link
        poi = hits.iloc[0]
        base["lat"] = float(poi["lat"])
        base["lon"] = float(poi["lon"])
        base["osm_id"] = poi["osm_id"]
        base["match_status"] = "unresolved"
        base["requires_manual_review"] = True
        base["evidence"] = (
            f"OSM name match for '{token}' (osm_id={poi['osm_id']}) but no "
            f"direction-compatible motorway connection for {candidate.travel_direction}; "
            "refusing opposite-carriageway snap"
        )
        return base

    base.update(best)
    return base


def build_candidate_sites(
    config: dict[str, Any],
    G: nx.DiGraph,
    pbf_path: Path,
    bbox: list[float],
    adm_html_cache: Path | None = None,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    sa = config["service_areas"]
    url = sa["source_url"]
    meta: dict[str, Any] = {"adm_url": url, "adm_trafic": probe_adm_trafic()}

    if adm_html_cache and adm_html_cache.exists():
        html = adm_html_cache.read_text(encoding="utf-8")
        meta["adm_html_source"] = str(adm_html_cache)
    else:
        html = fetch_adm_directory(url)
        if adm_html_cache:
            adm_html_cache.parent.mkdir(parents=True, exist_ok=True)
            adm_html_cache.write_text(html, encoding="utf-8")
            meta["adm_html_source"] = str(adm_html_cache)

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
    df = pd.DataFrame(rows)
    # Ensure nulls stay empty for unresolved coords when truly missing
    return df, meta


def write_candidate_sites(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False)
    logger.info("Wrote %s (%d candidates)", path, len(df))
