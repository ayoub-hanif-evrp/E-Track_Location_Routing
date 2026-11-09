"""Task 05C — direction-specific station attachment (no wrong-carriageway snap)."""

from __future__ import annotations

from pathlib import Path

import networkx as nx
import pandas as pd
import pytest
from shapely.geometry import LineString

from morocco_etruck.optimization.multiroute_charging import (
    match_travel_direction,
    select_grounded_chargers_on_union,
)

ROOT = Path(__file__).resolve().parents[2]
SITES = ROOT / "data/processed/candidate_sites.csv"


def _toy_union_graph(node_ids: list[int], coords: dict[int, tuple[float, float]]) -> nx.DiGraph:
    G = nx.DiGraph()
    for nid, (lon, lat) in coords.items():
        G.add_node(nid, lon=lon, lat=lat)
    for a, b in zip(node_ids[:-1], node_ids[1:]):
        G.add_edge(
            a,
            b,
            length_m=1000.0,
            geometry_wkt=LineString([coords[a], coords[b]]).wkt,
        )
    return G


@pytest.mark.skipif(not SITES.exists(), reason="candidate_sites.csv missing")
def test_match_direction_normalizes_arrows():
    assert match_travel_direction("Casablanca→Agadir", "Casablanca->Agadir")
    assert match_travel_direction("Agadir → Casablanca", "Agadir→Casablanca")
    assert not match_travel_direction("Casablanca→Agadir", "Agadir→Casablanca")


@pytest.mark.skipif(not SITES.exists(), reason="candidate_sites.csv missing")
def test_settat_casa_to_agadir_selects_correct_osm():
    sites = pd.read_csv(SITES)
    # Forward Settat connected node from ADM
    fwd = sites[
        (sites["osm_id"] == 127661106)
        & (sites["directed_access_status"] == "entrance_and_exit")
    ].iloc[0]
    rev = sites[
        (sites["osm_id"] == 127661105)
        & (sites["directed_access_status"] == "entrance_and_exit")
    ].iloc[0]
    cid = int(fwd["connected_node_id"])
    # Place reverse facility nearby so a naive snap would prefer the wrong row
    coords = {
        cid: (float(fwd["lon"]), float(fwd["lat"])),
        int(rev["connected_node_id"]): (float(rev["lon"]), float(rev["lat"])),
        1: (float(fwd["lon"]) - 0.05, float(fwd["lat"])),
        9: (float(fwd["lon"]) + 0.05, float(fwd["lat"])),
    }
    path = [1, cid, 9]
    G = _toy_union_graph(path, coords)
    # Also include reverse node in union to tempt wrong selection without direction filter
    G.add_node(
        int(rev["connected_node_id"]),
        lon=float(rev["lon"]),
        lat=float(rev["lat"]),
    )
    res = select_grounded_chargers_on_union(
        sites,
        union_osm_nodes=set(path),
        decision_nodes={"O": 1, "D": 9, "J": cid},
        station_specs=[
            {
                "key": "settat_ca",
                "name_contains": "SETTAT",
                "travel_direction": "Casablanca→Agadir",
                "osm_id": "127661106",
            }
        ],
        G=G,
        allow_proximity_snap=False,
    )
    assert len(res.verified) == 1
    assert res.verified[0].osm_id == "127661106"
    assert res.verified[0].osm_node_id == cid
    assert res.verified[0].access_class == "topology_verified"


@pytest.mark.skipif(not SITES.exists(), reason="candidate_sites.csv missing")
def test_settat_rejects_wrong_carriageway_without_snap():
    sites = pd.read_csv(SITES)
    fwd = sites[sites["osm_id"] == 127661106].iloc[0]
    # Union only has an unrelated nearby node — not the ADM connected_node_id
    near = 999001
    coords = {
        near: (float(fwd["lon"]), float(fwd["lat"])),
        1: (float(fwd["lon"]) - 0.01, float(fwd["lat"])),
        9: (float(fwd["lon"]) + 0.01, float(fwd["lat"])),
    }
    G = _toy_union_graph([1, near, 9], coords)
    res = select_grounded_chargers_on_union(
        sites,
        union_osm_nodes={1, near, 9},
        decision_nodes={"O": 1, "D": 9},
        station_specs=[
            {
                "key": "settat_ca",
                "name_contains": "SETTAT",
                "travel_direction": "Casablanca→Agadir",
                "osm_id": "127661106",
            }
        ],
        G=G,
        allow_proximity_snap=False,
    )
    assert res.verified == []
    assert res.hypothetical == []
    assert len(res.unresolved) == 1
    assert res.unresolved[0].reason == "connected_node_not_on_union_no_snap"


@pytest.mark.skipif(not SITES.exists(), reason="candidate_sites.csv missing")
def test_benguerir_both_directions():
    sites = pd.read_csv(SITES)
    ca = sites[sites["osm_id"] == 127661099].iloc[0]
    ac = sites[sites["osm_id"] == 127661098].iloc[0]
    cid_ca = int(ca["connected_node_id"])
    cid_ac = int(ac["connected_node_id"])
    coords = {
        cid_ca: (float(ca["lon"]), float(ca["lat"])),
        cid_ac: (float(ac["lon"]), float(ac["lat"])),
        10: (float(ca["lon"]) - 0.02, float(ca["lat"])),
        11: (float(ca["lon"]) + 0.02, float(ca["lat"])),
        20: (float(ac["lon"]) - 0.02, float(ac["lat"])),
        21: (float(ac["lon"]) + 0.02, float(ac["lat"])),
    }
    G = nx.DiGraph()
    for nid, (lon, lat) in coords.items():
        G.add_node(nid, lon=lon, lat=lat)

    res_ca = select_grounded_chargers_on_union(
        sites,
        union_osm_nodes={10, cid_ca, 11},
        decision_nodes={"O": 10, "D": 11},
        station_specs=[
            {
                "key": "benguerir_ca",
                "name_contains": "BENGUERIR",
                "travel_direction": "Casablanca→Agadir",
                "osm_id": "127661099",
            }
        ],
        G=G,
        allow_proximity_snap=False,
    )
    res_ac = select_grounded_chargers_on_union(
        sites,
        union_osm_nodes={20, cid_ac, 21},
        decision_nodes={"O": 20, "D": 21},
        station_specs=[
            {
                "key": "benguerir_ac",
                "name_contains": "BENGUERIR",
                "travel_direction": "Agadir→Casablanca",
                "osm_id": "127661098",
            }
        ],
        G=G,
        allow_proximity_snap=False,
    )
    assert res_ca.verified[0].osm_id == "127661099"
    assert res_ac.verified[0].osm_id == "127661098"
    assert res_ca.verified[0].osm_node_id == cid_ca
    assert res_ac.verified[0].osm_node_id == cid_ac


@pytest.mark.skipif(not SITES.exists(), reason="candidate_sites.csv missing")
def test_missing_travel_direction_is_unresolved():
    sites = pd.read_csv(SITES)
    G = nx.DiGraph()
    G.add_node(1, lon=-8.0, lat=32.0)
    res = select_grounded_chargers_on_union(
        sites,
        union_osm_nodes={1},
        decision_nodes={"O": 1},
        station_specs=[{"key": "settat_ca", "name_contains": "SETTAT"}],
        G=G,
        allow_proximity_snap=False,
    )
    assert res.verified == []
    assert res.unresolved[0].reason == "missing_travel_direction_in_spec"


@pytest.mark.skipif(not SITES.exists(), reason="candidate_sites.csv missing")
def test_proximity_snap_marked_hypothetical_only_when_enabled():
    sites = pd.read_csv(SITES)
    fwd = sites[sites["osm_id"] == 127661106].iloc[0]
    near = 888001
    coords = {
        near: (float(fwd["lon"]), float(fwd["lat"])),
        1: (float(fwd["lon"]) - 0.01, float(fwd["lat"])),
        9: (float(fwd["lon"]) + 0.01, float(fwd["lat"])),
    }
    G = _toy_union_graph([1, near, 9], coords)
    res = select_grounded_chargers_on_union(
        sites,
        union_osm_nodes={1, near, 9},
        decision_nodes={"O": 1, "D": 9},
        station_specs=[
            {
                "key": "settat_ca",
                "name_contains": "SETTAT",
                "travel_direction": "Casablanca→Agadir",
                "osm_id": "127661106",
            }
        ],
        G=G,
        allow_proximity_snap=True,
        max_snap_m=2500.0,
    )
    assert res.verified == []
    assert len(res.hypothetical) == 1
    assert res.hypothetical[0].access_class == "hypothetical"
    assert "not_physically_certified" in res.hypothetical[0].reason
