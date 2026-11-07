"""Generate HTML and static figures for the pilot corridor."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import folium
import matplotlib.pyplot as plt
import pandas as pd

from morocco_etruck.validation import network_summary

logger = logging.getLogger(__name__)


def _html_table(df: pd.DataFrame) -> str:
    return df.fillna("").to_html(index=False, border=1, classes="data")


def _access_color(status: str) -> str:
    return {
        "entrance_and_exit": "green",
        "entrance_only": "orange",
        "exit_only": "orange",
        "proximity_only": "purple",
        "opposite_carriageway_only": "brown",
        "unresolved": "red",
    }.get(status, "gray")


def generate_report(
    G,
    sites: pd.DataFrame,
    baseline: dict[str, Any],
    processed_dir: Path,
    reports_dir: Path,
    title: str = "Task 01B — Casablanca–Agadir Pilot Network (audited)",
) -> Path:
    reports_dir.mkdir(parents=True, exist_ok=True)
    out = reports_dir / "pilot_corridor_report.html"

    m = folium.Map(location=[31.8, -8.4], zoom_start=7, tiles="OpenStreetMap")

    if G.is_multigraph():
        edge_list = list(G.edges(keys=True, data=True))
    else:
        edge_list = [(u, v, 0, d) for u, v, d in G.edges(data=True)]
    step = max(1, len(edge_list) // 4000)
    for i, (u, v, _k, data) in enumerate(edge_list):
        if i % step != 0:
            continue
        coords = [
            [G.nodes[u]["lat"], G.nodes[u]["lon"]],
            [G.nodes[v]["lat"], G.nodes[v]["lon"]],
        ]
        brg = data.get("bearing_deg")
        try:
            brg_f = float(brg) if brg not in ("", None) else None
        except (TypeError, ValueError):
            brg_f = None
        color = "#1f77b4"
        if brg_f is not None:
            color = "#1f77b4" if 120 <= brg_f <= 300 else "#ff7f0e"
        folium.PolyLine(coords, color=color, weight=1, opacity=0.35).add_to(m)

    for feat in baseline.get("geojson", {}).get("features", []):
        coords = [[c[1], c[0]] for c in feat["geometry"]["coordinates"]]
        label = feat["properties"].get("label", "route")
        folium.PolyLine(coords, color="#d62728", weight=4, opacity=0.9, tooltip=label).add_to(m)

    for _, row in sites.iterrows():
        if pd.isna(row.get("lat")) or pd.isna(row.get("lon")):
            continue
        status = str(row.get("directed_access_status", "unresolved"))
        color = _access_color(status)
        folium.CircleMarker(
            location=[float(row["lat"]), float(row["lon"])],
            radius=7,
            color=color,
            fill=True,
            fill_opacity=0.8,
            tooltip=f"{row.get('official_name')} [{status}]",
            popup=(
                f"{row.get('official_name')}<br>{row.get('travel_direction')}<br>"
                f"location={row.get('location_match_status')}<br>"
                f"access={status}<br>hgv={row.get('hgv_access_status')}"
            ),
        ).add_to(m)

    map_html = m.get_root().render()
    summary = network_summary(G)
    route_rows = [
        {
            "route": r.get("label", key),
            "ok": r.get("ok"),
            "distance_km": r.get("distance_km"),
            "n_nodes": r.get("n_nodes"),
            "error": r.get("error"),
        }
        for key, r in baseline.get("routes", {}).items()
    ]
    routes_df = pd.DataFrame(route_rows)
    net_df = pd.DataFrame([summary])
    site_cols = [
        c
        for c in [
            "official_name",
            "partner",
            "travel_direction",
            "lat",
            "lon",
            "osm_id",
            "location_match_status",
            "directed_access_status",
            "hgv_access_status",
            "entrance_path_m",
            "exit_path_m",
            "requires_manual_review",
            "evidence",
        ]
        if c in sites.columns
    ]

    limitations = """
    <h2>Data quality limitations</h2>
    <ul>
      <li>ADM HTML has names/directions but <strong>no coordinates</strong>.</li>
      <li><code>location_match_status</code> is separate from <code>directed_access_status</code>.</li>
      <li>Proximity or bearing alone never yields truck-accessible verification.</li>
      <li>OSM entrance/exit topology ≠ legal HGV certification; <code>hgv_access_status</code> is usually unknown.</li>
      <li>Service areas are not claimed as electrically suitable charger sites.</li>
      <li>OpenStreetMap © contributors, ODbL 1.0. Python code licence is separate.</li>
    </ul>
    """

    body = f"""
    <html><head><meta charset="utf-8"><title>{title}</title>
    <style>
      body {{ font-family: Georgia, serif; margin: 24px; }}
      table.data {{ border-collapse: collapse; font-size: 13px; }}
      table.data th, table.data td {{ border: 1px solid #444; padding: 4px 8px; }}
    </style></head><body>
    <h1>{title}</h1>
    <p>Task 01B audited data foundation. No energy model or optimization.</p>
    <div class="map">{map_html}</div>
    <h2>Network summary</h2>
    {_html_table(net_df)}
    <h2>Baseline route distances</h2>
    {_html_table(routes_df)}
    <p>Direction asymmetry (km): {baseline.get('direction_asymmetry_km')}</p>
    <h2>Candidate access audit</h2>
    {_html_table(sites[site_cols])}
    {limitations}
    </body></html>
    """
    out.write_text(body, encoding="utf-8")
    logger.info("Wrote report %s", out)
    return out


def write_static_corridor_figure(
    sites: pd.DataFrame,
    baseline: dict[str, Any],
    reports_dir: Path,
) -> Path:
    """Lightweight PNG suitable for GitHub review (edge-geometry baselines + sites)."""
    reports_dir.mkdir(parents=True, exist_ok=True)
    out = reports_dir / "pilot_corridor_overview.png"
    fig, ax = plt.subplots(figsize=(7.5, 9), dpi=120)

    for feat in baseline.get("geojson", {}).get("features", []):
        coords = feat["geometry"]["coordinates"]
        xs = [c[0] for c in coords]
        ys = [c[1] for c in coords]
        label = feat["properties"].get("label", "route")
        ax.plot(xs, ys, linewidth=1.8, label=label)

    for _, row in sites.iterrows():
        if pd.isna(row.get("lat")) or pd.isna(row.get("lon")):
            continue
        status = str(row.get("directed_access_status", "unresolved"))
        ax.scatter(
            float(row["lon"]),
            float(row["lat"]),
            s=36,
            c=_access_color(status),
            edgecolors="black",
            linewidths=0.4,
            zorder=5,
        )
        ax.annotate(
            str(row.get("name_token", ""))[:10],
            (float(row["lon"]), float(row["lat"])),
            fontsize=7,
            xytext=(3, 3),
            textcoords="offset points",
        )

    ax.set_xlabel("Longitude (EPSG:4326)")
    ax.set_ylabel("Latitude (EPSG:4326)")
    ax.set_title("A3 pilot baselines and ADM candidates\n(green=entrance+exit topology; red=unresolved)")
    ax.legend(loc="best", fontsize=8)
    ax.set_aspect("equal", adjustable="datalim")
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(out, bbox_inches="tight")
    plt.close(fig)
    logger.info("Wrote static figure %s", out)
    return out
