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
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts/final_evidence"))
from reconstruct_executed_routes import _elevation_slice  # noqa: E402

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


def _node_xy(node: str, nodes: pd.DataFrame, cand: pd.DataFrame):
    n = str(node)
    if n.startswith("J"):
        try:
            nid = int(n[1:])
            if nid in nodes.index:
                return float(nodes.loc[nid, "lon"]), float(nodes.loc[nid, "lat"])
        except Exception:
            pass
    # directional / station keys
    key = n if n.startswith("y_") else f"y_{n}" if "_" in n else n
    for col in ("retained_headline_key_guess", "site_key", "official_name"):
        if col in cand.columns:
            hit = cand[cand[col].astype(str).str.contains(n.replace("y_", ""), case=False, na=False)]
            if len(hit):
                return float(hit.iloc[0].lon), float(hit.iloc[0].lat)
    return None


def _load_geom_cache(audit_path: Path) -> dict[str, list]:
    cache: dict[str, list] = {}
    if not audit_path.exists():
        return cache
    audit = pd.read_csv(audit_path)
    for _, r in audit.iterrows():
        aid = str(r.arc_id)
        try:
            coords = json.loads(r.lon_lat_json) if isinstance(r.lon_lat_json, str) else []
        except Exception:
            coords = []
        if len(coords) >= 2 and (aid not in cache or len(coords) > len(cache[aid])):
            cache[aid] = coords
    return cache


def _parent_meta(aid: str, audit_path: Path) -> tuple[str, float]:
    if not audit_path.exists():
        return "", 0.0
    audit = pd.read_csv(audit_path)
    hit = audit[audit.arc_id.astype(str) == aid]
    if not len(hit):
        return "", 0.0
    r = hit.iloc[0]
    return str(r.get("parent_arc_id") or ""), float(r.get("macro_s0_m") or 0.0)


def _executed_elevation(acts, elev_dir: Path, audit_path: Path):
    """Elevation vs distance on executed route; parent-slice DEM when child JSON absent (P1/P3 policy)."""
    xs, zs, rows = [], [], []
    offset = 0.0
    gain = loss = 0.0
    missing = []
    for a in acts:
        typ = a.get("action_type") or a.get("type")
        if typ != "DRIVE":
            continue
        aid = str(a.get("arc_id") or "")
        length = float(a.get("length_m") or 0.0)
        parent, s0 = _parent_meta(aid, audit_path)
        elev = _elevation_slice(aid, parent, s0, length)
        src = elev["terrain_source"]
        d_loc = np.asarray(elev["distances_m"], dtype=float)
        z = np.asarray(elev["elevations_m"], dtype=float)
        if len(d_loc) >= 2 and len(z) >= 2 and elev.get("dem_ok"):
            span = float(d_loc[-1]) if float(d_loc[-1]) > 1e-6 else length
            scale = (length / span) if span > 1e-6 else 1.0
            d_use = d_loc * scale + offset
            xs.extend(d_use.tolist())
            zs.extend(z.tolist())
            dz = np.diff(z.astype(float))
            gain += float(dz[dz > 0].sum()) if len(dz) else 0.0
            loss += float((-dz[dz < 0]).sum()) if len(dz) else 0.0
            for d, zz in zip(d_use, z):
                rows.append(
                    {
                        "distance_m": float(d),
                        "distance_km": float(d) / 1000.0,
                        "elevation_m": float(zz),
                        "arc_id": aid,
                        "profile": src,
                    }
                )
            offset += length
            continue
        missing.append(aid)
        xs.extend([offset, offset + length])
        zs.extend([np.nan, np.nan])
        rows.append(
            {
                "distance_m": offset,
                "distance_km": offset / 1000.0,
                "elevation_m": np.nan,
                "arc_id": aid,
                "profile": src or "missing",
            }
        )
        rows.append(
            {
                "distance_m": offset + length,
                "distance_km": (offset + length) / 1000.0,
                "elevation_m": np.nan,
                "arc_id": aid,
                "profile": src or "missing",
            }
        )
        offset += length
    return {
        "distances_m": np.asarray(xs, dtype=float),
        "elevations_m": np.asarray(zs, dtype=float),
        "path_length_m": offset,
        "cum_gain_m": gain,
        "cum_loss_m": loss,
        "missing_arc_ids": missing,
        "frame": pd.DataFrame(rows),
    }


def main() -> None:
    FIG.mkdir(parents=True, exist_ok=True)
    SRC.mkdir(parents=True, exist_ok=True)
    panel = FE / "experiments/primary_i0_i3_panel/primary_i0_i3_missions.csv"
    mpath = panel if panel.exists() else FE / "experiments/primary_comparison/primary_missions.csv"
    m = pd.read_csv(mpath)
    elev_dir = ROOT / "data/processed/multiroute/elevation"
    audit_path = FE / "experiments/executed_route_geometry/executed_arc_geometry_audit.csv"
    geom_cache = _load_geom_cache(audit_path)
    nodes = pd.read_csv(ROOT / "data/processed/multiroute/nodes.csv").set_index("osm_node_id")
    cand = pd.read_csv(FE / "tables/dataset/D-T04_candidate_inventory.csv")
    cand = cand[pd.to_numeric(cand.lon, errors="coerce").notna()]

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
        drive_arcs = [
            {
                "arc_id": str(a.get("arc_id")),
                "length_m": float(a.get("length_m") or 0),
                "u": a.get("u"),
                "v": a.get("v"),
            }
            for a in acts
            if (a.get("action_type") or a.get("type")) == "DRIVE" and a.get("arc_id")
        ]
        fig, axes = plt.subplots(2, 2, figsize=(11, 7.5), constrained_layout=True)
        fig.patch.set_facecolor("white")

        # (a) map: densified DEM coords when present; else u/v node waypoints
        ax = axes[0, 0]
        xs, ys = [], []
        charge_xy = []
        missing_geom = []
        for a in acts:
            typ = a.get("action_type") or a.get("type")
            if typ == "DRIVE" and a.get("arc_id"):
                aid = str(a["arc_id"])
                placed = False
                coords = geom_cache.get(aid) or []
                if not coords:
                    p = elev_dir / f"arc_{aid}.json"
                    if p.exists():
                        raw = json.loads(p.read_text(encoding="utf-8"))
                        coords = raw.get("coords_lonlat") or []
                if not coords:
                    parent, s0 = _parent_meta(aid, audit_path)
                    elev = _elevation_slice(aid, parent, s0, float(a.get("length_m") or 0))
                    coords = elev.get("coords_lonlat") or []
                if coords:
                    xs.extend([float(c[0]) for c in coords])
                    ys.extend([float(c[1]) for c in coords])
                    placed = True
                if not placed:
                    missing_geom.append(aid)
                    for node in (a.get("u"), a.get("v")):
                        xy = _node_xy(str(node), nodes, cand) if node is not None else None
                        if xy:
                            xs.append(xy[0])
                            ys.append(xy[1])
            if typ == "CHARGE":
                site = str(a.get("site") or a.get("node") or "")
                xy = _node_xy(site, nodes, cand)
                if xy:
                    charge_xy.append((xy[0], xy[1], float(a.get("dt_s") or 0) / 60.0, site))
                elif xs:
                    charge_xy.append((xs[-1], ys[-1], float(a.get("dt_s") or 0) / 60.0, site))
        if xs:
            ax.plot(xs, ys, color=C["blue"], lw=1.5)
            for x, y, dur, site in charge_xy:
                ax.scatter([x], [y], c=C["orange"], s=40, zorder=5)
                ax.text(x, y, f" {site or 'charge'} {dur:.0f} min", fontsize=7, color=C["orange"])
        if missing_geom:
            ax.text(
                0.02,
                0.02,
                f"arcs without densified geom: {len(missing_geom)} (u/v waypoints used)",
                transform=ax.transAxes,
                fontsize=7,
                color=C["vermillion"],
            )
        ax.set_title("(a) Executed route + directional charge sites")
        ax.set_aspect("equal", adjustable="box")
        ax.grid(True, ls=":", lw=0.3)

        # (b) elevation on SAME executed distance axis (NaN gaps if DEM missing)
        ax = axes[0, 1]
        elev = _executed_elevation(acts, elev_dir, audit_path)
        if len(elev["distances_m"]):
            dkm = elev["distances_m"] / 1000.0
            ax.plot(dkm, elev["elevations_m"], color=C["green"], lw=1.2)
            ax.set_xlabel("Distance along executed route (km)")
            ax.set_ylabel("Elevation (m)")
            elev["frame"].to_csv(SRC / f"R-Fig5_{od}_elevation.csv", index=False)
        miss_n = len(elev["missing_arc_ids"])
        ax.set_title(
            f"(b) Executed-route elevation (+{elev['cum_gain_m']:.0f}/−{elev['cum_loss_m']:.0f} m)\n"
            f"trace_len={elev['path_length_m']/1000.0:.1f} km; missing DEM arcs={miss_n}"
        )
        ax.grid(True, ls=":", lw=0.4)
        pd.DataFrame(drive_arcs).to_csv(SRC / f"R-Fig5_{od}_executed_arcs.csv", index=False)

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
        "R-Figure 5 multipanel: all panels use the same executed DRIVE arc sequence — map, "
        "executed-route distance axis, SOC at action endpoints (soc_min_along shown when "
        "present; not claimed as precise geographical samples), charging/waiting markers, "
        "and cumulative journey time. Elevation uses DEM profiles only where arc profiles "
        "exist; parent-slice DEM fills missing child profiles (same as solver). "
        "Missing arcs leave NaN gaps (distance still advances by trace length_m). "
        "Map uses P3 audit polylines, else child/parent DEM coords, else u/v waypoints.\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
