#!/usr/bin/env python3
"""D-Figure 1 — Geographical study area map from actual OSM-derived geometry."""
from __future__ import annotations

import json
from pathlib import Path

import geopandas as gpd
import matplotlib.pyplot as plt
import pandas as pd
from matplotlib.lines import Line2D
from matplotlib.patches import FancyBboxPatch
from shapely.geometry import LineString, Point

ROOT = Path(__file__).resolve().parents[2]
FIG = ROOT / "results/final_evidence/figures/dataset"
SRC = FIG / "source_data"
C = {
    "motorway": "#0072B2",
    "trunk": "#E69F00",
    "primary": "#CC79A7",
    "city": "#000000",
    "candidate": "#D55E00",
    "land": "#f7f7f7",
}


def _edges_to_gdf(nodes: pd.DataFrame, edges: pd.DataFrame, sample_every: int = 1) -> gpd.GeoDataFrame:
    idc = "osm_node_id" if "osm_node_id" in nodes.columns else "node_id"
    node_xy = nodes.set_index(idc)[["lon", "lat"]]
    # Subsample long tables for plotting speed while keeping corridors
    e = edges.iloc[::sample_every].copy()
    geoms = []
    keep = []
    for i, r in e.iterrows():
        try:
            a = node_xy.loc[int(r.u)]
            b = node_xy.loc[int(r.v)]
        except KeyError:
            continue
        geoms.append(LineString([(float(a.lon), float(a.lat)), (float(b.lon), float(b.lat))]))
        keep.append(i)
    g = e.loc[keep].copy()
    return gpd.GeoDataFrame(g, geometry=geoms, crs="EPSG:4326")


def main() -> None:
    FIG.mkdir(parents=True, exist_ok=True)
    SRC.mkdir(parents=True, exist_ok=True)

    road_nodes = pd.read_csv(ROOT / "data/processed/road_nodes.csv")
    road_edges = pd.read_csv(ROOT / "data/processed/road_edges.csv")
    # Motorway geometry (full) — denser than needed; sample lightly for PNG size
    mw = _edges_to_gdf(road_nodes, road_edges, sample_every=3)

    # Expanded classes for context near Atlantic corridor: sample trunk/primary
    mr_nodes = pd.read_csv(ROOT / "data/processed/multiroute/nodes.csv")
    mr_edges = pd.read_csv(ROOT / "data/processed/multiroute/edges.csv")
    trunk = mr_edges[mr_edges.highway.isin(["trunk", "trunk_link"])]
    primary = mr_edges[mr_edges.highway.isin(["primary", "primary_link"])]
    # Heavy subsample for background
    tr_g = _edges_to_gdf(mr_nodes, trunk, sample_every=40)
    pr_g = _edges_to_gdf(mr_nodes, primary, sample_every=80)

    cand = pd.read_csv(ROOT / "results/final_evidence/tables/dataset/D-T04_candidate_inventory.csv")
    cand = cand[pd.to_numeric(cand["lon"], errors="coerce").notna()]
    cand = cand[pd.to_numeric(cand["lat"], errors="coerce").notna()]
    cand_g = gpd.GeoDataFrame(
        cand,
        geometry=[Point(xy) for xy in zip(cand.lon.astype(float), cand.lat.astype(float))],
        crs="EPSG:4326",
    )
    cand_g = cand_g[~cand_g.geometry.is_empty]

    anchors = json.loads(
        (ROOT / "data/processed/multiroute/build_manifest.json").read_text(encoding="utf-8")
    )["anchors"]
    city_ids = {
        "Tangier": anchors["tangier"],
        "Rabat": anchors["rabat"],
        "Casablanca": anchors["casablanca"],
        "Fès": anchors["fes"],
        "Oujda": anchors["oujda"],
        "Marrakech": anchors["marrakech"],
        "Agadir": anchors["agadir"],
    }
    node_xy = mr_nodes.set_index("osm_node_id")[["lon", "lat"]]
    city_rows = []
    for name, nid in city_ids.items():
        r = node_xy.loc[int(nid)]
        city_rows.append({"name": name, "lon": float(r.lon), "lat": float(r.lat)})
    cities = pd.DataFrame(city_rows)
    cities.to_csv(SRC / "D-Fig1_cities.csv", index=False)
    cand[["official_name", "lon", "lat", "travel_direction", "location_match_status"]].to_csv(
        SRC / "D-Fig1_candidates.csv", index=False
    )

    # Project to Web Mercator for scale bar friendliness, then plot
    fig, ax = plt.subplots(figsize=(9.5, 11), constrained_layout=True)
    fig.patch.set_facecolor("white")
    ax.set_facecolor(C["land"])

    pr_g.plot(ax=ax, color="#dddddd", linewidth=0.15, alpha=0.5, zorder=1)
    tr_g.plot(ax=ax, color=C["trunk"], linewidth=0.35, alpha=0.7, zorder=2)
    mw.plot(ax=ax, color=C["motorway"], linewidth=0.7, alpha=0.95, zorder=3)

    matched = cand_g[cand_g.location_match_status == "matched_osm"]
    unmatched = cand_g[cand_g.location_match_status != "matched_osm"]
    if len(matched):
        ax.scatter(
            matched.geometry.x,
            matched.geometry.y,
            c=C["candidate"],
            s=36,
            marker="^",
            zorder=5,
            label="_nolegend_",
        )
    if len(unmatched):
        ax.scatter(
            unmatched.geometry.x,
            unmatched.geometry.y,
            c="#999999",
            s=28,
            marker="x",
            zorder=4,
            label="_nolegend_",
        )

    for _, r in cities.iterrows():
        ax.scatter(r.lon, r.lat, c=C["city"], s=22, zorder=6)
        ax.annotate(
            r["name"],
            (r.lon, r.lat),
            textcoords="offset points",
            xytext=(4, 4),
            fontsize=8,
            fontweight="bold",
        )

    # Study bbox from manifest
    ax.set_xlim(-9.9, -1.6)
    ax.set_ylim(30.1, 36.0)
    ax.set_xlabel("Longitude (°E, WGS84)")
    ax.set_ylabel("Latitude (°N, WGS84)")
    ax.set_title("D-Figure 1 — Morocco long-haul study area and directional candidates")
    ax.set_aspect("equal", adjustable="box")
    ax.grid(True, linestyle=":", linewidth=0.4, color="#bbbbbb")

    legend = [
        Line2D([0], [0], color=C["motorway"], lw=2, label="Motorway (routing baseline)"),
        Line2D([0], [0], color=C["trunk"], lw=1.5, label="Trunk (expanded network)"),
        Line2D([0], [0], color="#cccccc", lw=1, label="Primary (background sample)"),
        Line2D([0], [0], marker="^", color="w", markerfacecolor=C["candidate"], markersize=8, label="Matched ADM candidate"),
        Line2D([0], [0], marker="x", color="#999999", markersize=8, label="Unmatched inventory"),
        Line2D([0], [0], marker="o", color="w", markerfacecolor="k", markersize=6, label="OD city anchors"),
    ]
    ax.legend(handles=legend, loc="lower right", fontsize=8, frameon=True)

    # Approximate scale bar at ~34N (1° lon ≈ 92 km)
    x0, y0 = -9.3, 30.45
    ax.plot([x0, x0 + 100 / 92.0], [y0, y0], color="k", lw=2)
    ax.text(x0 + 50 / 92.0, y0 + 0.12, "100 km", ha="center", fontsize=8)

    ax.text(
        0.01,
        0.01,
        "CRS: EPSG:4326 (WGS84). Road geometry: © OpenStreetMap contributors (ODbL).\n"
        "ADM service-area names: ADM. Chargers are hypothetical research installations.\n"
        "Lines are actual directed OSM edge segments (sampled), not OD straight lines.",
        transform=ax.transAxes,
        fontsize=6.5,
        va="bottom",
        ha="left",
        bbox=dict(boxstyle="round,pad=0.3", facecolor="white", edgecolor="#cccccc", alpha=0.92),
    )

    base = FIG / "D-Figure1_study_area"
    fig.savefig(base.with_suffix(".pdf"))
    fig.savefig(base.with_suffix(".png"), dpi=400)
    fig.savefig(base.with_suffix(".svg"))
    plt.close(fig)

    (FIG / "D-Figure1_description.md").write_text(
        "\n".join(
            [
                "# D-Figure 1 — Geographical study area",
                "",
                "Actual OSM-derived motorway/trunk/primary edge geometry with OD city anchors",
                "and ADM directional service-area candidates. CRS WGS84; OSM+ADM attribution.",
                "",
                "**Script:** `scripts/final_evidence/plot_d_figure1_study_area.py`",
                "",
            ]
        ),
        encoding="utf-8",
    )
    print("Wrote", base)


if __name__ == "__main__":
    main()
