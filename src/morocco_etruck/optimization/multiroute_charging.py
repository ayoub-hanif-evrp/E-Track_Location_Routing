"""Geographically grounded multiroute charging candidates (Task 05C)."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Literal, Sequence

import pandas as pd

from morocco_etruck.optimization.problem import StationData
from morocco_etruck.optimization.route_choice_graph import DecisionArc, make_arc_id
from morocco_etruck.road_network import geodesic_length_m

_ARTIFICIAL_MIDPOINT_RE = re.compile(r"^R\d+_")

AccessClass = Literal["topology_verified", "hypothetical", "unresolved"]


@dataclass(frozen=True)
class GroundedCharger:
    key: str
    node: str  # decision-graph node name
    osm_node_id: int
    official_name: str
    osm_id: str
    lat: float
    lon: float
    snap_distance_m: float
    hgv_status: str
    travel_direction: str
    access_class: AccessClass = "topology_verified"
    hypothetical_access: bool = True
    reason: str = ""


@dataclass
class ChargerSelectionResult:
    verified: list[GroundedCharger] = field(default_factory=list)
    hypothetical: list[GroundedCharger] = field(default_factory=list)
    unresolved: list[GroundedCharger] = field(default_factory=list)

    @property
    def attachable(self) -> list[GroundedCharger]:
        """Stations that may enter the fixed decision graph."""
        return list(self.verified) + list(self.hypothetical)


class ArtificialMidpointRejected(ValueError):
    """Raised when a Task 05A R{{i}} midpoint charger is proposed."""


def reject_artificial_midpoint_keys(keys: Sequence[str]) -> None:
    bad = [k for k in keys if _ARTIFICIAL_MIDPOINT_RE.match(str(k))]
    if bad:
        raise ArtificialMidpointRejected(
            f"Artificial midpoint charger keys are not allowed in Task 05B/05C: {bad}"
        )


def match_travel_direction(travel: str, wanted: str) -> bool:
    """Normalize ADM travel_direction strings (arrows / spacing) before equality."""
    a = travel.replace(" ", "").lower()
    b = wanted.replace(" ", "").lower()
    for ch in ("→", "-->", "->", "—", "–"):
        a = a.replace(ch, ">")
        b = b.replace(ch, ">")
    return a == b


def select_grounded_chargers_on_union(
    sites: pd.DataFrame,
    *,
    union_osm_nodes: set[int],
    decision_nodes: dict[str, Any],
    station_specs: list[dict[str, Any]],
    G,
    max_snap_m: float = 2500.0,
    allow_proximity_snap: bool = False,
) -> ChargerSelectionResult:
    """
    Attach entrance_and_exit ADM candidates that are direction-compatible with the OD.

    Baseline scientific topology (allow_proximity_snap=False):
      only exact ``connected_node_id ∈ union`` → topology_verified.
      Wrong-carriageway / missing attach → unresolved (never proximity snap).

    Optional hypothetical mode (allow_proximity_snap=True):
      documented proximity snap → hypothetical (not physically certified access).
    """
    reject_artificial_midpoint_keys([str(s.get("key", "")) for s in station_specs])
    osm_to_name = {int(v): str(k) for k, v in decision_nodes.items()}
    result = ChargerSelectionResult()
    used_keys: set[str] = set()

    for spec in station_specs:
        key = str(spec["key"])
        if key in used_keys:
            continue
        if _ARTIFICIAL_MIDPOINT_RE.match(key):
            raise ArtificialMidpointRejected(key)
        if "travel_direction" not in spec or not str(spec.get("travel_direction") or "").strip():
            result.unresolved.append(
                GroundedCharger(
                    key=key,
                    node=key,
                    osm_node_id=-1,
                    official_name="",
                    osm_id=str(spec.get("osm_id") or ""),
                    lat=0.0,
                    lon=0.0,
                    snap_distance_m=0.0,
                    hgv_status="unknown",
                    travel_direction="",
                    access_class="unresolved",
                    reason="missing_travel_direction_in_spec",
                )
            )
            used_keys.add(key)
            continue

        token = str(spec.get("name_contains") or key).upper()
        wanted_dir = str(spec["travel_direction"])
        wanted_osm = str(spec["osm_id"]) if spec.get("osm_id") not in (None, "") else ""

        hits = sites[
            sites["official_name"].astype(str).str.upper().str.contains(token, regex=False)
            & (sites["directed_access_status"].astype(str) == "entrance_and_exit")
        ]
        direction_hits: list[pd.Series] = []
        for _, row in hits.iterrows():
            if not match_travel_direction(str(row.get("travel_direction") or ""), wanted_dir):
                continue
            if wanted_osm:
                row_osm = str(int(row["osm_id"])) if pd.notna(row.get("osm_id")) else ""
                if row_osm != wanted_osm:
                    continue
            direction_hits.append(row)

        if not direction_hits:
            result.unresolved.append(
                GroundedCharger(
                    key=key,
                    node=key,
                    osm_node_id=-1,
                    official_name="",
                    osm_id=wanted_osm,
                    lat=0.0,
                    lon=0.0,
                    snap_distance_m=0.0,
                    hgv_status="unknown",
                    travel_direction=wanted_dir,
                    access_class="unresolved",
                    reason="no_direction_compatible_adm_row",
                )
            )
            used_keys.add(key)
            continue

        # Prefer exact on-union connected_node_id
        on_union: list[tuple[pd.Series, int, float]] = []
        for row in direction_hits:
            if pd.isna(row.get("connected_node_id")):
                continue
            cid = int(row["connected_node_id"])
            if cid in union_osm_nodes:
                snap = float(row.get("connection_distance_m") or 0.0)
                on_union.append((row, cid, snap))

        chosen: GroundedCharger | None = None
        if len(on_union) == 1:
            row, cid, snap = on_union[0]
            node_name = osm_to_name.get(cid, key)
            chosen = GroundedCharger(
                key=key,
                node=node_name,
                osm_node_id=cid,
                official_name=str(row["official_name"]),
                osm_id=str(int(row["osm_id"])) if pd.notna(row.get("osm_id")) else wanted_osm,
                lat=float(row["lat"]),
                lon=float(row["lon"]),
                snap_distance_m=snap,
                hgv_status=str(row.get("hgv_access_status") or "unknown"),
                travel_direction=str(row.get("travel_direction") or wanted_dir),
                access_class="topology_verified",
                hypothetical_access=True,
                reason="connected_node_on_union",
            )
        elif len(on_union) > 1:
            # Ambiguous: multiple on-union attaches for same site/direction
            result.unresolved.append(
                GroundedCharger(
                    key=key,
                    node=key,
                    osm_node_id=-1,
                    official_name=str(on_union[0][0]["official_name"]),
                    osm_id=wanted_osm
                    or (
                        str(int(on_union[0][0]["osm_id"]))
                        if pd.notna(on_union[0][0].get("osm_id"))
                        else ""
                    ),
                    lat=float(on_union[0][0]["lat"]),
                    lon=float(on_union[0][0]["lon"]),
                    snap_distance_m=0.0,
                    hgv_status=str(on_union[0][0].get("hgv_access_status") or "unknown"),
                    travel_direction=wanted_dir,
                    access_class="unresolved",
                    reason="ambiguous_on_union_attach",
                )
            )
            used_keys.add(key)
            continue
        elif allow_proximity_snap:
            # Documented hypothetical connector only — never baseline-certified
            best_row, best_nid, best_d = None, None, float("inf")
            for row in direction_hits:
                for nid in union_osm_nodes:
                    if nid not in G.nodes:
                        continue
                    d = geodesic_length_m(
                        [
                            (float(row["lon"]), float(row["lat"])),
                            (float(G.nodes[nid]["lon"]), float(G.nodes[nid]["lat"])),
                        ]
                    )
                    if d < best_d:
                        best_d, best_nid, best_row = d, nid, row
            if best_row is not None and best_nid is not None and best_d <= max_snap_m:
                node_name = osm_to_name.get(int(best_nid), key)
                chosen = GroundedCharger(
                    key=key,
                    node=node_name,
                    osm_node_id=int(best_nid),
                    official_name=str(best_row["official_name"]),
                    osm_id=str(int(best_row["osm_id"]))
                    if pd.notna(best_row.get("osm_id"))
                    else wanted_osm,
                    lat=float(best_row["lat"]),
                    lon=float(best_row["lon"]),
                    snap_distance_m=float(best_d),
                    hgv_status=str(best_row.get("hgv_access_status") or "unknown"),
                    travel_direction=str(best_row.get("travel_direction") or wanted_dir),
                    access_class="hypothetical",
                    hypothetical_access=True,
                    reason=f"proximity_snap_{best_d:.1f}m_not_physically_certified",
                )
            else:
                result.unresolved.append(
                    GroundedCharger(
                        key=key,
                        node=key,
                        osm_node_id=-1,
                        official_name=str(direction_hits[0]["official_name"]),
                        osm_id=wanted_osm
                        or (
                            str(int(direction_hits[0]["osm_id"]))
                            if pd.notna(direction_hits[0].get("osm_id"))
                            else ""
                        ),
                        lat=float(direction_hits[0]["lat"]),
                        lon=float(direction_hits[0]["lon"]),
                        snap_distance_m=0.0,
                        hgv_status=str(direction_hits[0].get("hgv_access_status") or "unknown"),
                        travel_direction=wanted_dir,
                        access_class="unresolved",
                        reason="snap_exceeded_or_no_union_node",
                    )
                )
                used_keys.add(key)
                continue
        else:
            # Wrong carriageway or attach not on this OD union — leave unresolved
            row0 = direction_hits[0]
            cid0 = (
                int(row0["connected_node_id"])
                if pd.notna(row0.get("connected_node_id"))
                else -1
            )
            result.unresolved.append(
                GroundedCharger(
                    key=key,
                    node=key,
                    osm_node_id=cid0,
                    official_name=str(row0["official_name"]),
                    osm_id=str(int(row0["osm_id"])) if pd.notna(row0.get("osm_id")) else wanted_osm,
                    lat=float(row0["lat"]),
                    lon=float(row0["lon"]),
                    snap_distance_m=float(row0.get("connection_distance_m") or 0.0),
                    hgv_status=str(row0.get("hgv_access_status") or "unknown"),
                    travel_direction=str(row0.get("travel_direction") or wanted_dir),
                    access_class="unresolved",
                    reason="connected_node_not_on_union_no_snap",
                )
            )
            used_keys.add(key)
            continue

        if chosen is not None:
            used_keys.add(key)
            if chosen.access_class == "topology_verified":
                result.verified.append(chosen)
            elif chosen.access_class == "hypothetical":
                result.hypothetical.append(chosen)
            else:
                result.unresolved.append(chosen)
    return result


# Back-compat wrapper used by older call sites expecting a flat list
def select_grounded_chargers_on_union_list(
    *args: Any,
    include_hypothetical: bool = False,
    **kwargs: Any,
) -> list[GroundedCharger]:
    res = select_grounded_chargers_on_union(*args, **kwargs)
    if include_hypothetical:
        return res.attachable
    return list(res.verified)


def to_station_data(
    chargers: Sequence[GroundedCharger],
    *,
    power_kw: float,
    eta: float,
    price_cents: int,
) -> dict[str, StationData]:
    reject_artificial_midpoint_keys([c.key for c in chargers])
    return {
        c.key: StationData(
            node=c.key,
            power_kw=power_kw,
            eta=eta,
            price_cents_per_grid_kwh=price_cents,
            compatible=True,
            official_name=c.official_name,
            hypothetical_access=True,
            hgv_status=c.hgv_status,
            osm_id=c.osm_id,
            snap_distance_m=c.snap_distance_m,
        )
        for c in chargers
    }


def _edge_length_m(G, a: Any, b: Any) -> float | None:
    """Best-effort directed edge length for DiGraph or MultiDiGraph."""
    if G is None or not G.has_edge(a, b):
        return None
    data = G.get_edge_data(a, b)
    if data is None:
        return None
    # MultiDiGraph: data is {key: attr_dict}
    if data and all(isinstance(v, dict) for v in data.values()):
        lengths = [float(v.get("length_m") or 0.0) for v in data.values()]
        return min(lengths) if lengths else 0.0
    return float(data.get("length_m") or 0.0)


def _child_s0_m(parent: DecisionArc, split_index: int, G=None) -> float:
    """Cumulative road distance from parent start to path_nodes[split_index]."""
    if G is not None and split_index > 0:
        s = float(parent.macro_s0_m)
        for a, b in zip(parent.path_nodes[:split_index], parent.path_nodes[1 : split_index + 1]):
            L = _edge_length_m(G, a, b)
            if L is None:
                nseg = max(len(parent.path_nodes) - 1, 1)
                s += float(parent.length_m) / nseg
            else:
                s += L
        return s
    nseg = max(len(parent.path_nodes) - 1, 1)
    return float(parent.macro_s0_m) + float(parent.length_m) * (split_index / nseg)


def _subpath_length_m(path_nodes: list[Any], G=None, fallback_length: float = 0.0) -> float:
    if G is None or len(path_nodes) < 2:
        return float(fallback_length)
    total = 0.0
    for a, b in zip(path_nodes[:-1], path_nodes[1:]):
        L = _edge_length_m(G, a, b)
        if L is None:
            return float(fallback_length)
        total += L
    return total


def split_arcs_at_charger_nodes(
    arcs: list[DecisionArc],
    *,
    chargers: Sequence[GroundedCharger],
    decision_nodes: dict[str, Any],
    G=None,
) -> tuple[list[DecisionArc], dict[str, Any], dict[str, str]]:
    """
    Insert charger keys as decision nodes and split macros that contain their OSM ids.

    Child arcs inherit ``parent_arc_id`` (root pre-split id) and ``macro_s0_m`` for DEM slicing.
    Station MRLS node name = charger.key (aligned with StationData.node).
    """
    nodes = dict(decision_nodes)
    key_by_osm: dict[int, str] = {int(c.osm_node_id): c.key for c in chargers}
    rename: dict[str, str] = {}
    for name, nid in list(nodes.items()):
        if int(nid) in key_by_osm and name != key_by_osm[int(nid)]:
            rename[name] = key_by_osm[int(nid)]
    for c in chargers:
        nodes[c.key] = int(c.osm_node_id)

    if not key_by_osm:
        return arcs, nodes, {}

    def _label(nid: int, default: str) -> str:
        return key_by_osm.get(int(nid), rename.get(default, default))

    new_arcs: list[DecisionArc] = []
    seen: set[str] = set()
    for arc in arcs:
        u0 = rename.get(arc.u, arc.u)
        v0 = rename.get(arc.v, arc.v)
        root_id = arc.parent_arc_id or arc.arc_id or make_arc_id(arc.osm_edge_pairs)
        splits = [i for i, nid in enumerate(arc.path_nodes) if int(nid) in key_by_osm]
        splits = [i for i in splits if 0 < i < len(arc.path_nodes) - 1]
        if not splits:
            aid = arc.arc_id or make_arc_id(arc.osm_edge_pairs)
            if aid not in seen:
                new_arcs.append(
                    DecisionArc(
                        u=u0,
                        v=v0,
                        path_nodes=list(arc.path_nodes),
                        osm_edge_pairs=list(arc.osm_edge_pairs),
                        length_m=arc.length_m,
                        highway_classes=list(arc.highway_classes),
                        scenario_speed_kmh=arc.scenario_speed_kmh,
                        hgv_access=arc.hgv_access,
                        provenance_od_ids=list(arc.provenance_od_ids),
                        arc_id=aid,
                        parent_arc_id=arc.parent_arc_id,
                        macro_s0_m=float(arc.macro_s0_m),
                    )
                )
                seen.add(aid)
            continue
        idxs = [0] + splits + [len(arc.path_nodes) - 1]
        for a, b in zip(idxs[:-1], idxs[1:]):
            if a == b:
                continue
            sub_nodes = arc.path_nodes[a : b + 1]
            if len(sub_nodes) < 2:
                continue
            pairs = list(zip(sub_nodes[:-1], sub_nodes[1:]))
            u_nid, v_nid = int(sub_nodes[0]), int(sub_nodes[-1])
            u_name = _label(u_nid, u0 if a == 0 else f"J{u_nid}")
            v_name = _label(v_nid, v0 if b == len(arc.path_nodes) - 1 else f"J{v_nid}")
            if a == 0:
                u_name = _label(u_nid, u0)
            if b == len(arc.path_nodes) - 1:
                v_name = _label(v_nid, v0)
            aid = make_arc_id(pairs)
            if aid in seen or u_name == v_name:
                continue
            nseg = max(len(arc.path_nodes) - 1, 1)
            frac = (len(sub_nodes) - 1) / nseg
            length_m = _subpath_length_m(
                sub_nodes, G=G, fallback_length=float(arc.length_m) * frac
            )
            child_s0 = _child_s0_m(arc, a, G=G)
            new_arcs.append(
                DecisionArc(
                    u=u_name,
                    v=v_name,
                    path_nodes=list(sub_nodes),
                    osm_edge_pairs=list(pairs),
                    length_m=length_m,
                    highway_classes=list(arc.highway_classes),
                    scenario_speed_kmh=arc.scenario_speed_kmh,
                    hgv_access=arc.hgv_access,
                    provenance_od_ids=list(arc.provenance_od_ids),
                    arc_id=aid,
                    parent_arc_id=root_id,
                    macro_s0_m=child_s0,
                )
            )
            seen.add(aid)
            nodes.setdefault(u_name, u_nid)
            nodes.setdefault(v_name, v_nid)

    station_node_alias = {c.key: c.key for c in chargers}
    return new_arcs, nodes, station_node_alias
