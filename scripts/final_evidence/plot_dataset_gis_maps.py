#!/usr/bin/env python3
"""Publication-grade GIS upgrades for D-Figure 1, 2 and 4.

- Continuous OSM edge geometries (no arbitrary motorway subsampling)
- Projected metric CRS with scale bars and attribution
- Verified matched-candidate coordinates only
- D-Fig2 geographic reduction panels (not count-only boxes)
- D-Fig4 Benguerir carriageway entrance/exit inset
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import geopandas as gpd
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.lines import Line2D
from matplotlib.patches import Patch, Rectangle
from shapely.geometry import LineString, Point, box

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts/final_evidence"))

from gis_map_utils import (  # noqa: E402
    CRS_PLOT,
    add_attribution,
    add_scale_bar,
    edges_to_gdf,
    load_city_anchors,
    matched_candidates,
    path_nodes_to_line,
    project,
    save_fig,
)

FIG = ROOT / "results/final_evidence/figures/dataset"
SRC = FIG / "source_data"
C = {
    "motorway": "#0072B2",
    "trunk": "#E69F00",
    "primary": "#B0B0B0",
    "city": "#000000",
    "candidate": "#D55E00",
    "land": "#f4f4f1",
    "path": "#009E73",
    "decision": "#CC79A7",
    "entrance": "#0072B2",
    "exit": "#D55E00",
}


def _motorway_full() -> gpd.GeoDataFrame:
    nodes = pd.read_csv(ROOT / "data/processed/road_nodes.csv")
    edges = pd.read_csv(ROOT / "data/processed/road_edges.csv")
    # Prefer motorway tags if present; else entire baseline road table is motorway-oriented
    if "highway" in edges.columns:
        edges = edges[edges.highway.astype(str).str.contains("motorway", na=False)]
    return edges_to_gdf(nodes, edges)


def _expanded_classes() -> tuple[gpd.GeoDataFrame, gpd.GeoDataFrame]:
    nodes = pd.read_csv(ROOT / "data/processed/multiroute/nodes.csv")
    edges = pd.read_csv(ROOT / "data/processed/multiroute/edges.csv")
    trunk = edges[edges.highway.isin(["trunk", "trunk_link"])]
    primary = edges[edges.highway.isin(["primary", "primary_link"])]
    # Continuous within study corridor bbox — filter spatially after build via clip
    return edges_to_gdf(nodes, trunk), edges_to_gdf(nodes, primary)


def _od_path_lines() -> gpd.GeoDataFrame:
    nodes = pd.read_csv(ROOT / "data/processed/multiroute/nodes.csv")
    paths = pd.read_csv(ROOT / "data/processed/multiroute/path_alternatives.csv")
    rows = []
    geoms = []
    for _, r in paths.iterrows():
        npath = json.loads(r.node_path_json)
        geom = path_nodes_to_line(nodes, npath)
        if geom is None:
            continue
        rows.append(
            {
                "od_id": r.od_id,
                "method": r.method,
                "length_m": float(r.length_m),
            }
        )
        geoms.append(geom)
    return gpd.GeoDataFrame(rows, geometry=geoms, crs="EPSG:4326")


def _decision_graph_layers() -> tuple[gpd.GeoDataFrame, gpd.GeoDataFrame]:
    nodes_xy = pd.read_csv(ROOT / "data/processed/multiroute/nodes.csv").set_index("osm_node_id")
    dg = json.loads(
        (ROOT / "data/processed/multiroute/decision_graph.json").read_text(encoding="utf-8")
    )
    dnodes = dg.get("decision_nodes") or {}
    n_rows, n_geoms = [], []
    for did, osm_id in dnodes.items():
        try:
            r = nodes_xy.loc[int(osm_id)]
        except (KeyError, ValueError, TypeError):
            continue
        n_rows.append({"decision_id": did, "osm_node_id": int(osm_id)})
        n_geoms.append(Point(float(r.lon), float(r.lat)))
    nodes_g = gpd.GeoDataFrame(n_rows, geometry=n_geoms, crs="EPSG:4326")

    a_rows, a_geoms = [], []
    for a in dg.get("arcs") or []:
        pn = [int(x) for x in (a.get("path_nodes") or [])]
        coords = []
        for nid in pn:
            if nid in nodes_xy.index:
                rr = nodes_xy.loc[nid]
                coords.append((float(rr.lon), float(rr.lat)))
        if len(coords) < 2:
            continue
        a_rows.append(
            {
                "arc_id": a.get("arc_id"),
                "u": a.get("u"),
                "v": a.get("v"),
                "length_m": a.get("length_m"),
            }
        )
        a_geoms.append(LineString(coords))
    arcs_g = gpd.GeoDataFrame(a_rows, geometry=a_geoms, crs="EPSG:4326")
    return nodes_g, arcs_g


def plot_d_figure1() -> None:
    print("[D1] building continuous geometries...", flush=True)
    mw = _motorway_full()
    trunk, primary = _expanded_classes()
    cities = load_city_anchors()
    cand = matched_candidates()
    # Clip trunk/primary to study extent for readability while keeping all segments inside
    study = gpd.GeoDataFrame(
        geometry=[box(-9.95, 30.05, -1.55, 36.05)], crs="EPSG:4326"
    )
    trunk = gpd.clip(trunk, study)
    primary = gpd.clip(primary, study)

    mw_p, tr_p, pr_p = project(mw), project(trunk), project(primary)
    cities_p, cand_p = project(cities), project(cand)

    fig, ax = plt.subplots(figsize=(9.2, 11.0), constrained_layout=True)
    fig.patch.set_facecolor("white")
    ax.set_facecolor(C["land"])
    pr_p.plot(ax=ax, color=C["primary"], linewidth=0.25, alpha=0.55, zorder=1)
    tr_p.plot(ax=ax, color=C["trunk"], linewidth=0.55, alpha=0.85, zorder=2)
    mw_p.plot(ax=ax, color=C["motorway"], linewidth=0.85, alpha=0.95, zorder=3)
    if len(cand_p):
        cand_p.plot(ax=ax, color=C["candidate"], markersize=28, marker="^", zorder=5)
    cities_p.plot(ax=ax, color=C["city"], markersize=18, zorder=6)
    for _, r in cities_p.iterrows():
        ax.annotate(
            r["name"],
            (r.geometry.x, r.geometry.y),
            textcoords="offset points",
            xytext=(5, 5),
            fontsize=8,
            fontweight="bold",
        )

    # Study extent rectangle in projected coords
    study_p = project(study)
    minx, miny, maxx, maxy = study_p.total_bounds
    ax.set_xlim(minx, maxx)
    ax.set_ylim(miny, maxy)
    ax.set_aspect("equal")
    ax.set_xticks([])
    ax.set_yticks([])
    ax.set_title("D-Figure 1 — Morocco long-haul study area and directional candidates", fontsize=12)
    add_scale_bar(ax, 100)
    add_attribution(ax, "Matched OSM candidate coordinates only.")
    legend = [
        Line2D([0], [0], color=C["motorway"], lw=2.2, label="Motorway (continuous)"),
        Line2D([0], [0], color=C["trunk"], lw=1.6, label="Trunk (expanded)"),
        Line2D([0], [0], color=C["primary"], lw=1.2, label="Primary (expanded)"),
        Line2D([0], [0], marker="^", color="w", markerfacecolor=C["candidate"], markersize=8, label="Matched ADM candidate"),
        Line2D([0], [0], marker="o", color="w", markerfacecolor="k", markersize=6, label="OD city anchors"),
    ]
    ax.legend(handles=legend, loc="lower right", fontsize=8)
    cities.drop(columns="geometry").to_csv(SRC / "D-Fig1_cities.csv", index=False)
    cand.drop(columns="geometry").to_csv(SRC / "D-Fig1_candidates.csv", index=False)
    save_fig(fig, FIG / "D-Figure1_study_area")
    (FIG / "D-Figure1_description.md").write_text(
        "D-Figure 1: Projected continuous OSM motorway/trunk/primary geometry with OD city "
        "anchors and OSM-matched ADM directional candidates only. Metric scale bar; OSM+ADM attribution.\n",
        encoding="utf-8",
    )


def plot_d_figure2() -> None:
    print("[D2] geographic reduction panels...", flush=True)
    summary = json.loads(
        (ROOT / "results/final_evidence/dataset/independent_recount_summary.json").read_text(
            encoding="utf-8"
        )
    )
    vc = summary["verified_counts"]
    mw = _motorway_full()
    trunk, primary = _expanded_classes()
    study = gpd.GeoDataFrame(geometry=[box(-9.95, 30.05, -1.55, 36.05)], crs="EPSG:4326")
    trunk = gpd.clip(trunk, study)
    primary = gpd.clip(primary, study)
    paths = _od_path_lines()
    # Headline ODs only for readability in path-union panel
    headline = {
        "casa_marrakech",
        "casa_agadir",
        "marrakech_agadir",
        "agadir_casa",
        "casa_tangier",
        "tangier_casa",
        "rabat_fes",
        "fes_rabat",
        "casa_rabat",
        "rabat_casa",
        "rabat_tangier",
        "tangier_rabat",
        "agadir_marrakech",
        "marrakech_casa",
    }
    paths_h = paths[paths.od_id.isin(headline)]
    dnodes, darcs = _decision_graph_layers()

    mw_p = project(mw)
    exp_p = project(pd.concat([trunk, primary], ignore_index=True))
    paths_p = project(paths_h)
    darcs_p = project(darcs)
    dnodes_p = project(dnodes)
    cities_p = project(load_city_anchors())
    study_p = project(study)
    minx, miny, maxx, maxy = study_p.total_bounds

    fig, axes = plt.subplots(2, 2, figsize=(11.5, 10.5), constrained_layout=True)
    fig.patch.set_facecolor("white")
    panels = [
        (axes[0, 0], "(a) Motorway network", mw_p, C["motorway"], 0.7,
         f"{vc['motorway_nodes']:,} nodes · {vc['motorway_edges']:,} edges"),
        (axes[0, 1], "(b) Expanded network", exp_p, C["trunk"], 0.45,
         f"{vc['expanded_nodes']:,} nodes · {vc['expanded_edges']:,} edges"),
        (axes[1, 0], "(c) Route-union paths", paths_p, C["path"], 1.1,
         f"{vc['od_pairs']} OD × 2 alts = {vc['path_records']} path records"),
        (axes[1, 1], "(d) Decision graph", darcs_p, C["decision"], 1.0,
         f"{vc['decision_nodes']} nodes · {vc['decision_arcs']} arcs"),
    ]
    for ax, title, layer, color, lw, counts in panels:
        ax.set_facecolor(C["land"])
        # faint motorway underlay for geographic context
        mw_p.plot(ax=ax, color="#d0d0d0", linewidth=0.25, zorder=1)
        layer.plot(ax=ax, color=color, linewidth=lw, alpha=0.9, zorder=3)
        if title.startswith("(d)") and len(dnodes_p):
            dnodes_p.plot(ax=ax, color="k", markersize=4, zorder=4)
        cities_p.plot(ax=ax, color="k", markersize=8, zorder=5)
        ax.set_xlim(minx, maxx)
        ax.set_ylim(miny, maxy)
        ax.set_aspect("equal")
        ax.set_xticks([])
        ax.set_yticks([])
        ax.set_title(f"{title}\n{counts}", fontsize=10)
        add_scale_bar(ax, 100, location=(0.08, 0.08))

    add_attribution(axes[1, 1], "Verified recount overlays geographic layers.")
    fig.suptitle("D-Figure 2 — Dataset construction and graph reduction (geographic)", fontsize=12)
    pd.DataFrame(
        [
            {"panel": "a_motorway", "nodes": vc["motorway_nodes"], "edges": vc["motorway_edges"]},
            {"panel": "b_expanded", "nodes": vc["expanded_nodes"], "edges": vc["expanded_edges"]},
            {"panel": "c_paths", "od_pairs": vc["od_pairs"], "path_records": vc["path_records"]},
            {"panel": "d_decision", "nodes": vc["decision_nodes"], "arcs": vc["decision_arcs"]},
        ]
    ).to_csv(SRC / "D-Fig2_panel_counts.csv", index=False)
    save_fig(fig, FIG / "D-Figure2_graph_reduction")
    (FIG / "D-Figure2_description.md").write_text(
        "D-Figure 2: Geographic reduction from continuous motorway → expanded trunk/primary → "
        "OD route-union paths → decision-graph macros/nodes, with verified recount labels.\n",
        encoding="utf-8",
    )


def plot_d_figure4() -> None:
    print("[D4] candidates + Benguerir carriageway inset...", flush=True)
    nodes = pd.read_csv(ROOT / "data/processed/multiroute/nodes.csv")
    edges = pd.read_csv(ROOT / "data/processed/multiroute/edges.csv")
    mw = _motorway_full()
    cand = matched_candidates()
    cities = load_city_anchors()
    # Focus retained headline-ish matched candidates
    if "retained_in_headline_candidate_pool" in cand.columns:
        retained = cand[cand["retained_in_headline_candidate_pool"] == True]  # noqa: E712
        if not len(retained):
            retained = cand
    else:
        retained = cand

    fig = plt.figure(figsize=(12.5, 6.2), constrained_layout=True)
    fig.patch.set_facecolor("white")
    gs = fig.add_gridspec(1, 2, width_ratios=[1.15, 1.0])
    ax = fig.add_subplot(gs[0, 0])
    ax.set_facecolor(C["land"])
    mw_p = project(mw)
    cand_p = project(retained)
    cities_p = project(cities)
    mw_p.plot(ax=ax, color="#cfcfcf", linewidth=0.35, zorder=1)
    cand_p.plot(ax=ax, color=C["candidate"], markersize=36, marker="^", zorder=4)
    # Directional CA vs AC styling via travel_direction if available
    if "travel_direction" in retained.columns:
        for _, r in project(retained).iterrows():
            td = str(r.get("travel_direction") or "")
            marker = "^" if "Casablanca" in td and "Agadir" in td else "v"
            ax.scatter(
                [r.geometry.x],
                [r.geometry.y],
                c=C["candidate"],
                s=42,
                marker=marker,
                zorder=5,
                edgecolors="k",
                linewidths=0.3,
            )
    cities_p.plot(ax=ax, color="k", markersize=14, zorder=6)
    for _, r in cities_p.iterrows():
        ax.annotate(
            r["name"],
            (r.geometry.x, r.geometry.y),
            fontsize=7,
            fontweight="bold",
            xytext=(4, 4),
            textcoords="offset points",
        )
    for _, r in project(retained).iterrows():
        label = str(r.official_name)[:18]
        ax.annotate(label, (r.geometry.x, r.geometry.y), fontsize=5.5, xytext=(4, -10), textcoords="offset points")
    study_p = project(gpd.GeoDataFrame(geometry=[box(-9.5, 30.2, -5.5, 35.8)], crs="EPSG:4326"))
    minx, miny, maxx, maxy = study_p.total_bounds
    ax.set_xlim(minx, maxx)
    ax.set_ylim(miny, maxy)
    ax.set_aspect("equal")
    ax.set_xticks([])
    ax.set_yticks([])
    ax.set_title("(a) Matched directional candidates (verified OSM coords)")
    add_scale_bar(ax, 100)
    ax.legend(
        handles=[
            Line2D([0], [0], marker="^", color="w", markerfacecolor=C["candidate"], markersize=8, label="Matched candidate"),
            Line2D([0], [0], marker="o", color="w", markerfacecolor="k", markersize=6, label="City anchor"),
        ],
        fontsize=7,
        loc="lower right",
    )

    # (b) Benguerir opposite-carriageway inset with entrance/exit
    ax2 = fig.add_subplot(gs[0, 1])
    ax2.set_facecolor(C["land"])
    beng = cand[
        cand.official_name.astype(str).str.contains("BENGUERIR", case=False, na=False)
    ].copy()
    # Local motorway/trunk edges near Benguerir
    local_box = box(-8.05, 32.20, -7.88, 32.35)
    local_area = gpd.GeoDataFrame(geometry=[local_box], crs="EPSG:4326")
    local_roads = gpd.clip(mw, local_area)
    # Also include nearby expanded edges
    near_edges = edges.copy()
    # Build from nodes within bbox
    node_xy = nodes.set_index("osm_node_id")
    in_bbox = node_xy[
        (node_xy.lon >= -8.05)
        & (node_xy.lon <= -7.88)
        & (node_xy.lat >= 32.20)
        & (node_xy.lat <= 32.35)
    ].index.astype(int)
    near = edges[edges.u.isin(in_bbox) | edges.v.isin(in_bbox)]
    near_g = edges_to_gdf(nodes, near)

    project(near_g).plot(ax=ax2, color="#bbbbbb", linewidth=0.8, zorder=1)
    project(local_roads).plot(ax=ax2, color=C["motorway"], linewidth=1.6, zorder=2)

    inset_rows = []
    beng_g = gpd.GeoDataFrame(
        beng,
        geometry=[Point(xy) for xy in zip(beng.lon.astype(float), beng.lat.astype(float))],
        crs="EPSG:4326",
    )
    beng_p = project(beng_g)
    xs_all, ys_all = [], []
    # Slight horizontal offset for opposite carriageway labels/sites so CA≠AC collapse
    offsets = {}
    for i, (_, r0) in enumerate(beng_p.iterrows()):
        offsets[r0.official_name] = (-180 if i == 0 else 180, 120 if i == 0 else -120)

    for _, r in beng_p.iterrows():
        name = str(r.official_name)
        if "Casablanca" in name and "Agadir" in name and name.lower().find("casablanca") < name.lower().find("agadir"):
            col = "#0072B2"
            carriage = "CA (Casa→Agadir)"
        else:
            col = "#D55E00"
            carriage = "AC (Agadir→Casa)"
        dx, dy = offsets.get(r.official_name, (0, 0))
        sx, sy = r.geometry.x + dx * 0.15, r.geometry.y + dy * 0.15
        ax2.scatter([sx], [sy], c=col, s=80, marker="^", zorder=5, edgecolors="k")
        ax2.annotate(carriage, (sx, sy), fontsize=7, xytext=(8, 6), textcoords="offset points")
        xs_all.extend([sx])
        ys_all.extend([sy])

        ent_pt = ex_pt = None
        for kind, ncol, col_id in [
            ("entrance", "#009E73", r.get("entrance_node_id")),
            ("exit", "#E69F00", r.get("exit_node_id")),
        ]:
            if pd.isna(col_id):
                continue
            try:
                nr = node_xy.loc[int(float(col_id))]
            except Exception:
                continue
            pt = project(
                gpd.GeoDataFrame(geometry=[Point(float(nr.lon), float(nr.lat))], crs="EPSG:4326")
            )
            px, py = float(pt.geometry.iloc[0].x), float(pt.geometry.iloc[0].y)
            # small perpendicular nudge so entrance/exit remain distinguishable
            nudge = 40 if kind == "entrance" else -40
            px2, py2 = px + nudge, py + nudge
            ax2.scatter(
                [px2],
                [py2],
                c=ncol,
                s=42,
                marker="o" if kind == "entrance" else "s",
                zorder=6,
                edgecolors="k",
                linewidths=0.4,
            )
            ax2.annotate(kind[:3], (px2, py2), fontsize=6, xytext=(4, 2), textcoords="offset points")
            xs_all.extend([px2])
            ys_all.extend([py2])
            if kind == "entrance":
                ent_pt = (px2, py2)
            else:
                ex_pt = (px2, py2)
            inset_rows.append(
                {
                    "site": r.official_name,
                    "carriageway": carriage,
                    "node_role": kind,
                    "osm_node_id": int(float(col_id)),
                    "lon": float(nr.lon),
                    "lat": float(nr.lat),
                    "access": r.get("directed_access_status"),
                }
            )
        if ent_pt and ex_pt:
            ax2.plot([ent_pt[0], ex_pt[0]], [ent_pt[1], ex_pt[1]], color=col, lw=1.2, ls="--", zorder=4)

    # Tight zoom on actual node cluster
    if xs_all and ys_all:
        minx, maxx = min(xs_all), max(xs_all)
        miny, maxy = min(ys_all), max(ys_all)
        pad = max(800.0, 0.35 * max(maxx - minx, maxy - miny, 1.0))
        ax2.set_xlim(minx - pad, maxx + pad)
        ax2.set_ylim(miny - pad, maxy + pad)
    else:
        loc_p = project(local_area)
        minx, miny, maxx, maxy = loc_p.total_bounds
        pad = 1500
        ax2.set_xlim(minx - pad, maxx + pad)
        ax2.set_ylim(miny - pad, maxy + pad)
    ax2.set_aspect("equal")
    ax2.set_xticks([])
    ax2.set_yticks([])
    ax2.set_title("(b) Benguerir opposite-carriageway inset\nentrance/exit nodes on continuous road geometry")
    add_scale_bar(ax2, 5, location=(0.08, 0.08))
    ax2.legend(
        handles=[
            Line2D([0], [0], color=C["motorway"], lw=2, label="Motorway"),
            Line2D([0], [0], marker="^", color="w", markerfacecolor="#0072B2", markersize=8, label="CA carriageway site"),
            Line2D([0], [0], marker="^", color="w", markerfacecolor="#D55E00", markersize=8, label="AC carriageway site"),
            Line2D([0], [0], marker="o", color="w", markerfacecolor="#009E73", markersize=7, label="Entrance node"),
            Line2D([0], [0], marker="s", color="w", markerfacecolor="#E69F00", markersize=7, label="Exit node"),
        ],
        fontsize=6.5,
        loc="upper left",
    )
    add_attribution(ax2, "Entrance/exit from matched OSM connectivity audit.")

    pd.DataFrame(inset_rows).to_csv(SRC / "D-Fig4_benguerir_access_inset.csv", index=False)
    retained.drop(columns="geometry").to_csv(SRC / "D-Fig4_candidates.csv", index=False)
    fig.suptitle("D-Figure 4 — Directional candidate infrastructure", fontsize=12)
    save_fig(fig, FIG / "D-Figure4_directional_candidates")
    (FIG / "D-Figure4_description.md").write_text(
        "D-Figure 4: (a) OSM-matched directional candidates on continuous motorway context; "
        "(b) Benguerir CA/AC carriageway inset with entrance and exit nodes on local road geometry.\n",
        encoding="utf-8",
    )


def main() -> int:
    FIG.mkdir(parents=True, exist_ok=True)
    SRC.mkdir(parents=True, exist_ok=True)
    plot_d_figure1()
    plot_d_figure2()
    plot_d_figure4()
    print("GIS dataset maps complete")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
