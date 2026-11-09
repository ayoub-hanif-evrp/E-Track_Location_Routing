"""Route-choice path discovery and junction/macro contraction (Task 05A/05B)."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any, Iterable, Sequence

import networkx as nx

from morocco_etruck.baseline_routing import nearest_node
from morocco_etruck.road_network import geodesic_length_m

_CITY_NAMES = frozenset({"casablanca", "marrakech", "agadir", "settat"})


@dataclass
class PathRecord:
    od_id: str
    node_path: list[Any]
    length_m: float
    edge_keys: list[tuple[Any, Any, Any]]
    method: str
    jaccard_distance_vs_shortest: float = 0.0


@dataclass
class DecisionArc:
    """Contracted macro between decision nodes (may bundle many OSM edges)."""

    u: str
    v: str
    path_nodes: list[Any]
    osm_edge_pairs: list[tuple[Any, Any]]
    length_m: float
    highway_classes: list[str] = field(default_factory=list)
    maxspeed_kmh: float | None = None
    scenario_speed_kmh: float = 50.0
    hgv_access: str = "unknown"
    provenance_od_ids: list[str] = field(default_factory=list)
    arc_id: str = ""


@dataclass
class RouteChoiceGraph:
    """Branching decision graph for MRLS (exact only over selected path union)."""

    decision_nodes: dict[str, Any]  # name -> osm node id or synthetic
    arcs: list[DecisionArc]
    path_records: list[PathRecord]
    notes: list[str] = field(default_factory=list)
    # alias label -> canonical decision-node name (one OSM id → one name)
    alias_to_canonical: dict[str, str] = field(default_factory=dict)
    # od_id -> {origin, destination} canonical decision-node names
    od_terminals: dict[str, dict[str, str]] = field(default_factory=dict)


def make_arc_id(osm_edge_pairs: Sequence[tuple[Any, Any]]) -> str:
    """Stable identity for a directed OSM micro-edge sequence (parallel-safe)."""
    blob = "|".join(f"{u}->{v}" for u, v in osm_edge_pairs)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


def _terminal_name_priority(name: str) -> tuple[int, str]:
    if name in _CITY_NAMES:
        return (0, name)
    if name.endswith("__o") or name.endswith("__d"):
        return (2, name)
    return (1, name)


def canonicalize_terminals(
    terminals: dict[str, Any],
) -> tuple[dict[str, Any], dict[Any, str], dict[str, str]]:
    """
    One canonical label per OSM node id.

    Prefer city names over per-OD ``{od}__o/__d`` aliases so spur macros are not
    duplicated under multiple endpoint labels.
    """
    by_osm: dict[Any, list[str]] = {}
    for name, nid in terminals.items():
        by_osm.setdefault(nid, []).append(str(name))

    decision_nodes: dict[str, Any] = {}
    rev: dict[Any, str] = {}
    alias_map: dict[str, str] = {}
    for nid, names in by_osm.items():
        canon = sorted(names, key=_terminal_name_priority)[0]
        decision_nodes[canon] = nid
        rev[nid] = canon
        for n in names:
            alias_map[n] = canon
    return decision_nodes, rev, alias_map


def verify_arc_length(
    union_G: nx.DiGraph,
    arc: DecisionArc,
    *,
    rel_tol: float = 0.02,
    abs_tol_m: float = 25.0,
) -> tuple[bool, float, float]:
    """Compare DecisionArc.length_m to sum of underlying OSM edge lengths."""
    summed = 0.0
    for u, v in arc.osm_edge_pairs:
        if not union_G.has_edge(u, v):
            return False, summed, float(arc.length_m)
        summed += float(union_G.edges[u, v].get("length_m") or 0.0)
    ok = abs(summed - float(arc.length_m)) <= max(abs_tol_m, rel_tol * max(summed, 1.0))
    return ok, summed, float(arc.length_m)


def _as_weighted_digraph(G: nx.Graph) -> nx.DiGraph:
    if not G.is_multigraph():
        H = nx.DiGraph(G)
        return H
    H = nx.DiGraph()
    for n, data in G.nodes(data=True):
        H.add_node(n, **data)
    for u, v, k, data in G.edges(keys=True, data=True):
        length = float(data.get("length_m") or 0.0)
        if H.has_edge(u, v):
            if length < float(H.edges[u, v].get("length_m") or 0.0):
                H.edges[u, v].clear()
                H.edges[u, v].update(data)
                H.edges[u, v]["edge_key"] = k
        else:
            H.add_edge(u, v, **data, edge_key=k)
    return H


def path_length_m(G: nx.DiGraph, path: Sequence[Any]) -> float:
    total = 0.0
    for u, v in zip(path[:-1], path[1:]):
        total += float(G.edges[u, v].get("length_m") or 0.0)
    return total


def path_edge_set(path: Sequence[Any]) -> set[tuple[Any, Any]]:
    return {(u, v) for u, v in zip(path[:-1], path[1:])}


def jaccard_distance(a: set, b: set) -> float:
    if not a and not b:
        return 0.0
    inter = len(a & b)
    union = len(a | b)
    return 1.0 - (inter / union if union else 0.0)


def shortest_path_record(
    G: nx.DiGraph, origin: Any, destination: Any, *, od_id: str
) -> PathRecord:
    path = nx.shortest_path(G, origin, destination, weight="length_m")
    edges = [(u, v, G.edges[u, v].get("edge_key", 0)) for u, v in zip(path[:-1], path[1:])]
    return PathRecord(
        od_id=od_id,
        node_path=list(path),
        length_m=path_length_m(G, path),
        edge_keys=edges,
        method="shortest_distance",
        jaccard_distance_vs_shortest=0.0,
    )


def diverse_paths(
    G: nx.Graph,
    origin: Any,
    destination: Any,
    *,
    od_id: str,
    max_alternatives: int = 4,
    min_jaccard_distance: float = 0.25,
    min_length_ratio: float = 1.05,
    penalty_factor: float = 3.0,
    max_penalty_rounds: int = 8,
) -> list[PathRecord]:
    """
    Shortest path + iterative edge-penalty alternatives.

    Does not invent edges; only returns directed paths present in G.
    """
    H = _as_weighted_digraph(G)
    if origin not in H or destination not in H:
        return []
    if not nx.has_path(H, origin, destination):
        return []

    records: list[PathRecord] = []
    try:
        shortest = shortest_path_record(H, origin, destination, od_id=od_id)
    except (nx.NetworkXNoPath, nx.NodeNotFound):
        return []
    records.append(shortest)
    short_edges = path_edge_set(shortest.node_path)
    short_len = shortest.length_m

    # Working copy for penalties
    W = H.copy()
    for _ in range(max_penalty_rounds):
        if len(records) >= max_alternatives:
            break
        # Penalize edges of all accepted paths
        for rec in records:
            for u, v in path_edge_set(rec.node_path):
                if W.has_edge(u, v):
                    W.edges[u, v]["length_m"] = float(W.edges[u, v]["length_m"]) * penalty_factor
        try:
            path = nx.shortest_path(W, origin, destination, weight="length_m")
        except (nx.NetworkXNoPath, nx.NodeNotFound):
            break
        # Measure true length on unpenalized graph
        true_len = path_length_m(H, path)
        edges = path_edge_set(path)
        jd = jaccard_distance(edges, short_edges)
        # Also require diversity vs all accepted
        ok_vs_all = all(
            jaccard_distance(edges, path_edge_set(r.node_path)) >= min_jaccard_distance * 0.5
            for r in records
        )
        if jd >= min_jaccard_distance or true_len >= short_len * min_length_ratio:
            if ok_vs_all and path not in [r.node_path for r in records]:
                records.append(
                    PathRecord(
                        od_id=od_id,
                        node_path=list(path),
                        length_m=true_len,
                        edge_keys=[
                            (u, v, H.edges[u, v].get("edge_key", 0))
                            for u, v in zip(path[:-1], path[1:])
                        ],
                        method="edge_penalty",
                        jaccard_distance_vs_shortest=jd,
                    )
                )
        # Prevent infinite identical path
        if path == shortest.node_path and len(records) == 1:
            # Force exclude one edge from shortest and retry once more structure
            if len(shortest.node_path) < 3:
                break
            mid_u, mid_v = shortest.node_path[len(shortest.node_path) // 2 - 1], shortest.node_path[
                len(shortest.node_path) // 2
            ]
            if W.has_edge(mid_u, mid_v):
                W.remove_edge(mid_u, mid_v)
            continue
        if len(records) >= max_alternatives:
            break
    return records


def snap_anchors(
    G: nx.Graph, anchors: dict[str, dict[str, Any]], *, search_radius_m: float
) -> dict[str, int]:
    out: dict[str, int] = {}
    for name, a in anchors.items():
        if name == "search_radius_m":
            continue
        if not isinstance(a, dict) or "lon" not in a:
            continue
        out[name] = nearest_node(G, float(a["lon"]), float(a["lat"]), search_radius_m)
    return out


def snap_od_pair(
    G: nx.Graph,
    *,
    origin_lon: float,
    origin_lat: float,
    dest_lon: float,
    dest_lat: float,
    search_radius_m: float,
    candidate_k: int = 12,
) -> tuple[Any, Any] | None:
    """
    Snap OD to nearby nodes that admit a directed path origin→destination.
    Tries nearest-k pairs by geodesic distance sum.
    """
    H = _as_weighted_digraph(G)

    def nearest_k(lon: float, lat: float, k: int) -> list[tuple[float, Any]]:
        scored = []
        for nid, data in H.nodes(data=True):
            d = geodesic_length_m([(lon, lat), (float(data["lon"]), float(data["lat"]))])
            if d <= search_radius_m:
                scored.append((d, nid))
        scored.sort()
        return scored[:k]

    origins = nearest_k(origin_lon, origin_lat, candidate_k)
    dests = nearest_k(dest_lon, dest_lat, candidate_k)
    if not origins or not dests:
        return None
    best = None
    best_score = float("inf")
    for do, o in origins:
        for dd, d in dests:
            if o == d:
                continue
            if nx.has_path(H, o, d):
                score = do + dd
                if score < best_score:
                    best_score = score
                    best = (o, d)
    return best


def union_path_digraph(G: nx.Graph, paths: Iterable[Sequence[Any]]) -> nx.DiGraph:
    """Directed union of node sequences using attributes from G."""
    H = _as_weighted_digraph(G)
    U = nx.DiGraph()
    for path in paths:
        for n in path:
            if n not in U:
                U.add_node(n, **H.nodes[n])
        for u, v in zip(path[:-1], path[1:]):
            if not U.has_edge(u, v) and H.has_edge(u, v):
                U.add_edge(u, v, **H.edges[u, v])
    return U


def _scenario_speed_kmh(data: dict[str, Any], speed_policy: dict[str, Any]) -> float:
    defaults = speed_policy.get("class_defaults_kmh") or {}
    highway = str(data.get("highway") or "default")
    default_v = float(defaults.get(highway, defaults.get("default", 50)))
    if not speed_policy.get("use_osm_maxspeed", True):
        return default_v
    raw = data.get("maxspeed_kmh")
    try:
        v = float(raw) if raw not in (None, "") else None
    except (TypeError, ValueError):
        v = None
    lo = float(speed_policy.get("maxspeed_sane_min_kmh", 30))
    hi = float(speed_policy.get("maxspeed_sane_max_kmh", 120))
    if v is not None and lo <= v <= hi:
        return v
    return default_v


def contract_to_decision_graph(
    union_G: nx.DiGraph,
    *,
    terminals: dict[str, Any],
    path_records: list[PathRecord],
    speed_policy: dict[str, Any],
    od_pairs: list[dict[str, str]] | None = None,
) -> RouteChoiceGraph:
    """
    Contract degree-2 chains; keep terminals and branch/merge junctions.

    Terminals that share an OSM id collapse to one canonical label.
    """
    decision_nodes, rev, alias_map = canonicalize_terminals(terminals)
    terminal_nodes = set(decision_nodes.values())
    branch_nodes = set()
    for n in union_G.nodes():
        indeg = union_G.in_degree(n)
        outdeg = union_G.out_degree(n)
        if n in terminal_nodes or indeg != 1 or outdeg != 1:
            branch_nodes.add(n)
        if outdeg > 1 or indeg > 1:
            branch_nodes.add(n)

    for nid in sorted(branch_nodes, key=lambda x: int(x) if str(x).isdigit() else str(x)):
        if nid in rev:
            continue
        label = f"J{nid}"
        decision_nodes[label] = nid
        rev[nid] = label

    arcs: list[DecisionArc] = []
    seen: set[tuple[str, str, tuple]] = set()

    def walk_from(u_name: str, u_nid: Any) -> None:
        for _, v, data in union_G.out_edges(u_nid, data=True):
            path_nodes = [u_nid, v]
            osm_pairs = [(u_nid, v)]
            length = float(data.get("length_m") or 0.0)
            highways = [str(data.get("highway") or "")]
            speeds = [_scenario_speed_kmh(data, speed_policy)]
            hgv = str(data.get("hgv_access") or "unknown")
            cur = v
            while cur not in branch_nodes:
                outs = list(union_G.out_edges(cur, data=True))
                if len(outs) != 1:
                    break
                _, nxt, d2 = outs[0]
                path_nodes.append(nxt)
                osm_pairs.append((cur, nxt))
                length += float(d2.get("length_m") or 0.0)
                highways.append(str(d2.get("highway") or ""))
                speeds.append(_scenario_speed_kmh(d2, speed_policy))
                if str(d2.get("hgv_access") or "") == "no":
                    hgv = "no"
                elif hgv != "no" and str(d2.get("hgv_access") or "unknown") == "unknown":
                    hgv = "unknown"
                cur = nxt
            if cur not in rev:
                continue
            v_name = rev[cur]
            key = (u_name, v_name, tuple(osm_pairs))
            if key in seen or u_name == v_name:
                continue
            seen.add(key)
            if length > 0 and speeds:
                scen = sum(speeds) / len(speeds)
            else:
                scen = float((speed_policy.get("class_defaults_kmh") or {}).get("default", 50))
            arcs.append(
                DecisionArc(
                    u=u_name,
                    v=v_name,
                    path_nodes=path_nodes,
                    osm_edge_pairs=osm_pairs,
                    length_m=length,
                    highway_classes=sorted({h for h in highways if h}),
                    scenario_speed_kmh=float(scen),
                    hgv_access=hgv,
                    provenance_od_ids=sorted({r.od_id for r in path_records}),
                    arc_id=make_arc_id(osm_pairs),
                )
            )

    # Walk once per unique OSM decision node (not once per alias).
    walked: set[Any] = set()
    for name, nid in list(decision_nodes.items()):
        if nid in union_G and nid not in walked:
            walk_from(name, nid)
            walked.add(nid)

    od_terminals: dict[str, dict[str, str]] = {}
    for od in od_pairs or []:
        od_id = str(od["id"])
        o_raw, d_raw = str(od["origin"]), str(od["destination"])
        od_terminals[od_id] = {
            "origin": alias_map.get(o_raw, o_raw),
            "destination": alias_map.get(d_raw, d_raw),
        }

    notes = [
        "Exact MRLS optimality is only over this selected path-union decision graph.",
        "Stations/chargers remain hypothetical unless independently verified.",
        "Decision nodes are canonicalized to one label per OSM id (Task 05B).",
    ]
    return RouteChoiceGraph(
        decision_nodes=decision_nodes,
        arcs=arcs,
        path_records=path_records,
        notes=notes,
        alias_to_canonical=alias_map,
        od_terminals=od_terminals,
    )


def build_route_choice_for_ods(
    G: nx.Graph,
    *,
    anchors: dict[str, int],
    od_pairs: list[dict[str, str]],
    path_cfg: dict[str, Any],
    speed_policy: dict[str, Any],
) -> RouteChoiceGraph:
    all_records: list[PathRecord] = []
    notes: list[str] = []
    for od in od_pairs:
        od_id = str(od["id"])
        o_name, d_name = str(od["origin"]), str(od["destination"])
        if o_name not in anchors or d_name not in anchors:
            notes.append(f"{od_id}: missing anchor snap")
            continue
        recs = diverse_paths(
            G,
            anchors[o_name],
            anchors[d_name],
            od_id=od_id,
            max_alternatives=int(path_cfg.get("max_alternatives", 4)),
            min_jaccard_distance=float(path_cfg.get("min_jaccard_distance", 0.25)),
            min_length_ratio=float(path_cfg.get("min_length_ratio", 1.05)),
            penalty_factor=float(path_cfg.get("penalty_factor", 3.0)),
            max_penalty_rounds=int(path_cfg.get("max_penalty_rounds", 8)),
        )
        if not recs:
            notes.append(f"{od_id}: no directed path")
        elif len(recs) == 1:
            notes.append(f"{od_id}: single credible route only (no diverse alternative found)")
        else:
            notes.append(f"{od_id}: {len(recs)} routes")
        all_records.extend(recs)

    terminals = {k: v for k, v in anchors.items()}
    union = union_path_digraph(G, [r.node_path for r in all_records])
    rcg = contract_to_decision_graph(
        union,
        terminals=terminals,
        path_records=all_records,
        speed_policy=speed_policy,
        od_pairs=od_pairs,
    )
    rcg.notes.extend(notes)
    return rcg


def classify_path_diversity(
    records: list[PathRecord],
    *,
    substantial_jaccard: float = 0.35,
    minor_length_ratio_max: float = 1.12,
) -> list[dict[str, Any]]:
    """Label alternatives as substantial corridor vs minor detour (audit helper)."""
    by_od: dict[str, list[PathRecord]] = {}
    for r in records:
        by_od.setdefault(r.od_id, []).append(r)
    rows: list[dict[str, Any]] = []
    for od_id, recs in sorted(by_od.items()):
        short = min(recs, key=lambda r: r.length_m)
        for r in recs:
            ratio = float(r.length_m) / max(float(short.length_m), 1.0)
            if r.method == "shortest_distance":
                label = "shortest"
            elif r.jaccard_distance_vs_shortest >= substantial_jaccard:
                label = "substantial"
            elif ratio <= minor_length_ratio_max:
                label = "minor_detour"
            else:
                label = "substantial_length_detour"
            rows.append(
                {
                    "od_id": od_id,
                    "method": r.method,
                    "length_m": r.length_m,
                    "length_ratio_vs_shortest": ratio,
                    "jaccard_distance_vs_shortest": r.jaccard_distance_vs_shortest,
                    "diversity_class": label,
                }
            )
    return rows
