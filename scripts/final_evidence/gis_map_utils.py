#!/usr/bin/env python3
"""Shared GIS helpers for publication-quality final-evidence maps."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

import geopandas as gpd
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from shapely.geometry import LineString, Point, box

ROOT = Path(__file__).resolve().parents[2]
CRS_GEO = "EPSG:4326"
CRS_PLOT = "EPSG:3857"  # metric Web Mercator for scale bars


def edges_to_gdf(
    nodes: pd.DataFrame,
    edges: pd.DataFrame,
    *,
    id_col: str | None = None,
    u_col: str = "u",
    v_col: str = "v",
) -> gpd.GeoDataFrame:
    """Build continuous edge LineStrings (no arbitrary subsampling)."""
    if id_col is None:
        id_col = "osm_node_id" if "osm_node_id" in nodes.columns else "node_id"
    xy = nodes.set_index(id_col)[["lon", "lat"]]
    geoms: list = []
    keep: list = []
    for i, r in edges.iterrows():
        try:
            a = xy.loc[int(r[u_col])]
            b = xy.loc[int(r[v_col])]
        except (KeyError, ValueError, TypeError):
            continue
        geoms.append(LineString([(float(a.lon), float(a.lat)), (float(b.lon), float(b.lat))]))
        keep.append(i)
    g = edges.loc[keep].copy()
    return gpd.GeoDataFrame(g, geometry=geoms, crs=CRS_GEO)


def path_nodes_to_line(nodes: pd.DataFrame, npath: Iterable[int]) -> LineString | None:
    id_col = "osm_node_id" if "osm_node_id" in nodes.columns else "node_id"
    xy = nodes.set_index(id_col)[["lon", "lat"]]
    coords = []
    for nid in npath:
        try:
            r = xy.loc[int(nid)]
        except KeyError:
            continue
        coords.append((float(r.lon), float(r.lat)))
    if len(coords) < 2:
        return None
    return LineString(coords)


def project(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    if gdf.crs is None:
        gdf = gdf.set_crs(CRS_GEO)
    return gdf.to_crs(CRS_PLOT)


def add_scale_bar(ax, length_km: float = 100.0, location=(0.08, 0.06)) -> None:
    """Metric scale bar in projected CRS (meters)."""
    xmin, xmax = ax.get_xlim()
    ymin, ymax = ax.get_ylim()
    x0 = xmin + (xmax - xmin) * location[0]
    y0 = ymin + (ymax - ymin) * location[1]
    length_m = length_km * 1000.0
    ax.plot([x0, x0 + length_m], [y0, y0], color="k", lw=2.2, solid_capstyle="butt", zorder=20)
    ax.plot([x0, x0], [y0 - length_m * 0.015, y0 + length_m * 0.015], color="k", lw=1.5, zorder=20)
    ax.plot(
        [x0 + length_m, x0 + length_m],
        [y0 - length_m * 0.015, y0 + length_m * 0.015],
        color="k",
        lw=1.5,
        zorder=20,
    )
    ax.text(
        x0 + length_m / 2,
        y0 + (ymax - ymin) * 0.012,
        f"{length_km:.0f} km",
        ha="center",
        va="bottom",
        fontsize=8,
        zorder=20,
    )


def add_attribution(ax, extra: str = "") -> None:
    txt = (
        "CRS: EPSG:3857 (plot) / source EPSG:4326. "
        "Road geometry © OpenStreetMap contributors (ODbL). "
        "ADM service-area names: ADM. Chargers are hypothetical research installations."
    )
    if extra:
        txt = txt + " " + extra
    ax.text(
        0.01,
        0.01,
        txt,
        transform=ax.transAxes,
        fontsize=6.0,
        va="bottom",
        ha="left",
        zorder=30,
        bbox=dict(boxstyle="round,pad=0.3", facecolor="white", edgecolor="#cccccc", alpha=0.92),
    )


def study_bounds_gdf() -> gpd.GeoDataFrame:
    # Morocco Atlantic / atlas corridor study extent
    return gpd.GeoDataFrame(geometry=[box(-9.9, 30.1, -1.6, 36.0)], crs=CRS_GEO)


def load_city_anchors() -> gpd.GeoDataFrame:
    anchors = json.loads(
        (ROOT / "data/processed/multiroute/build_manifest.json").read_text(encoding="utf-8")
    )["anchors"]
    nodes = pd.read_csv(ROOT / "data/processed/multiroute/nodes.csv").set_index("osm_node_id")
    rows = []
    for name, key in [
        ("Tangier", "tangier"),
        ("Rabat", "rabat"),
        ("Casablanca", "casablanca"),
        ("Fès", "fes"),
        ("Oujda", "oujda"),
        ("Marrakech", "marrakech"),
        ("Agadir", "agadir"),
    ]:
        nid = int(anchors[key])
        r = nodes.loc[nid]
        rows.append({"name": name, "osm_node_id": nid, "lon": float(r.lon), "lat": float(r.lat)})
    df = pd.DataFrame(rows)
    return gpd.GeoDataFrame(
        df, geometry=[Point(xy) for xy in zip(df.lon, df.lat)], crs=CRS_GEO
    )


def matched_candidates() -> gpd.GeoDataFrame:
    """Only OSM-matched candidates with finite coordinates (verified)."""
    cand = pd.read_csv(ROOT / "results/final_evidence/tables/dataset/D-T04_candidate_inventory.csv")
    cand = cand[cand.location_match_status == "matched_osm"].copy()
    cand = cand[pd.to_numeric(cand.lon, errors="coerce").notna()]
    cand = cand[pd.to_numeric(cand.lat, errors="coerce").notna()]
    return gpd.GeoDataFrame(
        cand,
        geometry=[Point(xy) for xy in zip(cand.lon.astype(float), cand.lat.astype(float))],
        crs=CRS_GEO,
    )


def save_fig(fig, base: Path) -> None:
    base.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(base.with_suffix(".pdf"))
    fig.savefig(base.with_suffix(".png"), dpi=400)
    fig.savefig(base.with_suffix(".svg"))
    plt.close(fig)
    print("Wrote", base)
