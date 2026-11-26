#!/usr/bin/env python3
"""D-Figure 3 — Freight OD and route-alternative map (actual node paths)."""
from __future__ import annotations

import ast
import json
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd
from matplotlib.lines import Line2D

ROOT = Path(__file__).resolve().parents[2]
FIG = ROOT / "results/final_evidence/figures/dataset"
SRC = FIG / "source_data"

HEADLINE = {
    "casa_marrakech",
    "casa_agadir",
    "marrakech_agadir",
    "agadir_marrakech",
    "marrakech_casa",
    "agadir_casa",
    "casa_tangier",
    "tangier_casa",
    "tangier_rabat",
    "rabat_tangier",
    "rabat_fes",
    "fes_rabat",
    "casa_rabat",
    "rabat_casa",
}
OUJDA = {"fes_oujda", "oujda_fes", "casa_oujda", "oujda_casa"}


def _parse_nodes(s):
    if isinstance(s, list):
        return s
    try:
        return json.loads(s)
    except Exception:
        return ast.literal_eval(s)


def main() -> None:
    FIG.mkdir(parents=True, exist_ok=True)
    SRC.mkdir(parents=True, exist_ok=True)
    paths = pd.read_csv(ROOT / "data/processed/multiroute/path_alternatives.csv")
    nodes = pd.read_csv(ROOT / "data/processed/multiroute/nodes.csv").set_index("osm_node_id")

    fig, ax = plt.subplots(figsize=(9.5, 11), constrained_layout=True)
    fig.patch.set_facecolor("white")
    ax.set_facecolor("#f7f7f7")

    export_rows = []
    for _, r in paths.iterrows():
        od = r.od_id
        npath = _parse_nodes(r.node_path_json)
        xs, ys = [], []
        for nid in npath:
            try:
                row = nodes.loc[int(nid)]
            except KeyError:
                continue
            xs.append(float(row.lon))
            ys.append(float(row.lat))
        if len(xs) < 2:
            continue
        if od in HEADLINE:
            color = "#0072B2"
            lw = 1.2
            alpha = 0.75
            z = 3
        elif od in OUJDA:
            color = "#999999"
            lw = 0.8
            alpha = 0.45
            z = 2
        else:
            color = "#CC79A7"
            lw = 0.8
            alpha = 0.5
            z = 2
        # Distinguish alternatives lightly
        if str(r.method) != "shortest":
            ls = "--"
            alpha *= 0.85
        else:
            ls = "-"
        ax.plot(xs, ys, color=color, lw=lw, alpha=alpha, ls=ls, zorder=z)
        export_rows.append(
            {
                "od_id": od,
                "method": r.method,
                "length_m": r.length_m,
                "n_nodes": len(npath),
                "in_headline": od in HEADLINE,
                "is_oujda": od in OUJDA,
            }
        )

    # City anchors
    anchors = json.loads(
        (ROOT / "data/processed/multiroute/build_manifest.json").read_text(encoding="utf-8")
    )["anchors"]
    for name, key in [
        ("Tangier", "tangier"),
        ("Rabat", "rabat"),
        ("Casablanca", "casablanca"),
        ("Fès", "fes"),
        ("Oujda", "oujda"),
        ("Marrakech", "marrakech"),
        ("Agadir", "agadir"),
    ]:
        pt = nodes.loc[int(anchors[key])]
        ax.scatter(float(pt.lon), float(pt.lat), c="k", s=18, zorder=5)
        ax.annotate(name, (float(pt.lon), float(pt.lat)), xytext=(3, 3), textcoords="offset points", fontsize=7)

    ax.set_xlim(-9.9, -1.6)
    ax.set_ylim(30.1, 36.0)
    ax.set_aspect("equal", adjustable="box")
    ax.set_xlabel("Longitude (°E, WGS84)")
    ax.set_ylabel("Latitude (°N, WGS84)")
    ax.set_title("D-Figure 3 — Constructed OD routes (actual path geometry)")
    ax.grid(True, ls=":", lw=0.4, color="#bbbbbb")
    legend = [
        Line2D([0], [0], color="#0072B2", lw=2, label="Headline 14 (solid=shortest, dashed=alt)"),
        Line2D([0], [0], color="#999999", lw=1.5, label="Oujda-related (excluded from headline)"),
    ]
    ax.legend(handles=legend, loc="lower right", fontsize=8)
    ax.text(
        0.01,
        0.01,
        "Line thickness does NOT encode freight demand (no observed flows).\n"
        "Geometry from constructed path alternatives on OSM-derived network.",
        transform=ax.transAxes,
        fontsize=6.5,
        va="bottom",
        bbox=dict(boxstyle="round,pad=0.3", facecolor="white", edgecolor="#ccc", alpha=0.9),
    )
    pd.DataFrame(export_rows).to_csv(SRC / "D-Fig3_od_routes.csv", index=False)
    base = FIG / "D-Figure3_od_route_alternatives"
    fig.savefig(base.with_suffix(".pdf"))
    fig.savefig(base.with_suffix(".png"), dpi=400)
    fig.savefig(base.with_suffix(".svg"))
    plt.close(fig)
    (FIG / "D-Figure3_description.md").write_text(
        "# D-Figure 3 — OD route alternatives\n\nActual node-path geometry for 18 constructed ODs; headline 14 vs Oujda excluded.\n",
        encoding="utf-8",
    )
    print("Wrote", base)


if __name__ == "__main__":
    main()
