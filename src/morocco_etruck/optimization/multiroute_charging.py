"""Geographically grounded multiroute charging candidates (Task 05B)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Sequence

import pandas as pd

from morocco_etruck.optimization.problem import StationData
from morocco_etruck.optimization.route_choice_graph import DecisionArc, make_arc_id
from morocco_etruck.road_network import geodesic_length_m

_ARTIFICIAL_MIDPOINT_RE = re.compile(r"^R\d+_")


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
    hypothetical_access: bool = True


class ArtificialMidpointRejected(ValueError):
    """Raised when a Task 05A R{{i}} midpoint charger is proposed."""


def reject_artificial_midpoint_keys(keys: Sequence[str]) -> None:
    bad = [k for k in keys if _ARTIFICIAL_MIDPOINT_RE.match(str(k))]
    if bad:
        raise ArtificialMidpointRejected(
            f"Artificial midpoint charger keys are not allowed in Task 05B: {bad}"
        )


def select_grounded_chargers_on_union(
    sites: pd.DataFrame,
    *,
    union_osm_nodes: set[int],
    decision_nodes: dict[str, Any],
    station_specs: list[dict[str, Any]],
    G,
    max_snap_m: float = 2500.0,
) -> list[GroundedCharger]:
    """
    Attach entrance_and_exit ADM candidates whose carriageway node lies on the
    OD path-union (or snaps within max_snap_m to a union node).

    Does not invent midpoints. Unmatched / opposite-carriageway sites are skipped.
    """
    reject_artificial_midpoint_keys([str(s.get("key", "")) for s in station_specs])
    osm_to_name = {int(v): str(k) for k, v in decision_nodes.items()}
    out: list[GroundedCharger] = []
    used_keys: set[str] = set()

    for spec in station_specs:
        key = str(spec["key"])
        if key in used_keys:
            continue
        if _ARTIFICIAL_MIDPOINT_RE.match(key):
            raise ArtificialMidpointRejected(key)
        token = str(spec.get("name_contains") or key).upper()
        hits = sites[
            sites["official_name"].astype(str).str.upper().str.contains(token, regex=False)
            & (sites["directed_access_status"].astype(str) == "entrance_and_exit")
        ]
        chosen: GroundedCharger | None = None
        for _, row in hits.iterrows():
            if pd.isna(row.get("connected_node_id")):
                continue
            cid = int(row["connected_node_id"])
            snap = float(row.get("connection_distance_m") or 0.0)
            if cid not in union_osm_nodes:
                # Snap to nearest union decision node (documented uncertainty)
                best_nid, best_d = None, float("inf")
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
                        best_d, best_nid = d, nid
                if best_nid is None or best_d > max_snap_m:
                    continue
                cid = int(best_nid)
                snap = float(best_d)
            # Ensure a decision-node label exists for this OSM id
            if cid in osm_to_name:
                node_name = osm_to_name[cid]
            else:
                node_name = key
                osm_to_name[cid] = node_name
            chosen = GroundedCharger(
                key=key,
                node=node_name,
                osm_node_id=cid,
                official_name=str(row["official_name"]),
                osm_id=str(int(row["osm_id"])) if pd.notna(row.get("osm_id")) else "",
                lat=float(row["lat"]),
                lon=float(row["lon"]),
                snap_distance_m=snap,
                hgv_status=str(row.get("hgv_access_status") or "unknown"),
                travel_direction=str(row.get("travel_direction") or ""),
                hypothetical_access=True,
            )
            break
        if chosen is not None:
            used_keys.add(key)
            out.append(chosen)
    return out


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


def split_arcs_at_charger_nodes(
    arcs: list[DecisionArc],
    *,
    chargers: Sequence[GroundedCharger],
    decision_nodes: dict[str, Any],
) -> tuple[list[DecisionArc], dict[str, Any], dict[str, str]]:
    """
    Insert charger keys as decision nodes and split macros that contain their OSM ids.

    Station MRLS node name = charger.key (aligned with StationData.node).
    Existing labels for the same OSM id are remapped to the charger key.
    """
    nodes = dict(decision_nodes)
    key_by_osm: dict[int, str] = {int(c.osm_node_id): c.key for c in chargers}
    # Remap any existing decision label that points at a charger OSM id → charger key
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
            frac = (len(sub_nodes) - 1) / max(len(arc.path_nodes) - 1, 1)
            new_arcs.append(
                DecisionArc(
                    u=u_name,
                    v=v_name,
                    path_nodes=list(sub_nodes),
                    osm_edge_pairs=list(pairs),
                    length_m=float(arc.length_m) * frac,
                    highway_classes=list(arc.highway_classes),
                    scenario_speed_kmh=arc.scenario_speed_kmh,
                    hgv_access=arc.hgv_access,
                    provenance_od_ids=list(arc.provenance_od_ids),
                    arc_id=aid,
                )
            )
            seen.add(aid)
            nodes.setdefault(u_name, u_nid)
            nodes.setdefault(v_name, v_nid)

    station_node_alias = {c.key: c.key for c in chargers}
    return new_arcs, nodes, station_node_alias
