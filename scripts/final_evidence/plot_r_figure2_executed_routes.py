#!/usr/bin/env python3
"""R-Figure 2 — Geographic feasibility using executed routes from action traces.

Feasible missions: reconstruct geometry from DRIVE arc_ids + decision-arc path_nodes.
Infeasible missions: explicitly labeled shortest-path reference route.
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
}


def _load_arc_geoms():
    # Prefer OD-local elevation coords when available; else nodes along decision path_nodes
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
            arcs[aid] = (xs, ys)
    # Also index elevation profiles by arc_id for denser geometry
    elev = ROOT / "data/processed/multiroute/elevation"
    denser = {}
    for p in elev.glob("arc_*.json"):
        aid = p.stem.replace("arc_", "")
        try:
            raw = json.loads(p.read_text(encoding="utf-8"))
            coords = raw.get("coords_lonlat") or []
            if len(coords) >= 2:
                denser[aid] = (
                    [float(c[0]) for c in coords],
                    [float(c[1]) for c in coords],
                )
        except Exception:
            continue
    return arcs, denser, nodes


def _trace_arcs(trace) -> list[str]:
    if trace is None or (isinstance(trace, float) and pd.isna(trace)):
        return []
    actions = json.loads(trace) if isinstance(trace, str) else trace
    out = []
    for a in actions:
        if (a.get("action_type") or a.get("type")) == "DRIVE" and a.get("arc_id"):
            out.append(str(a["arc_id"]))
    return out


def _charge_sites(trace) -> list[str]:
    if trace is None or (isinstance(trace, float) and pd.isna(trace)):
        return []
    actions = json.loads(trace) if isinstance(trace, str) else trace
    sites = []
    for a in actions:
        if (a.get("action_type") or a.get("type")) == "CHARGE":
            sites.append(str(a.get("site") or a.get("node") or ""))
    return [s for s in sites if s]


def main() -> None:
    FIG.mkdir(parents=True, exist_ok=True)
    SRC.mkdir(parents=True, exist_ok=True)
    arcs, denser, nodes = _load_arc_geoms()
    m = pd.read_csv(FE / "experiments/primary_comparison/primary_missions.csv")
    m = m[(m.vehicle_key == "eactros_600") & (m.soc_scenario == "stressed_mixed")]
    paths = pd.read_csv(ROOT / "data/processed/multiroute/path_alternatives.csv")
    cand = pd.read_csv(FE / "tables/dataset/D-T04_candidate_inventory.csv")
    cand = cand[pd.to_numeric(cand.lon, errors="coerce").notna()]

    export_rows = []
    fig, axes = plt.subplots(1, 3, figsize=(13.5, 5.4), constrained_layout=True)
    fig.patch.set_facecolor("white")
    for ax, infra, title in zip(
        axes,
        ["I0_none", "I1_benguerir_ca", "I2_benguerir_larache"],
        ["I0 none", "I1 Benguerir CA", "I2 +Larache"],
    ):
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
            if drive_arcs:
                for aid in drive_arcs:
                    geom = denser.get(aid) or arcs.get(aid)
                    if not geom:
                        continue
                    xs_all.extend(geom[0])
                    ys_all.extend(geom[1])
            if len(xs_all) < 2:
                # reference shortest path (explicitly labeled for infeasible / missing trace)
                route_kind = "reference_shortest"
                pr = paths[paths.od_id == od].sort_values("length_m").iloc[0]
                npath = json.loads(pr.node_path_json)
                for nid in npath:
                    if int(nid) in nodes.index:
                        xs_all.append(float(nodes.loc[int(nid), "lon"]))
                        ys_all.append(float(nodes.loc[int(nid), "lat"]))
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
                label_class = "infeasible_reference" if route_kind == "reference_shortest" else "infeasible"
            ax.plot(xs_all, ys_all, color=col, lw=lw, ls=ls, alpha=0.9)
            # direction arrow near mid
            mid = len(xs_all) // 2
            if mid + 1 < len(xs_all):
                ax.annotate(
                    "",
                    xy=(xs_all[mid + 1], ys_all[mid + 1]),
                    xytext=(xs_all[mid], ys_all[mid]),
                    arrowprops=dict(arrowstyle="->", color=col, lw=0.8),
                )
            sites = _charge_sites(r.action_trace_json) if served else []
            for s in sites:
                token = s.replace("y_", "").split("_")[0]
                hit = cand[
                    cand.official_name.astype(str).str.contains(token, case=False, na=False)
                    | cand.retained_headline_key_guess.astype(str).str.contains(
                        token, case=False, na=False
                    )
                ]
                if len(hit):
                    ax.scatter(
                        float(hit.iloc[0].lon),
                        float(hit.iloc[0].lat),
                        c=C["orange"],
                        s=28,
                        zorder=5,
                        edgecolors="k",
                        linewidths=0.3,
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
                    "charge_sites": ",".join(sites),
                }
            )
        ax.set_title(title)
        ax.set_xlim(-9.9, -5.5)
        ax.set_ylim(30.1, 36.0)
        ax.set_aspect("equal", adjustable="box")
        ax.grid(True, ls=":", lw=0.3)
        ax.set_xlabel("Longitude")
        ax.set_ylabel("Latitude")
    legend = [
        Line2D([0], [0], color=C["green"], lw=2, label="Feasible at I0 (executed)"),
        Line2D([0], [0], color=C["blue"], lw=2, label="Newly enabled (executed)"),
        Line2D([0], [0], color=C["vermillion"], lw=2, ls=":", label="Infeasible (reference route)"),
        Line2D([0], [0], color=C["orange"], lw=2, ls="--", label="Unresolved LIMIT"),
        Line2D([0], [0], marker="o", color="w", markerfacecolor=C["orange"], markersize=7, label="Visited charger"),
    ]
    axes[-1].legend(handles=legend, fontsize=6.5, loc="lower right")
    fig.suptitle(
        "R-Figure 2 — Geographic feasibility with executed routes (eActros stressed)",
        fontsize=12,
    )
    pd.DataFrame(export_rows).to_csv(SRC / "R-Fig2_feasibility_by_infra.csv", index=False)
    (FIG / "R-Figure2_description.md").write_text(
        "R-Figure 2: Feasible missions plot executed DRIVE arcs from solution traces; "
        "infeasible missions use an explicitly labeled shortest-path reference. "
        "Arrows show direction; orange markers show visited chargers.\n",
        encoding="utf-8",
    )
    base = FIG / "R-Figure2_geographic_feasibility"
    fig.savefig(base.with_suffix(".pdf"))
    fig.savefig(base.with_suffix(".png"), dpi=400)
    fig.savefig(base.with_suffix(".svg"))
    plt.close(fig)
    print("Wrote", base, "rows", len(export_rows))


if __name__ == "__main__":
    main()
