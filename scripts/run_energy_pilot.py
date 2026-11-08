#!/usr/bin/env python3
"""Run Task 02 energy pilot matrix → energy_pilot.csv + scientific figures."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd
import yaml
from shapely.geometry import shape

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from morocco_etruck.energy.refrigeration import load_refrigeration  # noqa: E402
from morocco_etruck.energy.simulator import (  # noqa: E402
    edges_from_route_geometry,
    evaluate_route,
)
from morocco_etruck.energy.terrain import flat_profile, load_profile  # noqa: E402
from morocco_etruck.energy.vehicle import load_vehicle  # noqa: E402
from morocco_etruck.energy.weather import (  # noqa: E402
    CorridorWeatherDay,
    WeatherPointDay,
    load_corridor_day_from_cache,
)


def _load_selection(cache_dir: Path, fixture_dir: Path, cfg: dict) -> dict:
    for path in (cache_dir / "selection.json", fixture_dir / "selection.json"):
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    return {
        "hot_date": cfg["weather_days"]["hot"]["default_date"],
        "cool_date": cfg["weather_days"]["cool"]["default_date"],
    }


def _weather_day(
    day_id: str,
    date: str,
    points_cfg: dict,
    cache_dir: Path,
    fixture_dir: Path,
) -> CorridorWeatherDay:
    for d in (cache_dir, fixture_dir):
        try:
            return load_corridor_day_from_cache(day_id, date, points_cfg, d)
        except FileNotFoundError:
            continue
        except Exception:
            # Missing one of the point files
            pts = {}
            ok = True
            for pid, pcfg in points_cfg.items():
                fpath = d / f"{pid}_{date}.json"
                if not fpath.exists():
                    ok = False
                    break
                raw = json.loads(fpath.read_text(encoding="utf-8"))
                pts[pid] = WeatherPointDay(**raw)
            if ok and pts:
                return CorridorWeatherDay(day_id=day_id, date=date, points=pts)
    raise FileNotFoundError(
        f"No weather cache/fixtures for {day_id} date={date}. "
        "Run scripts/fetch_corridor_weather.py or ensure tests/fixtures/weather/ exists."
    )


def _terrain_for(route: str, mode: str, geom, processed: Path):
    if mode == "flat":
        return flat_profile(geom)
    path = processed / f"elevation_profile_{route}.json"
    if path.exists():
        prof = load_profile(path)
        if prof.source != "flat":
            return prof
        # DEM file exists but is flat fallback — still label as dem attempt with flat data
        return prof
    # No DEM profile: labeled flat with dem-requested tag handled by caller
    return flat_profile(geom)


def make_figures(df: pd.DataFrame, figures_dir: Path, track_rows: list[dict]) -> None:
    figures_dir.mkdir(parents=True, exist_ok=True)

    # Figure 1: Net tractor energy vs payload × refrigeration (both directions)
    # Aggregate over weather/terrain/power for clarity: use cool + flat + A as primary panel,
    # and show all A/flat rows faceted.
    sub = df[(df["power_source"] == "A") & (df["terrain"] == "flat") & (df["weather"] == "cool")].copy()
    if sub.empty:
        sub = df[(df["power_source"] == "A") & (df["terrain"] == "flat")].copy()

    fig, ax = plt.subplots(figsize=(8, 4.5))
    directions = sorted(sub["direction"].unique())
    payloads = ["light_25t", "heavy_40t"]
    width = 0.35
    import numpy as np

    x = np.arange(len(directions))
    for j, refrig in enumerate(["off", "on"]):
        heights = []
        for d in directions:
            for pay in payloads:
                row = sub[(sub["direction"] == d) & (sub["payload"] == pay) & (sub["refrigeration"] == refrig)]
                heights.append(float(row["E_net_tractor_kWh"].mean()) if len(row) else float("nan"))
        # Group by direction with payload pairs — simpler grouped bars per direction×payload
    # Cleaner: grouped bars for payload, hue=refrig, panels=direction
    fig, axes = plt.subplots(1, 2, figsize=(10, 4), sharey=True)
    for ax, direction in zip(axes, directions):
        part = sub[sub["direction"] == direction]
        labels = []
        off_vals, on_vals = [], []
        for pay in payloads:
            labels.append(pay)
            off_vals.append(
                float(part[(part["payload"] == pay) & (part["refrigeration"] == "off")]["E_net_tractor_kWh"].mean())
            )
            on_vals.append(
                float(part[(part["payload"] == pay) & (part["refrigeration"] == "on")]["E_net_tractor_kWh"].mean())
            )
        idx = np.arange(len(labels))
        ax.bar(idx - width / 2, off_vals, width, label="refrig off", color="#4C78A8")
        ax.bar(idx + width / 2, on_vals, width, label="refrig on", color="#F58518")
        ax.set_xticks(idx)
        ax.set_xticklabels(labels)
        ax.set_title(direction.replace("_", " "))
        ax.set_xlabel("Payload")
        ax.grid(True, axis="y", alpha=0.3)
    axes[0].set_ylabel("Net tractor energy (kWh)")
    axes[0].legend(loc="upper left")
    fig.suptitle("Net tractor energy vs payload × refrigeration (cool, flat, config A)")
    fig.tight_layout()
    fig.savefig(figures_dir / "energy_vs_payload_refrig.png", dpi=120)
    plt.close(fig)

    # Figure 2: Elevation + cumulative energy Casa→Agadir DEM vs flat
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(9, 6), sharex=True)
    plotted = False
    for row in track_rows:
        if row["direction"] != "casablanca_to_agadir":
            continue
        if row["payload"] != "heavy_40t":
            continue
        if row["weather"] != "cool" or row["refrigeration"] != "off" or row["power_source"] != "A":
            continue
        xs = [d / 1000.0 for d in row["cumulative_distance_m"]]
        label = f"terrain={row['terrain']} ({row['terrain_source']})"
        ax1.plot(xs, row["elevations_m"], label=label)
        ax2.plot(xs, row["cumulative_energy_kwh"], label=label)
        plotted = True
    ax1.set_ylabel("Elevation (m)")
    ax1.legend(loc="best", fontsize=8)
    ax1.grid(True, alpha=0.3)
    ax1.set_title("Casablanca→Agadir elevation profile")
    ax2.set_ylabel("Cumulative tractor energy (kWh)")
    ax2.set_xlabel("Distance (km)")
    ax2.legend(loc="best", fontsize=8)
    ax2.grid(True, alpha=0.3)
    ax2.set_title("Cumulative net tractor energy (heavy, cool, refrig off, A)")
    if not plotted:
        ax1.text(0.5, 0.5, "No track data", transform=ax1.transAxes, ha="center")
    fig.tight_layout()
    fig.savefig(figures_dir / "elevation_cumulative_energy.png", dpi=120)
    plt.close(fig)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--config",
        type=Path,
        default=ROOT / "configs" / "energy" / "pilot_scenarios.yaml",
    )
    p.add_argument(
        "--weather-cache",
        type=Path,
        default=ROOT / "data" / "raw" / "weather",
    )
    p.add_argument(
        "--fixture-dir",
        type=Path,
        default=ROOT / "tests" / "fixtures" / "weather",
    )
    p.add_argument(
        "--processed",
        type=Path,
        default=ROOT / "data" / "processed" / "energy",
    )
    args = p.parse_args()

    cfg = yaml.safe_load(args.config.read_text(encoding="utf-8"))
    vehicle = load_vehicle(ROOT / cfg["vehicle_config"])
    fridge = load_refrigeration(ROOT / cfg["refrigeration_config"])

    gj_path = ROOT / cfg["baseline_geojson"]
    if not gj_path.exists():
        print(f"Missing {gj_path}")
        return 1
    gj = json.loads(gj_path.read_text(encoding="utf-8"))
    routes = {f["properties"]["route"]: shape(f["geometry"]) for f in gj["features"]}

    selection = _load_selection(args.weather_cache, args.fixture_dir, cfg)
    hot_date = selection.get("hot_date") or cfg["weather_days"]["hot"]["default_date"]
    cool_date = selection.get("cool_date") or cfg["weather_days"]["cool"]["default_date"]

    weather_days = {
        "hot": _weather_day("hot", hot_date, cfg["corridor_weather_points"], args.weather_cache, args.fixture_dir),
        "cool": _weather_day("cool", cool_date, cfg["corridor_weather_points"], args.weather_cache, args.fixture_dir),
    }

    rows: list[dict] = []
    track_rows: list[dict] = []

    for direction, geom in routes.items():
        edges = edges_from_route_geometry(geom, max_edge_m=2000.0)
        for pay_key, pay_cfg in cfg["gcm_scenarios"].items():
            for weather_key, weather in weather_days.items():
                for refrig in cfg["refrigeration"]:
                    refrig_label = str(refrig).lower()
                    if refrig_label in ("true", "1"):
                        refrig_label = "on"
                    elif refrig_label in ("false", "0"):
                        refrig_label = "off"
                    refrig_on = refrig_label == "on"
                    for terrain_mode in cfg["terrain"]:
                        terrain = _terrain_for(direction, terrain_mode, geom, args.processed)
                        # If dem requested but profile is flat-only file, still run labeled
                        for psrc in cfg["power_source"]:
                            result = evaluate_route(
                                edges,
                                vehicle,
                                weather,
                                fridge,
                                gcm_kg=float(pay_cfg["gcm_kg"]),
                                refrigeration_on=refrig_on,
                                power_source=str(psrc),
                                terrain=terrain,
                                tags={
                                    "direction": direction,
                                    "payload": pay_cfg["label"],
                                    "weather": weather_key,
                                    "weather_date": weather.date,
                                    "refrigeration": refrig_label,
                                    "terrain": terrain_mode,
                                    "power_source": str(psrc),
                                },
                            )
                            row = {
                                "direction": direction,
                                "payload": pay_cfg["label"],
                                "gcm_kg": pay_cfg["gcm_kg"],
                                "weather": weather_key,
                                "weather_date": weather.date,
                                "T_corridor_mean_c": weather.T_corridor_mean_c,
                                "refrigeration": refrig_label,
                                "terrain": terrain_mode,
                                "terrain_source": result.terrain_source,
                                "power_source": str(psrc),
                                "distance_km": result.distance_km,
                                "duration_h": result.duration_h,
                                "E_traction_kWh": result.E_traction_kWh,
                                "E_aux_kWh": result.E_aux_kWh,
                                "E_refrig_kWh": result.E_refrig_kWh,
                                "E_net_tractor_kWh": result.E_net_tractor_kWh,
                                "E_trailer_refrig_kWh": result.E_trailer_refrig_j / 3.6e6,
                                "SOC_final": result.soc_final,
                                "trailer_SOC_final": result.trailer_soc_final,
                                "mission_feasible_bool": result.mission_feasible,
                                "cruise_kmh": cfg["cruise_kmh"],
                            }
                            rows.append(row)
                            if (
                                direction == "casablanca_to_agadir"
                                and pay_cfg["label"] == "heavy_40t"
                                and weather_key == "cool"
                                and refrig_label == "off"
                                and str(psrc) == "A"
                                and terrain_mode in ("flat", "dem")
                            ):
                                track_rows.append(
                                    {
                                        **row,
                                        "cumulative_distance_m": result.cumulative_distance_m,
                                        "cumulative_energy_kwh": result.cumulative_energy_kwh,
                                        "elevations_m": result.elevations_m,
                                    }
                                )

    out_csv = ROOT / cfg["outputs"]["csv"]
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame(rows)
    df.to_csv(out_csv, index=False)
    print(f"Wrote {out_csv} ({len(df)} rows)")

    figures_dir = ROOT / cfg["outputs"]["figures_dir"]
    make_figures(df, figures_dir, track_rows)
    print(f"Figures under {figures_dir}")

    # Sanity summary
    print(df.groupby(["payload", "refrigeration", "terrain"])["E_net_tractor_kWh"].mean())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
