#!/usr/bin/env python3
"""R-Figure 5 — Multi-panel operational profiles (map, elevation, SOC, time)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts/final_evidence"))
from elevation_profiles import reconstruct_od_elevation  # noqa: E402

FE = ROOT / "results/final_evidence"
FIG = FE / "figures/results"
SRC = FIG / "source_data"
C = {"blue": "#0072B2", "orange": "#E69F00", "vermillion": "#D55E00", "green": "#009E73", "grey": "#999999"}

PICK = [
    ("casa_marrakech", "I1_benguerir_ca"),
    ("casa_agadir", "I1_benguerir_ca"),
]


def _actions(tr):
    if tr is None or (isinstance(tr, float) and pd.isna(tr)):
        return []
    return json.loads(tr) if isinstance(tr, str) else tr


def main() -> None:
    FIG.mkdir(parents=True, exist_ok=True)
    SRC.mkdir(parents=True, exist_ok=True)
    m = pd.read_csv(FE / "experiments/primary_comparison/primary_missions.csv")
    nodes = pd.read_csv(ROOT / "data/processed/multiroute/nodes.csv").set_index("osm_node_id")
    elev_dir = ROOT / "data/processed/multiroute/elevation"

    for od, infra in PICK:
        row = m[
            (m.vehicle_key == "eactros_600")
            & (m.soc_scenario == "stressed_mixed")
            & (m.infra_config_id == infra)
            & (m.od_id == od)
            & (m.operationally_served == True)  # noqa: E712
        ]
        if not len(row):
            continue
        r = row.iloc[0]
        acts = _actions(r.action_trace_json)
        fig, axes = plt.subplots(2, 2, figsize=(11, 7.5), constrained_layout=True)
        fig.patch.set_facecolor("white")

        # (a) route map from executed arcs densified coords when available
        ax = axes[0, 0]
        xs, ys = [], []
        charge_xy = []
        cum = 0.0
        for a in acts:
            typ = a.get("action_type") or a.get("type")
            if typ == "DRIVE" and a.get("arc_id"):
                p = elev_dir / f"arc_{a['arc_id']}.json"
                if p.exists():
                    raw = json.loads(p.read_text(encoding="utf-8"))
                    coords = raw.get("coords_lonlat") or []
                    xs.extend([c[0] for c in coords])
                    ys.extend([c[1] for c in coords])
                cum += float(a.get("length_m") or 0)
            if typ == "CHARGE":
                # approximate with last coord
                if xs:
                    charge_xy.append((xs[-1], ys[-1], float(a.get("dt_s") or 0) / 60.0))
        if xs:
            ax.plot(xs, ys, color=C["blue"], lw=1.5)
            for x, y, dur in charge_xy:
                ax.scatter([x], [y], c=C["orange"], s=40, zorder=5)
                ax.text(x, y, f" {dur:.0f} min", fontsize=7, color=C["orange"])
        ax.set_title("(a) Executed route + charge sites")
        ax.set_aspect("equal", adjustable="box")
        ax.grid(True, ls=":", lw=0.3)

        # (b) ordered elevation
        ax = axes[0, 1]
        elev = reconstruct_od_elevation(od, method="shortest_distance")
        if len(elev.distances_m):
            ax.plot(elev.distances_m / 1000.0, elev.elevations_m, color=C["green"], lw=1.2)
            ax.set_xlabel("Distance (km)")
            ax.set_ylabel("Elevation (m)")
            elev.to_frame().to_csv(SRC / f"R-Fig5_{od}_elevation.csv", index=False)
        ax.set_title(
            f"(b) Ordered elevation (+{elev.cum_gain_m:.0f}/−{elev.cum_loss_m:.0f} m)"
        )
        ax.grid(True, ls=":", lw=0.4)

        # (c) SOC vs distance — macro endpoints only (no fake interpolation claim)
        ax = axes[1, 0]
        dist, soc_end, soc_min = [0.0], [], []
        d = 0.0
        init = float(r.soc_frac)
        soc_end.append(init)
        soc_min.append(init)
        charge_x = []
        for a in acts:
            typ = a.get("action_type") or a.get("type")
            if typ == "DRIVE":
                d += float(a.get("length_m") or 0) / 1000.0
                dist.append(d)
                soc_end.append(float(a.get("soc_after", soc_end[-1])))
                sm = a.get("soc_min_along")
                soc_min.append(float(sm) if sm is not None and pd.notna(sm) else soc_end[-1])
            if typ == "CHARGE":
                charge_x.append(d)
                dist.append(d)
                soc_end.append(float(a.get("soc_after", soc_end[-1])))
                soc_min.append(soc_end[-1])
        ax.plot(dist, soc_end, color=C["blue"], lw=1.4, marker="o", markersize=3, label="SOC after action")
        ax.plot(dist, soc_min, color=C["vermillion"], lw=1.0, ls="--", label="soc_min_along (when present)")
        ax.axhline(0.1, color=C["grey"], ls=":", lw=1, label="reserve 0.10")
        for x in charge_x:
            ax.axvline(x, color=C["orange"], ls=":", lw=1)
        ax.set_ylim(0, 1)
        ax.set_xlabel("Distance (km)")
        ax.set_ylabel("SOC")
        ax.set_title("(c) Battery SOC (macro action endpoints)")
        ax.legend(fontsize=6)
        ax.grid(True, ls=":", lw=0.4)
        pd.DataFrame({"distance_km": dist, "soc_after": soc_end, "soc_min_along": soc_min}).to_csv(
            SRC / f"R-Fig5_{od}_soc.csv", index=False
        )

        # (d) cumulative time with charge/wait/break
        ax = axes[1, 1]
        t_h, labels = [0.0], []
        t = 0.0
        colors = []
        for a in acts:
            typ = a.get("action_type") or a.get("type")
            dt = float(a.get("dt_s") or 0) / 3600.0
            t += dt
            t_h.append(t)
            if typ == "DRIVE":
                colors.append(C["blue"])
            elif typ == "CHARGE":
                colors.append(C["orange"])
            else:
                colors.append(C["grey"])
        for i in range(len(colors)):
            ax.plot([i, i + 1], [t_h[i], t_h[i + 1]], color=colors[i], lw=2)
        ax.set_xlabel("Action index")
        ax.set_ylabel("Cumulative time (h)")
        ax.set_title(
            f"(d) Journey time (drive/charge/other) | "
            f"charge={r.charge_min_phys} min wait={r.wait_min_phys} min"
        )
        ax.grid(True, ls=":", lw=0.4)

        fig.suptitle(
            f"R-Figure 5 — {od} | {infra} | eActros stressed | "
            f"min_soc={r.min_soc:.3f}",
            fontsize=11,
        )
        base = FIG / f"R-Figure5_{od}_operational_profile"
        fig.savefig(base.with_suffix(".pdf"))
        fig.savefig(base.with_suffix(".png"), dpi=400)
        fig.savefig(base.with_suffix(".svg"))
        plt.close(fig)
        print("Wrote", base)

    # Keep combined legacy filename as casa_agadir panel pointer note
    (FIG / "R-Figure5_description.md").write_text(
        "R-Figure 5 multipanel: executed route map, ordered DEM elevation, SOC at action "
        "endpoints (with soc_min_along when available; not interpolated continuous samples), "
        "and cumulative journey time. Per-OD exports: R-Figure5_<od>_operational_profile.*\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
