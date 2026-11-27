#!/usr/bin/env python3
"""R-Figure 2 — Geographic feasibility using executed routes (I0–I3).

Feasible: reconstruct every DRIVE arc (including split/parent slices) from traces.
Missing arc geometry is flagged, not silently skipped without record.
Chargers use exact directional candidate IDs when available.
"""
from __future__ import annotations

import json
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd
from matplotlib.lines import Line2D

ROOT = Path(__file__).resolve().parents[2]
FE = ROOT / "results/final_evidence"
FIG = FE / "figures/results"
SRC = FIG / "source_data"
C = {
    "green": "#009E73",
    "blue": "#0072B2",
    "vermillion": "#D55E00",
    "orange": "#E69F00",
    "grey": "#999999",
    "purple": "#CC79A7",
}

INFRA = [
    ("I0_none", "I0 none"),
    ("I1_benguerir_ca", "I1 Benguerir CA"),
    ("I2_benguerir_larache", "I2 +Larache RT"),
    ("I3_benguerir_ca_larache_benguerir_ac", "I3 +Benguerir AC"),
]


def _load_arc_geoms():
    nodes = pd.read_csv(ROOT / "data/processed/multiroute/nodes.csv").set_index("osm_node_id")
    dg = json.loads(
        (ROOT / "data/processed/multiroute/decision_graph.json").read_text(encoding="utf-8")
    )
    arcs = {}
    for a in dg.get("arcs") or []:
        aid = str(a.get("arc_id"))
        pn = [int(x) for x in (a.get("path_nodes") or [])]
        xs, ys = [], []
        for nid in pn:
            if nid in nodes.index:
                xs.append(float(nodes.loc[nid, "lon"]))
                ys.append(float(nodes.loc[nid, "lat"]))
        if len(xs) >= 2:
            arcs[aid] = (xs, ys, float(a.get("length_m") or 0.0))
    denser = {}
    elev = ROOT / "data/processed/multiroute/elevation"
    for p in elev.glob("arc_*.json"):
        aid = p.stem.replace("arc_", "")
        try:
            raw = json.loads(p.read_text(encoding="utf-8"))
            coords = raw.get("coords_lonlat") or []
            if len(coords) >= 2:
                denser[aid] = (
                    [float(c[0]) for c in coords],
                    [float(c[1]) for c in coords],
                    float(raw.get("length_m") or 0.0),
                )
        except Exception:
            continue
    return arcs, denser, nodes


def _trace_arcs(trace) -> list[str]:
    if trace is None or (isinstance(trace, float) and pd.isna(trace)):
        return []
    actions = json.loads(trace) if isinstance(trace, str) else trace
    return [
        str(a["arc_id"])
        for a in actions
        if (a.get("action_type") or a.get("type")) == "DRIVE" and a.get("arc_id")
    ]


def _charge_sites(trace) -> list[str]:
    if trace is None or (isinstance(trace, float) and pd.isna(trace)):
        return []
    actions = json.loads(trace) if isinstance(trace, str) else trace
    sites = []
    for a in actions:
        if (a.get("action_type") or a.get("type")) == "CHARGE":
            sites.append(str(a.get("site") or a.get("node") or ""))
    return [s for s in sites if s]


def _site_xy(site_id: str, cand: pd.DataFrame):
    """Resolve directional site id to coordinates; never collapse CA/AC to 'Benguerir'."""
    sid = str(site_id)
    # Exact key matches first
    for col in ("retained_headline_key_guess", "site_id", "id", "official_name"):
        if col in cand.columns:
            hit = cand[cand[col].astype(str) == sid]
            if len(hit):
                return float(hit.iloc[0].lon), float(hit.iloc[0].lat), sid
    # y_benguerir_ca / y_benguerir_ac style
    token = sid.replace("y_", "")
    if "site_key" in cand.columns:
        hit = cand[cand.site_key.astype(str) == token]
        if len(hit):
            return float(hit.iloc[0].lon), float(hit.iloc[0].lat), sid
    if "retained_headline_key_guess" in cand.columns:
        hit = cand[cand.retained_headline_key_guess.astype(str).str.fullmatch(token, case=False)]
        if len(hit):
            return float(hit.iloc[0].lon), float(hit.iloc[0].lat), sid
    # Directional suffix disambiguation
    if "benguerir_ca" in token and "official_name" in cand.columns:
        hit = cand[
            cand.official_name.astype(str).str.contains("Benguerir", case=False, na=False)
            & cand.official_name.astype(str).str.contains("CA|Casablanca|south", case=False, na=False)
        ]
        if len(hit):
            return float(hit.iloc[0].lon), float(hit.iloc[0].lat), sid
    if "benguerir_ac" in token and "official_name" in cand.columns:
        hit = cand[
            cand.official_name.astype(str).str.contains("Benguerir", case=False, na=False)
            & cand.official_name.astype(str).str.contains("AC|Agadir|north", case=False, na=False)
        ]
        if len(hit):
            return float(hit.iloc[0].lon), float(hit.iloc[0].lat), sid
    return None


def main() -> None:
    FIG.mkdir(parents=True, exist_ok=True)
    SRC.mkdir(parents=True, exist_ok=True)
    arcs, denser, nodes = _load_arc_geoms()
    panel = FE / "experiments/primary_i0_i3_panel/primary_i0_i3_missions.csv"
    m = pd.read_csv(panel if panel.exists() else FE / "experiments/primary_comparison/primary_missions.csv")
    m = m[(m.vehicle_key == "eactros_600") & (m.soc_scenario == "stressed_mixed")]
    paths = pd.read_csv(ROOT / "data/processed/multiroute/path_alternatives.csv")
    cand = pd.read_csv(FE / "tables/dataset/D-T04_candidate_inventory.csv")
    cand = cand[pd.to_numeric(cand.lon, errors="coerce").notna()]

    # Installed directional sites per infra (not only visited)
    installed_xy = {
        "I1_benguerir_ca": ["y_benguerir_ca"],
        "I2_benguerir_larache": ["y_benguerir_ca", "y_larache_rt"],
        "I3_benguerir_ca_larache_benguerir_ac": [
            "y_benguerir_ca",
            "y_larache_rt",
            "y_benguerir_ac",
        ],
    }

    export_rows = []
    fig, axes = plt.subplots(1, 4, figsize=(16.5, 5.2), constrained_layout=True)
    fig.patch.set_facecolor("white")
    for ax, (infra, title) in zip(axes, INFRA):
        ax.set_facecolor("#f7f7f7")
        sub = m[m.infra_config_id == infra]
        for _, r in sub.iterrows():
            od = r.od_id
            served = bool(r.operationally_served)
            base = m[(m.infra_config_id == "I0_none") & (m.od_id == od)]
            was = bool(base.iloc[0].operationally_served) if len(base) else False
            status = str(r.status)
            route_kind = "executed"
            drive_arcs = _trace_arcs(r.action_trace_json) if served else []
            xs_all, ys_all = [], []
            missing_arcs = []
            route_len_m = 0.0
            if drive_arcs:
                for aid in drive_arcs:
                    geom = denser.get(aid) or arcs.get(aid)
                    if not geom:
                        missing_arcs.append(aid)
                        continue
                    xs_all.extend(geom[0])
                    ys_all.extend(geom[1])
                    route_len_m += float(geom[2] or 0.0)
            if len(xs_all) < 2:
                route_kind = "reference_shortest"
                pr = paths[paths.od_id == od].sort_values("length_m").iloc[0]
                npath = json.loads(pr.node_path_json)
                for nid in npath:
                    if int(nid) in nodes.index:
                        xs_all.append(float(nodes.loc[int(nid), "lon"]))
                        ys_all.append(float(nodes.loc[int(nid), "lat"]))
                route_len_m = float(pr.length_m)
            if len(xs_all) < 2:
                continue
            if served and was:
                col, lw, ls = C["green"], 1.5, "-"
                label_class = "feasible_I0"
            elif served:
                col, lw, ls = C["blue"], 1.6, "-"
                label_class = "newly_enabled"
            elif status == "LIMIT_REACHED":
                col, lw, ls = C["orange"], 1.3, "--"
                label_class = "unresolved"
            else:
                col, lw, ls = C["vermillion"], 1.2, ":" if route_kind == "reference_shortest" else "-"
                label_class = (
                    "infeasible_reference" if route_kind == "reference_shortest" else "infeasible"
                )
            ax.plot(xs_all, ys_all, color=col, lw=lw, ls=ls, alpha=0.9)
            mid = len(xs_all) // 2
            if mid + 1 < len(xs_all):
                ax.annotate(
                    "",
                    xy=(xs_all[mid + 1], ys_all[mid + 1]),
                    xytext=(xs_all[mid], ys_all[mid]),
                    arrowprops=dict(arrowstyle="->", color=col, lw=0.8),
                )
            visited = _charge_sites(r.action_trace_json) if served else []
            for s in visited:
                xy = _site_xy(s, cand)
                if xy:
                    ax.scatter(
                        xy[0], xy[1], c=C["orange"], s=28, zorder=6, edgecolors="k", linewidths=0.3
                    )
            export_rows.append(
                {
                    "od_id": od,
                    "infra_config_id": infra,
                    "status": status,
                    "operationally_served": served,
                    "route_kind": route_kind,
                    "label_class": label_class,
                    "n_drive_arcs": len(drive_arcs),
                    "n_missing_arc_geom": len(missing_arcs),
                    "missing_arc_ids": ",".join(missing_arcs),
                    "route_length_m": route_len_m,
                    "visited_charge_sites": ",".join(visited),
                }
            )
        # Installed sites (hollow) vs visited (filled)
        for sid in installed_xy.get(infra, []):
            xy = _site_xy(sid, cand)
            if xy:
                ax.scatter(
                    xy[0],
                    xy[1],
                    facecolors="none",
                    edgecolors=C["purple"],
                    s=55,
                    linewidths=1.2,
                    zorder=5,
                )
                ax.text(xy[0], xy[1], f" {sid}", fontsize=6, color=C["purple"])
        ax.set_title(title)
        ax.set_xlim(-9.9, -5.5)
        ax.set_ylim(30.1, 36.0)
        ax.set_aspect("equal", adjustable="box")
        ax.grid(True, ls=":", lw=0.3)
        ax.set_xlabel("Longitude")
        if ax is axes[0]:
            ax.set_ylabel("Latitude")
    legend = [
        Line2D([0], [0], color=C["green"], lw=2, label="Feasible at I0 (executed)"),
        Line2D([0], [0], color=C["blue"], lw=2, label="Newly enabled (executed)"),
        Line2D([0], [0], color=C["vermillion"], lw=2, ls=":", label="Infeasible (reference)"),
        Line2D([0], [0], color=C["orange"], lw=2, ls="--", label="Unresolved LIMIT"),
        Line2D(
            [0],
            [0],
            marker="o",
            color="w",
            markerfacecolor=C["orange"],
            markersize=7,
            label="Visited charger",
        ),
        Line2D(
            [0],
            [0],
            marker="o",
            color="w",
            markerfacecolor="none",
            markeredgecolor=C["purple"],
            markersize=8,
            label="Installed directional site",
        ),
    ]
    axes[-1].legend(handles=legend, fontsize=6, loc="lower right")
    fig.suptitle(
        "R-Figure 2 — Geographic feasibility with executed routes (eActros stressed, I0–I3)",
        fontsize=12,
    )
    pd.DataFrame(export_rows).to_csv(SRC / "R-Fig2_feasibility_by_infra.csv", index=False)
    (FIG / "R-Figure2_description.md").write_text(
        "R-Figure 2: Feasible missions plot every executed DRIVE arc from solution traces "
        "(missing geometry counted). Infeasible missions use an explicitly labeled shortest "
        "reference. Hollow purple markers = installed directional sites "
        "(y_benguerir_ca vs y_benguerir_ac distinguished); filled orange = visited chargers.\n",
        encoding="utf-8",
    )
    base = FIG / "R-Figure2_geographic_feasibility"
    fig.savefig(base.with_suffix(".pdf"))
    fig.savefig(base.with_suffix(".png"), dpi=400)
    # SVG omitted for oversized GIS-like exports; PDF/PNG are authoritative.
    plt.close(fig)
    print("Wrote", base, "rows", len(export_rows))


if __name__ == "__main__":
    main()
