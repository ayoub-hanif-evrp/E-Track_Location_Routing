#!/usr/bin/env python3
"""P1 — Canonical executed-route geometry + DEM reconstruction.

Uses the same parent-arc DEM slicing as the solver (`build_macro_with_terrain`):
  1. arc_{child}.json if present
  2. else arc_{parent}.json windowed at macro_s0_m
  3. else dem_unavailable (explicit flat fallback in physics)

Does not invent straight-line geography for missing arcs.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "scripts/final_evidence"))

import run_stage_c_hos_national as stage_c  # noqa: E402
from morocco_etruck.energy.terrain import load_profile  # noqa: E402
from morocco_etruck.optimization.multiroute_physics import (  # noqa: E402
    build_macro_with_terrain,
    try_load_macro_dem,
)
from morocco_etruck.road_network import load_graph_from_csv  # noqa: E402

OUT = ROOT / "results/final_evidence/experiments/executed_route_geometry"
TAB = ROOT / "results/final_evidence/tables/results"
FIG = ROOT / "results/final_evidence/figures/results"
SRC = FIG / "source_data"
ELEV = ROOT / "data/processed/multiroute/elevation"
PILOT = ROOT / "configs/optimization/multiroute_pilot.yaml"


def _actions(tr) -> list[dict]:
    if tr is None or (isinstance(tr, float) and pd.isna(tr)):
        return []
    return json.loads(tr) if isinstance(tr, str) else tr


def _drive_actions(acts: list[dict]) -> list[dict]:
    return [a for a in acts if (a.get("action_type") or a.get("type")) == "DRIVE" and a.get("arc_id")]


def _polyline_from_path_nodes(path_nodes: list[int], nodes: pd.DataFrame) -> tuple[list[float], list[float], list[int]]:
    xs, ys, missing = [], [], []
    for nid in path_nodes:
        if int(nid) in nodes.index:
            xs.append(float(nodes.loc[int(nid), "lon"]))
            ys.append(float(nodes.loc[int(nid), "lat"]))
        else:
            missing.append(int(nid))
    return xs, ys, missing


def _elevation_slice(arc_id: str, parent_arc_id: str, macro_s0: float, length_m: float) -> dict[str, Any]:
    """Mirror solver DEM resolution for visualization."""
    child = try_load_macro_dem(ELEV, arc_id)
    if child is not None:
        dist = np.asarray(child.distances_m, dtype=float)
        elev = np.asarray(child.elevations_m, dtype=float)
        coords = []
        # coords may live on raw file
        raw_p = ELEV / f"arc_{arc_id}.json"
        if raw_p.exists():
            coords = json.loads(raw_p.read_text(encoding="utf-8")).get("coords_lonlat") or []
        return {
            "terrain_source": "dem_per_arc",
            "distances_m": dist - float(dist[0]) if len(dist) else dist,
            "elevations_m": elev,
            "coords_lonlat": coords,
            "dem_ok": True,
        }
    if parent_arc_id:
        parent = try_load_macro_dem(ELEV, parent_arc_id)
        if parent is not None:
            dist = np.asarray(parent.distances_m, dtype=float)
            elev = np.asarray(parent.elevations_m, dtype=float)
            # window [macro_s0, macro_s0+length]
            s0 = float(macro_s0)
            s1 = s0 + float(length_m)
            mask = (dist >= s0 - 1.0) & (dist <= s1 + 1.0)
            if not np.any(mask):
                # nearest-window fallback by cumulative
                mask = (dist >= s0) & (dist <= s1)
            d_w = dist[mask] - s0 if np.any(mask) else np.array([])
            z_w = elev[mask] if np.any(mask) else np.array([])
            raw_p = ELEV / f"arc_{parent_arc_id}.json"
            coords = []
            if raw_p.exists() and len(d_w):
                raw = json.loads(raw_p.read_text(encoding="utf-8"))
                all_c = raw.get("coords_lonlat") or []
                # approximate index alignment by distance fraction
                if all_c and len(dist) > 1:
                    fr0 = s0 / float(dist[-1]) if float(dist[-1]) > 0 else 0
                    fr1 = s1 / float(dist[-1]) if float(dist[-1]) > 0 else 1
                    i0 = int(max(0, min(len(all_c) - 1, round(fr0 * (len(all_c) - 1)))))
                    i1 = int(max(i0 + 1, min(len(all_c), round(fr1 * (len(all_c) - 1)) + 1)))
                    coords = all_c[i0:i1]
            return {
                "terrain_source": "dem_parent_slice",
                "distances_m": d_w,
                "elevations_m": z_w,
                "coords_lonlat": coords,
                "dem_ok": True,
                "parent_arc_id": parent_arc_id,
                "macro_s0_m": s0,
            }
    return {
        "terrain_source": "dem_unavailable",
        "distances_m": np.array([]),
        "elevations_m": np.array([]),
        "coords_lonlat": [],
        "dem_ok": False,
    }


def reconstruct_mission(
    *,
    prep,
    pilot,
    G,
    nodes: pd.DataFrame,
    acts: list[dict],
    od_id: str,
    infra: str,
    vehicle_key: str,
) -> tuple[list[dict], dict]:
    macros = getattr(prep.ctx, "macros_by_arc_id", {}) or {}
    # Also index DecisionArc-like info from macros meta
    rows = []
    total_len = 0.0
    geom_len = 0.0
    elev_cov_len = 0.0
    missing_geom = 0
    dem_unavailable = 0
    parent_slice = 0
    per_arc = 0
    offset = 0.0
    elev_rows = []

    for a in _drive_actions(acts):
        aid = str(a["arc_id"])
        length = float(a.get("length_m") or 0.0)
        total_len += length
        macro = macros.get(aid)
        parent_id = ""
        macro_s0 = 0.0
        path_nodes: list[int] = []
        terrain_note = "unknown"
        dem_ok_solver = None
        if macro is not None:
            meta = getattr(macro, "meta", {}) or {}
            parent_id = str(meta.get("parent_arc_id") or "")
            macro_s0 = float(meta.get("macro_s0_m") or 0.0)
            path_nodes = list(getattr(macro, "path_nodes", []) or [])
            terrain_note = str(meta.get("terrain_note") or "")
            dem_ok_solver = meta.get("dem_ok")
            if length <= 0:
                length = float(getattr(macro, "length_m", 0.0) or 0.0)
        elev = _elevation_slice(aid, parent_id, macro_s0, length)
        xs, ys, miss_nodes = _polyline_from_path_nodes(path_nodes, nodes)
        # Prefer densified coords from elevation when available
        coords = elev.get("coords_lonlat") or []
        if coords:
            xs = [float(c[0]) for c in coords]
            ys = [float(c[1]) for c in coords]
        if len(xs) >= 2:
            geom_len += length
        else:
            missing_geom += 1
        src = elev["terrain_source"]
        if src == "dem_per_arc":
            per_arc += 1
            elev_cov_len += length
        elif src == "dem_parent_slice":
            parent_slice += 1
            elev_cov_len += length
        else:
            dem_unavailable += 1

        d_loc = np.asarray(elev["distances_m"], dtype=float)
        z = np.asarray(elev["elevations_m"], dtype=float)
        if len(d_loc) and len(z):
            # scale local window to action length if needed
            span = float(d_loc[-1]) if float(d_loc[-1]) > 1e-6 else length
            scale = (length / span) if span > 1e-6 else 1.0
            for d, zz in zip(d_loc * scale + offset, z):
                elev_rows.append(
                    {
                        "od_id": od_id,
                        "infra_config_id": infra,
                        "arc_id": aid,
                        "distance_m": float(d),
                        "distance_km": float(d) / 1000.0,
                        "elevation_m": float(zz),
                        "terrain_source": src,
                    }
                )
        else:
            # honest gap
            elev_rows.append(
                {
                    "od_id": od_id,
                    "infra_config_id": infra,
                    "arc_id": aid,
                    "distance_m": offset,
                    "distance_km": offset / 1000.0,
                    "elevation_m": np.nan,
                    "terrain_source": src,
                }
            )
            elev_rows.append(
                {
                    "od_id": od_id,
                    "infra_config_id": infra,
                    "arc_id": aid,
                    "distance_m": offset + length,
                    "distance_km": (offset + length) / 1000.0,
                    "elevation_m": np.nan,
                    "terrain_source": src,
                }
            )

        rows.append(
            {
                "od_id": od_id,
                "vehicle_key": vehicle_key,
                "infra_config_id": infra,
                "arc_id": aid,
                "parent_arc_id": parent_id,
                "macro_s0_m": macro_s0,
                "u": a.get("u"),
                "v": a.get("v"),
                "length_m_trace": float(a.get("length_m") or 0.0),
                "length_m_macro": length,
                "n_path_nodes": len(path_nodes),
                "n_geom_points": len(xs),
                "n_missing_nodes": len(miss_nodes),
                "terrain_source_viz": src,
                "terrain_note_solver": terrain_note,
                "dem_ok_solver": dem_ok_solver,
                "geometry_complete": len(xs) >= 2,
                "lon_lat_json": json.dumps(list(zip(xs, ys))),
            }
        )
        offset += length

    summary = {
        "od_id": od_id,
        "vehicle_key": vehicle_key,
        "infra_config_id": infra,
        "n_drive_arcs": len(rows),
        "route_length_m": total_len,
        "geometry_coverage_frac": (geom_len / total_len) if total_len else 0.0,
        "elevation_dem_coverage_frac": (elev_cov_len / total_len) if total_len else 0.0,
        "n_missing_geometry": missing_geom,
        "n_dem_per_arc": per_arc,
        "n_dem_parent_slice": parent_slice,
        "n_dem_unavailable": dem_unavailable,
        "solver_flat_fallback_arcs": int(
            sum(1 for r in rows if str(r.get("terrain_note_solver")) == "dem_unavailable")
        ),
    }
    return rows, summary, elev_rows


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    TAB.mkdir(parents=True, exist_ok=True)
    SRC.mkdir(parents=True, exist_ok=True)

    panel = ROOT / "results/final_evidence/experiments/primary_i0_i3_panel/primary_i0_i3_missions.csv"
    prim_path = (
        panel
        if panel.exists()
        else ROOT / "results/final_evidence/experiments/primary_comparison/primary_missions.csv"
    )
    prim = pd.read_csv(prim_path)
    # Focus: eActros stressed (R-Fig2) across I0–I3 + key profile ODs
    focus = prim[
        (prim.vehicle_key == "eactros_600")
        & (prim.soc_scenario == "stressed_mixed")
        & (prim.operationally_served == True)  # noqa: E712
    ].copy()

    from morocco_etruck.optimization.multiroute_adapter import load_multiroute_pilot_config

    pilot = load_multiroute_pilot_config(PILOT, root=ROOT)
    G = load_graph_from_csv(pilot.nodes_csv, pilot.edges_csv)
    nodes = pd.read_csv(pilot.nodes_csv).set_index("osm_node_id")

    orig = stage_c._patch_realistic_speed_policy()
    all_arc_rows = []
    summaries = []
    elev_by_key = {}
    try:
        # Prepare once per OD
        ods = sorted(focus.od_id.unique())
        prep_by_od = {}
        for od in ods:
            # payload/soc from first matching mission
            hit = focus[focus.od_id == od].iloc[0]
            print(f"[P1] prepare {od}", flush=True)
            cfg, vehicle, context, masks = stage_c._prepare_one(
                vehicle_key="eactros_600",
                od_id=od,
                payload=float(hit.payload_kg),
                soc=float(hit.soc_frac),
                q=2,
            )
            mid = context["missions"][0].id
            prep_by_od[od] = context["prepared"][mid]

        for _, r in focus.iterrows():
            od = str(r.od_id)
            infra = str(r.infra_config_id)
            acts = _actions(r.action_trace_json)
            if not _drive_actions(acts):
                continue
            print(f"[P1] reconstruct {od} {infra}", flush=True)
            rows, summary, elev_rows = reconstruct_mission(
                prep=prep_by_od[od],
                pilot=pilot,
                G=G,
                nodes=nodes,
                acts=acts,
                od_id=od,
                infra=infra,
                vehicle_key="eactros_600",
            )
            all_arc_rows.extend(rows)
            summaries.append(summary)
            elev_by_key[(od, infra)] = elev_rows
            print(
                f"  geom_cov={summary['geometry_coverage_frac']:.3f} "
                f"elev_cov={summary['elevation_dem_coverage_frac']:.3f} "
                f"parent_slice={summary['n_dem_parent_slice']} "
                f"unavailable={summary['n_dem_unavailable']}",
                flush=True,
            )
    finally:
        import morocco_etruck.optimization.multiroute_placement_evaluation as mpe

        mpe.load_multiroute_pilot_config = orig

    arc_df = pd.DataFrame(all_arc_rows)
    sum_df = pd.DataFrame(summaries)
    arc_df.to_csv(OUT / "executed_arc_geometry_audit.csv", index=False)
    sum_df.to_csv(OUT / "executed_route_summary.csv", index=False)
    sum_df.to_csv(TAB / "R-T15_executed_route_geometry_audit.csv", index=False)

    # Export elevation for R-Fig5 focus ODs at I1
    for od in ("casa_marrakech", "casa_agadir"):
        key = (od, "I1_benguerir_ca")
        if key in elev_by_key:
            pd.DataFrame(elev_by_key[key]).to_csv(
                SRC / f"R-Fig5_{od}_elevation_executed.csv", index=False
            )
            pd.DataFrame(elev_by_key[key]).to_csv(
                SRC / f"R-Fig5_{od}_elevation.csv", index=False
            )

    notes = [
        "# Executed-route geometry and DEM audit (P1)",
        "",
        "Reconstruction uses solver macros (`macros_by_arc_id`) with the same DEM policy as physics:",
        "child profile → parent-slice → dem_unavailable.",
        "",
        "## Summary",
        "",
        sum_df.to_string(index=False),
        "",
        "## Interpretation",
        "",
        "- If `n_dem_parent_slice > 0` and `solver_flat_fallback_arcs == 0`, missing child JSON files",
        "  are a **visualization** issue; physics already used parent DEM slices.",
        "- If `solver_flat_fallback_arcs > 0`, terrain entered the solver as flat fallback —",
        "  affected missions may need selective re-runs after DEM repair.",
        "",
    ]
    (OUT / "P1_executed_route_geometry_notes.md").write_text("\n".join(notes), encoding="utf-8")
    print(sum_df.to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
