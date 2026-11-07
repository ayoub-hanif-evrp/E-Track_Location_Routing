"""Generate an HTML research report for the pilot corridor."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import folium
import pandas as pd

from morocco_etruck.validation import network_summary

logger = logging.getLogger(__name__)


def _html_table(df: pd.DataFrame) -> str:
    return df.fillna("").to_html(index=False, border=1, classes="data")


def generate_report(
    G,
    sites: pd.DataFrame,
    baseline: dict[str, Any],
    processed_dir: Path,
    reports_dir: Path,
    title: str = "Task 01 — Casablanca–Agadir Pilot Network",
) -> Path:
    reports_dir.mkdir(parents=True, exist_ok=True)
    out = reports_dir / "pilot_corridor_report.html"

    # Map centre roughly mid-corridor
    m = folium.Map(location=[31.8, -8.4], zoom_start=7, tiles="OpenStreetMap")

    # Sample edges for performance
    edge_list = list(G.edges(data=True))
    step = max(1, len(edge_list) // 4000)
    for i, (u, v, data) in enumerate(edge_list):
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
        # Colour by rough travel direction: SW-ish = Casa→Agadir (blue), NE-ish = Agadir→Casa (orange)
        color = "#1f77b4"
        if brg_f is not None:
            if 120 <= brg_f <= 300:
                color = "#1f77b4"  # toward Agadir
            else:
                color = "#ff7f0e"
        folium.PolyLine(coords, color=color, weight=1, opacity=0.35).add_to(m)

    # Baseline paths
    for feat in baseline.get("geojson", {}).get("features", []):
        coords = [[c[1], c[0]] for c in feat["geometry"]["coordinates"]]
        label = feat["properties"].get("label", "route")
        folium.PolyLine(coords, color="#d62728", weight=4, opacity=0.9, tooltip=label).add_to(m)

    # Candidates
    for _, row in sites.iterrows():
        status = str(row.get("match_status", "unresolved"))
        if pd.isna(row.get("lat")) or pd.isna(row.get("lon")):
            continue
        color = {"verified": "green", "probable": "orange"}.get(status, "red")
        folium.CircleMarker(
            location=[float(row["lat"]), float(row["lon"])],
            radius=7,
            color=color,
            fill=True,
            fill_opacity=0.8,
            tooltip=f"{row.get('official_name')} [{status}]",
            popup=f"{row.get('official_name')}<br>{row.get('travel_direction')}<br>{status}",
        ).add_to(m)

    map_html = m.get_root().render()

    summary = network_summary(G)
    route_rows = []
    for key, r in baseline.get("routes", {}).items():
        route_rows.append(
            {
                "route": r.get("label", key),
                "ok": r.get("ok"),
                "distance_km": r.get("distance_km"),
                "n_nodes": r.get("n_nodes"),
                "error": r.get("error"),
            }
        )
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
            "connected_node_id",
            "connection_distance_m",
            "match_status",
            "requires_manual_review",
            "evidence",
        ]
        if c in sites.columns
    ]

    limitations = """
    <h2>Data quality limitations</h2>
    <ul>
      <li>ADM public HTML provides official names, partners, and travel directions but <strong>not coordinates</strong>.</li>
      <li>Candidate locations are matched to OpenStreetMap features when possible; unresolved rows are never given invented coordinates.</li>
      <li>A service area’s existence does <strong>not</strong> establish grid capacity, truck parking suitability, or high-power charging feasibility.</li>
      <li>HGV / goods access tags are frequently missing in OSM; such edges are labelled <code>hgv_access=unknown</code>.</li>
      <li>Baseline routes are shortest-distance connectivity checks on the directed motorway graph, not certified truck routes.</li>
      <li>Opposite-direction carriageways are never used as automatic snaps for a directional ADM aire.</li>
      <li>OpenStreetMap data is © OpenStreetMap contributors, ODbL 1.0.</li>
    </ul>
    """

    body = f"""
    <html><head><meta charset="utf-8"><title>{title}</title>
    <style>
      body {{ font-family: Georgia, serif; margin: 24px; }}
      table.data {{ border-collapse: collapse; font-size: 13px; }}
      table.data th, table.data td {{ border: 1px solid #444; padding: 4px 8px; }}
      .map {{ margin: 16px 0; }}
      .legend span {{ display:inline-block; width:12px; height:12px; margin-right:6px; }}
    </style></head><body>
    <h1>{title}</h1>
    <p>Joint charging placement and energy-feasible routing research — <em>Task 01 data foundation only</em>.
    No optimization algorithm is implemented in this report.</p>
    <div class="legend">
      <p><span style="background:#1f77b4"></span> Motorway edges (approx. Casa→Agadir bearing)
         <span style="background:#ff7f0e;margin-left:12px"></span> Motorway edges (approx. Agadir→Casa bearing)
         <span style="background:#d62728;margin-left:12px"></span> Baseline shortest paths
         <span style="background:green;margin-left:12px"></span> Verified candidates
         <span style="background:orange;margin-left:12px"></span> Probable
         <span style="background:red;margin-left:12px"></span> Unresolved (with coords only if OSM evidence exists)
      </p>
    </div>
    <div class="map">{map_html}</div>
    <h2>Network summary</h2>
    {_html_table(net_df)}
    <h2>Baseline route distances</h2>
    {_html_table(routes_df)}
    <p>Direction asymmetry (km): {baseline.get('direction_asymmetry_km')}</p>
    <h2>Candidate service areas (ADM directory, corridor only)</h2>
    {_html_table(sites[site_cols])}
    {limitations}
    <p><em>Generated from processed artifacts in {processed_dir.as_posix()}</em></p>
    </body></html>
    """
    out.write_text(body, encoding="utf-8")
    logger.info("Wrote report %s", out)
    return out
