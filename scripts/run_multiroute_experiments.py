#!/usr/bin/env python
"""Task 05B — Physics-validated path-union multiroute MRLS experiments."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from morocco_etruck.optimization.label_setting import SolverStatus, solve_mrls  # noqa: E402
from morocco_etruck.optimization.multiroute_adapter import (  # noqa: E402
    build_physics_od_instance,
    load_decision_graph,
    load_multiroute_pilot_config,
)
from morocco_etruck.optimization.multiroute_physics import induce_od_decision_arcs  # noqa: E402
from morocco_etruck.optimization.multiroute_replay import continuous_replay_multiroute  # noqa: E402
from morocco_etruck.optimization.replay import replay_solution  # noqa: E402
from morocco_etruck.road_network import load_graph_from_csv  # noqa: E402


def _shortest_row(path_df: pd.DataFrame, od_id: str) -> pd.Series | None:
    sub = path_df[path_df["od_id"] == od_id]
    if sub.empty:
        return None
    short = sub[sub["method"] == "shortest_distance"]
    if short.empty:
        return sub.loc[sub["length_m"].idxmin()]
    return short.iloc[0]


def _write_map(path_df: pd.DataFrame, G, chargers_xy, out_png: Path, out_geo: Path) -> None:
    features = []
    fig, ax = plt.subplots(figsize=(9, 10))
    colors = ["#1f4e79", "#c45c26", "#2a9d8f", "#6d597a", "#e9c46a", "#264653"]
    for i, od_id in enumerate(sorted(path_df["od_id"].unique())):
        sub = path_df[path_df["od_id"] == od_id]
        for _, row in sub.iterrows():
            nodes = json.loads(row["node_path_json"])
            xs, ys = [], []
            for nid in nodes:
                if nid not in G.nodes:
                    continue
                xs.append(float(G.nodes[nid]["lon"]))
                ys.append(float(G.nodes[nid]["lat"]))
            if len(xs) < 2:
                continue
            lw = 2.2 if row["method"] == "shortest_distance" else 1.0
            ax.plot(xs, ys, color=colors[i % len(colors)], linewidth=lw, alpha=0.7)
            features.append(
                {
                    "type": "Feature",
                    "properties": {
                        "od_id": od_id,
                        "method": row["method"],
                        "length_m": row["length_m"],
                    },
                    "geometry": {"type": "LineString", "coordinates": list(zip(xs, ys))},
                }
            )
    for c in chargers_xy:
        ax.scatter([c["lon"]], [c["lat"]], c="red", s=40, zorder=5, marker="^")
        features.append(
            {
                "type": "Feature",
                "properties": {"charger": c["key"], "hypothetical": True},
                "geometry": {"type": "Point", "coordinates": [c["lon"], c["lat"]]},
            }
        )
    ax.set_title("Task 05B path-union alternatives + grounded hypothetical chargers")
    ax.set_xlabel("Longitude")
    ax.set_ylabel("Latitude")
    ax.set_aspect("equal", adjustable="datalim")
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    out_png.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_png, dpi=140)
    plt.close(fig)
    out_geo.write_text(json.dumps({"type": "FeatureCollection", "features": features}, indent=2), encoding="utf-8")


def _mission_rows(cfg) -> list[dict]:
    """Limited reproducible portfolio for Stage 6."""
    ods = list(cfg.raw.get("pilot_od_pairs") or ["casa_marrakech", "casa_agadir", "marrakech_agadir"])
    rows = []
    for od in ods:
        rows.append(
            {
                "mission_id": f"{od}_full_flat_nochg",
                "od_id": od,
                "E_truck_init": int(cfg.raw.get("E_truck_init", 600)),
                "with_chargers": False,
                "refrigeration_on": False,
                "terrain_mode": "flat",
                "weather_id": "cool",
                "gcm": "light",
            }
        )
        rows.append(
            {
                "mission_id": f"{od}_low_flat_nochg",
                "od_id": od,
                "E_truck_init": 200,
                "with_chargers": False,
                "refrigeration_on": False,
                "terrain_mode": "flat",
                "weather_id": "cool",
                "gcm": "light",
            }
        )
        rows.append(
            {
                "mission_id": f"{od}_low_flat_chg",
                "od_id": od,
                "E_truck_init": 200,
                "with_chargers": True,
                "refrigeration_on": False,
                "terrain_mode": "flat",
                "weather_id": "cool",
                "gcm": "light",
            }
        )
    # Refrigeration contrast on one OD
    od0 = ods[0]
    rows.append(
        {
            "mission_id": f"{od0}_full_flat_refrig",
            "od_id": od0,
            "E_truck_init": int(cfg.raw.get("E_truck_init", 600)),
            "with_chargers": False,
            "refrigeration_on": True,
            "terrain_mode": "flat",
            "weather_id": "cool",
            "gcm": "light",
        }
    )
    # Heavy GCM on one OD
    rows.append(
        {
            "mission_id": f"{od0}_full_flat_heavy",
            "od_id": od0,
            "E_truck_init": int(cfg.raw.get("E_truck_init", 600)),
            "with_chargers": False,
            "refrigeration_on": False,
            "terrain_mode": "flat",
            "weather_id": "cool",
            "gcm": "heavy",
        }
    )
    # Grid sensitivity on smallest OD
    rows.append(
        {
            "mission_id": f"{od0}_full_flat_q1",
            "od_id": od0,
            "E_truck_init": int(cfg.raw.get("E_truck_init", 600)),
            "with_chargers": False,
            "refrigeration_on": False,
            "terrain_mode": "flat",
            "weather_id": "cool",
            "gcm": "light",
            "energy_quantum_kwh": int(cfg.raw.get("energy_quantum_sensitivity_kwh", 1)),
        }
    )
    return rows


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--config",
        type=Path,
        default=ROOT / "configs/optimization/multiroute_pilot.yaml",
    )
    args = p.parse_args()
    cfg = load_multiroute_pilot_config(args.config, root=ROOT)
    path_df = pd.read_csv(cfg.path_alternatives_csv)
    path_rows = path_df.to_dict(orient="records")
    dec = load_decision_graph(cfg.decision_graph_path)

    print("Loading multiroute graph for map…", flush=True)
    G = load_graph_from_csv(cfg.nodes_csv, cfg.edges_csv)
    fig_dir = ROOT / cfg.raw.get("outputs", {}).get("figures_dir", "reports/figures")

    # Collect charger coords for map (best-effort from candidate sites)
    sites = pd.read_csv(cfg.candidate_sites_csv)
    chargers_xy = []
    for token in ("SETTAT", "BENGUERIR", "AMSKROUD"):
        hits = sites[
            sites["official_name"].astype(str).str.upper().str.contains(token, regex=False)
            & (sites["directed_access_status"].astype(str) == "entrance_and_exit")
        ]
        if not hits.empty:
            r = hits.iloc[0]
            chargers_xy.append(
                {"key": token.lower(), "lon": float(r["lon"]), "lat": float(r["lat"])}
            )
    pilot_ods = list(cfg.raw.get("pilot_od_pairs") or [])
    map_df = path_df[path_df["od_id"].isin(pilot_ods)] if pilot_ods else path_df
    _write_map(
        map_df,
        G,
        chargers_xy,
        fig_dir / "multiroute_physics_paths.png",
        fig_dir / "multiroute_physics_paths.geojson",
    )

    rows = []
    for mission in _mission_rows(cfg):
        od_id = mission["od_id"]
        short = _shortest_row(path_df, od_id)
        n_alts = int((path_df["od_id"] == od_id).sum())
        gcm_kg = float(
            cfg.raw.get("physics", {}).get("gcm_heavy_kg", 40000.0)
            if mission.get("gcm") == "heavy"
            else cfg.gcm_kg
        )
        # Temporarily override gcm on cfg copy
        cfg.gcm_kg = gcm_kg

        t_prep = time.perf_counter()
        try:
            inst, ctx, station_notes = build_physics_od_instance(
                cfg=cfg,
                root=ROOT,
                od_id=od_id,
                path_rows=path_rows,
                E_truck_init=int(mission["E_truck_init"]),
                E_truck_cap=int(cfg.raw.get("E_truck_cap", 600)),
                E_truck_min=int(cfg.raw.get("E_truck_min", 60)),
                refrigeration_on=bool(mission["refrigeration_on"]),
                weather_id=str(mission.get("weather_id", "cool")),
                with_chargers=bool(mission["with_chargers"]),
                energy_quantum_kwh=mission.get("energy_quantum_kwh"),
                terrain_mode=str(mission.get("terrain_mode") or cfg.terrain_mode),
            )
        except Exception as exc:  # noqa: BLE001 — report mission failure honestly
            prep_s = time.perf_counter() - t_prep
            rows.append(
                {
                    "od_id": od_id,
                    "mission_id": mission["mission_id"],
                    "mrls_status": "BUILD_ERROR",
                    "error": str(exc),
                    "prep_sec": prep_s,
                    "claim_scope": "path_union_of_verified_alternatives_only",
                }
            )
            print(f"{mission['mission_id']}: BUILD_ERROR {exc}", flush=True)
            continue
        prep_s = time.perf_counter() - t_prep

        t0 = time.perf_counter()
        result = solve_mrls(
            inst,
            use_dominance=True,
            max_seconds=float(cfg.raw.get("solver", {}).get("max_seconds", 90)),
            max_expansions=int(cfg.raw.get("solver", {}).get("max_expansions", 800000)),
        )
        solve_s = time.perf_counter() - t0

        disc_ok = False
        cont_ok = False
        cont_reason = ""
        osm_path = []
        arc_ids = []
        length_m = None
        duration_s = None
        charge_events = []
        min_soc = None
        final_soc_kwh = None
        truck_energy_est = None
        chose_shortest = ""

        if result.status == SolverStatus.OPTIMAL:
            rep = replay_solution(inst, result.actions, expected_cost=result.objective)
            disc_ok = bool(rep.ok)
            crep, extras = continuous_replay_multiroute(
                ctx,
                inst,
                result.actions,
                discrete_cost=result.objective,
                discrete_t=result.final_label.t if result.final_label else None,
                discrete_E_truck=result.final_label.E_truck if result.final_label else None,
            )
            cont_ok = bool(crep.ok)
            cont_reason = crep.reason or ""
            osm_path = extras.osm_node_path
            arc_ids = extras.arc_ids
            length_m = extras.length_m
            duration_s = crep.continuous_duration_s
            charge_events = extras.charge_events
            min_soc = crep.min_soc
            final_soc_kwh = crep.continuous_E_truck_kwh
            if result.final_label is not None:
                truck_energy_est = float(inst.E_truck_init - result.final_label.E_truck)
            if short is not None and length_m is not None:
                # Compare reconstructed length to shortest alternative length
                ratio = float(length_m) / max(float(short["length_m"]), 1.0)
                chose_shortest = "true" if ratio <= 1.02 else "false"

        # Flat shortest-distance reference length on path set
        short_len = None if short is None else float(short["length_m"])

        # Induced graph size
        try:
            ind_arcs, _, _, _ = induce_od_decision_arcs(dec, path_rows, od_id)
            n_ind = len(ind_arcs)
        except Exception:
            n_ind = len(inst.arcs)

        power_ok = True
        if result.status == SolverStatus.OPTIMAL:
            for act in result.actions:
                if act.get("type") == "DRIVE" and act.get("table") and act.get("reason"):
                    power_ok = False

        rows.append(
            {
                "od_id": od_id,
                "mission_id": mission["mission_id"],
                "E_truck_init": mission["E_truck_init"],
                "n_path_alternatives": n_alts,
                "shortest_length_m": short_len,
                "n_decision_arcs": len(inst.arcs),
                "n_induced_arcs_pre_split": n_ind,
                "n_nodes": len(inst.nodes),
                "selected_path_nodes": "->".join(result.path_nodes),
                "selected_osm_node_path_json": json.dumps(osm_path),
                "selected_arc_ids_json": json.dumps(arc_ids),
                "road_distance_m": length_m,
                "travel_duration_s": duration_s,
                "truck_energy_kwh_est": truck_energy_est,
                "refrigeration_on": mission["refrigeration_on"],
                "charge_events_json": json.dumps(charge_events),
                "final_E_truck_kwh": final_soc_kwh,
                "min_soc": min_soc,
                "trailer_soc": "",
                "motor_power_feasible": power_ok,
                "mrls_status": result.status.value,
                "mrls_objective": result.objective,
                "chose_shortest_distance_route": chose_shortest,
                "discrete_replay_ok": disc_ok,
                "continuous_replay_ok": cont_ok,
                "continuous_replay_reason": cont_reason,
                "energy_quantum_kwh": inst.energy_quantum_kwh,
                "terrain_mode": mission.get("terrain_mode"),
                "gcm_kg": gcm_kg,
                "with_chargers": mission["with_chargers"],
                "station_notes": ";".join(station_notes),
                "prep_sec": prep_s,
                "solve_sec": solve_s,
                "hgv_uncertainty": "unknown_tags_retained_explicit_no_filtered",
                "claim_scope": "path_union_of_verified_alternatives_only",
                "labels_expanded": getattr(result.stats, "expanded", None)
                if result.stats
                else None,
            }
        )
        print(
            f"{mission['mission_id']}: status={result.status.value} obj={result.objective} "
            f"shortest={chose_shortest} cont_replay={cont_ok} "
            f"prep={prep_s:.1f}s solve={solve_s:.2f}s arcs={len(inst.arcs)}",
            flush=True,
        )

    out = ROOT / cfg.raw.get("outputs", {}).get(
        "experiments_csv", "results/multiroute_physics_experiments.csv"
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(out, index=False)
    print(f"Wrote {out} ({len(rows)} rows)", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
