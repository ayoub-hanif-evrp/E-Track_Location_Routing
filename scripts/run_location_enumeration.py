#!/usr/bin/env python3
"""Task 04A — Exact 32-subset charger-placement enumeration."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from morocco_etruck.optimization.morocco_adapter import (  # noqa: E402
    build_mission_context,
    corridor_map_features,
    load_pilot_config,
)
from morocco_etruck.optimization.site_enumeration import run_enumeration  # noqa: E402
from morocco_etruck.optimization.placement_problem import load_placement_config  # noqa: E402
from morocco_etruck.road_network import load_graph_from_csv  # noqa: E402


def _write_placement_figure(
    geojson_path: Path,
    png_path: Path,
    selected_keys: set[str],
    title: str,
) -> None:
    fc = json.loads(geojson_path.read_text(encoding="utf-8"))
    fig, ax = plt.subplots(figsize=(8, 10))
    for feat in fc["features"]:
        props = feat.get("properties") or {}
        geom = feat["geometry"]
        if geom["type"] == "LineString":
            xs = [c[0] for c in geom["coordinates"]]
            ys = [c[1] for c in geom["coordinates"]]
            ax.plot(xs, ys, color="#1f4e79", linewidth=1.4, label="OSM baseline (not HGV-certified)")
        elif geom["type"] == "Point":
            key = props.get("key", "")
            selected = key in selected_keys
            ax.scatter(
                geom["coordinates"][0],
                geom["coordinates"][1],
                s=90 if selected else 40,
                c="#c45c26" if selected else "#999999",
                zorder=5,
                label=("selected hypothetical" if selected else "hypothetical candidate"),
            )
            ax.annotate(
                key + ("*" if selected else ""),
                (geom["coordinates"][0], geom["coordinates"][1]),
                textcoords="offset points",
                xytext=(4, 4),
                fontsize=8,
            )
    handles, labels = ax.get_legend_handles_labels()
    uniq = dict(zip(labels, handles))
    ax.legend(uniq.values(), uniq.keys(), loc="best", fontsize=7)
    ax.set_title(title)
    ax.set_xlabel("Longitude")
    ax.set_ylabel("Latitude")
    ax.set_aspect("equal", adjustable="datalim")
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    png_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(png_path, dpi=140)
    plt.close(fig)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--config",
        type=Path,
        default=ROOT / "configs/optimization/placement_pilot.yaml",
    )
    p.add_argument("--demand", action="append", default=None, help="Demand scenario name(s)")
    p.add_argument("--capex", action="append", default=None, help="Capex scenario name(s)")
    p.add_argument("--price", action="append", default=None, help="Price mode(s)")
    p.add_argument("--max-subsets", type=int, default=None, help="Debug: limit subset count")
    args = p.parse_args()

    cfg = load_placement_config(args.config, root=ROOT)
    morocco_cfg = load_pilot_config(cfg.morocco_pilot_path)
    print("Loading road graph…", flush=True)
    G = load_graph_from_csv(ROOT / morocco_cfg["nodes_csv"], ROOT / morocco_cfg["edges_csv"])

    demands = args.demand or list(cfg.demand_scenarios.keys())
    capexes = args.capex or list(cfg.capex_scenarios.keys())
    prices = args.price or list(cfg.price_modes)

    all_rows: list[dict] = []
    all_opt: list[dict] = []
    for demand in demands:
        for capex in capexes:
            for price in prices:
                print(f"Enumerate demand={demand} capex={capex} price={price}", flush=True)
                res = run_enumeration(
                    cfg,
                    root=ROOT,
                    demand_name=demand,
                    capex_name=capex,
                    price_mode=price,
                    G=G,
                    max_subsets=args.max_subsets,
                )
                all_rows.extend(res.rows)
                all_opt.extend(res.optimal_rows)
                print(
                    f"  structural={sorted(res.structural_ids)} "
                    f"opt_rows={len(res.optimal_rows)}",
                    flush=True,
                )

    out_enum = ROOT / cfg.outputs.get("enumeration_csv", "results/location_enumeration.csv")
    out_opt = ROOT / cfg.outputs.get("optimal_csv", "results/location_optimal_solutions.csv")
    out_enum.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(all_rows).to_csv(out_enum, index=False)
    pd.DataFrame(all_opt).to_csv(out_opt, index=False)
    print(f"Wrote {out_enum} ({len(all_rows)} rows)", flush=True)
    print(f"Wrote {out_opt} ({len(all_opt)} rows)", flush=True)

    # Map + selection figures for two budgets (default/equal/uniform)
    fig_dir = ROOT / cfg.outputs.get("figures_dir", "reports/figures")
    fig_dir.mkdir(parents=True, exist_ok=True)
    ctx = build_mission_context(
        morocco_cfg,
        direction="casablanca_to_agadir",
        gcm="light",
        weather_id="cool",
        terrain="flat",
        refrigeration="off",
        power_source="A",
        root=ROOT,
        G=G,
    )
    geo = fig_dir / "morocco_placement_corridor_map.geojson"
    geo.write_text(json.dumps(corridor_map_features(ctx), indent=2), encoding="utf-8")

    opt_df = pd.DataFrame(all_opt)
    subset = opt_df[
        (opt_df["demand_scenario"] == "default")
        & (opt_df["capex_scenario"] == "equal")
        & (opt_df["price_mode"] == "uniform")
    ]
    for _, row in subset.iterrows():
        site_ids = [s for s in str(row["best_sites"]).split(",") if s and s != "NONE"]
        keys = set()
        for sid in site_ids:
            for s in cfg.sites:
                if s.id == sid and s.direction == "casablanca_to_agadir":
                    keys.add(s.station_key)
        png = fig_dir / f"placement_budget_{row['budget_name']}_CA.png"
        _write_placement_figure(
            geo,
            png,
            keys,
            title=(
                f"Budget {row['budget_name']}: selected Casa→Agadir sites\n"
                f"(hypothetical access; not verified HGV)"
            ),
        )
        print(f"Wrote {png}", flush=True)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
