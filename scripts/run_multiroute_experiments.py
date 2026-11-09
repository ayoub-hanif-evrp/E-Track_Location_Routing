#!/usr/bin/env python
"""Task 05A — Multi-route Moroccan MRLS experiments on the decision graph."""

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
    build_od_routing_instance,
    load_decision_graph,
    load_multiroute_pilot_config,
)
from morocco_etruck.optimization.problem import StationData  # noqa: E402
from morocco_etruck.optimization.reference_solver import solve_reference  # noqa: E402
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


def _write_map(path_df: pd.DataFrame, G, out_png: Path, out_geo: Path) -> None:
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
    ax.set_title("Task 05A multi-route path alternatives (OSM; not HGV-certified)")
    ax.set_xlabel("Longitude")
    ax.set_ylabel("Latitude")
    ax.set_aspect("equal", adjustable="datalim")
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    out_png.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_png, dpi=140)
    plt.close(fig)
    out_geo.write_text(json.dumps({"type": "FeatureCollection", "features": features}, indent=2), encoding="utf-8")


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
    _write_map(
        path_df,
        G,
        fig_dir / "multiroute_path_alternatives.png",
        fig_dir / "multiroute_path_alternatives.geojson",
    )

    rows = []
    for od in cfg.raw.get("od_pairs") or []:
        od_id = str(od["id"])
        origin = f"{od_id}__o"
        dest = f"{od_id}__d"
        if origin not in dec.get("decision_nodes", {}) or dest not in dec.get("decision_nodes", {}):
            # Fallback: city-level names
            print(f"Skip {od_id}: terminals missing in decision graph", flush=True)
            continue

        short = _shortest_row(path_df, od_id)
        n_alts = int((path_df["od_id"] == od_id).sum())

        for mode, e_init, with_charger in (
            ("full_battery", int(cfg.raw.get("E_truck_init", 600)), False),
            ("low_battery", 200, False),
            ("low_battery_hyp_charger", 200, True),
        ):
            stations = None
            active: set[str] = set()
            if with_charger:
                # Hypothetical charger on first route mid-node (not verified HGV access)
                mid = f"R0_{od_id}"
                stations = {
                    mid: StationData(
                        node=mid,
                        power_kw=350.0,
                        eta=0.95,
                        price_cents_per_grid_kwh=20,
                        compatible=True,
                        hypothetical_access=True,
                    )
                }
                active = {mid}
            t_prep = time.perf_counter()
            inst = build_od_routing_instance(
                cfg=cfg,
                od_id=od_id,
                origin_name=origin,
                dest_name=dest,
                path_rows=path_rows,
                E_truck_init=e_init,
                E_truck_cap=int(cfg.raw.get("E_truck_cap", 600)),
                E_truck_min=int(cfg.raw.get("E_truck_min", 60)),
                active_stations=active,
                stations=stations,
            )
            prep_s = time.perf_counter() - t_prep

            t0 = time.perf_counter()
            result = solve_mrls(
                inst,
                use_dominance=True,
                max_seconds=float(cfg.raw.get("solver", {}).get("max_seconds", 60)),
                max_expansions=int(cfg.raw.get("solver", {}).get("max_expansions", 500000)),
            )
            solve_s = time.perf_counter() - t0

            disc_ok = False
            if result.status == SolverStatus.OPTIMAL:
                rep = replay_solution(inst, result.actions, expected_cost=result.objective)
                disc_ok = bool(rep.ok)

            ref_status = ""
            ref_match = ""
            if len(inst.arcs) <= 12 and inst.E_truck_cap <= 200:
                ref = solve_reference(inst, max_states=5_000_000)
                ref_status = ref.status.value if hasattr(ref.status, "value") else str(ref.status)
                ref_match = str(result.status == ref.status and result.objective == ref.objective)

            chose_shortest = ""
            if result.status == SolverStatus.OPTIMAL and short is not None and result.path_nodes:
                # Path index encoded as R{i}_od
                mid = result.path_nodes[1] if len(result.path_nodes) >= 3 else ""
                if mid.startswith("R0_"):
                    chose_shortest = "true"
                elif mid.startswith("R"):
                    chose_shortest = "false"

            rows.append(
                {
                    "od_id": od_id,
                    "mode": mode,
                    "E_truck_init": e_init,
                    "n_path_alternatives": n_alts,
                    "shortest_length_m": None if short is None else float(short["length_m"]),
                    "n_route_arcs": len(inst.arcs),
                    "n_nodes": len(inst.nodes),
                    "mrls_status": result.status.value,
                    "mrls_objective": result.objective,
                    "mrls_path": "->".join(result.path_nodes),
                    "chose_shortest_distance_route": chose_shortest,
                    "discrete_replay_ok": disc_ok,
                    "prep_sec": prep_s,
                    "solve_sec": solve_s,
                    "ref_status": ref_status,
                    "ref_match": ref_match,
                    "hgv_uncertainty": "unknown_tags_retained_explicit_no_filtered",
                    "claim_scope": "selected_verified_path_set_only",
                }
            )
            print(
                f"{od_id}/{mode}: alts={n_alts} status={result.status.value} "
                f"obj={result.objective} shortest_route={chose_shortest} t={solve_s:.2f}s",
                flush=True,
            )

    out = ROOT / cfg.raw.get("outputs", {}).get("experiments_csv", "results/multiroute_experiments.csv")
    out.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(out, index=False)
    print(f"Wrote {out} ({len(rows)} rows)", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
