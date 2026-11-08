#!/usr/bin/env python3
"""Run Task 02/02B energy pilot matrix → energy_pilot.csv + scientific figures."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import replace
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import yaml
from shapely.geometry import shape

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from morocco_etruck.energy.refrigeration import load_refrigeration  # noqa: E402
from morocco_etruck.energy.simulator import (  # noqa: E402
    edges_from_route_geometry,
    evaluate_route,
    route_geodesic_length_m,
)
from morocco_etruck.energy.terrain import (  # noqa: E402
    assess_terrain_quality,
    flat_profile,
    load_profile,
    profile_distance_agrees,
)
from morocco_etruck.energy.vehicle import cargo_payload_kg, load_vehicle  # noqa: E402
from morocco_etruck.energy.weather import (  # noqa: E402
    CorridorWeatherDay,
    WeatherPointDay,
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
        pts = {}
        ok = True
        for pid, _pcfg in points_cfg.items():
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
        prof = flat_profile(geom)
        return prof, assess_terrain_quality(prof)
    path = processed / f"elevation_profile_{route}.json"
    if path.exists():
        prof = load_profile(path)
        return prof, assess_terrain_quality(prof)
    prof = flat_profile(geom)
    q = assess_terrain_quality(prof)
    # Requested DEM but missing file → treat as invalid/unavailable for dem mode
    return prof, replace(
        q,
        status="invalid",
        notes=list(q.notes) + [f"Missing DEM profile {path.name}"],
    )


def make_figures(df: pd.DataFrame, figures_dir: Path, track_rows: list[dict]) -> None:
    figures_dir.mkdir(parents=True, exist_ok=True)

    sub = df[(df["power_source"] == "A") & (df["terrain"] == "flat") & (df["weather"] == "cool")].copy()
    if sub.empty:
        sub = df[(df["power_source"] == "A") & (df["terrain"] == "flat")].copy()

    directions = sorted(sub["direction"].unique())
    gcms = sorted(sub["gcm_label"].unique())
    width = 0.35
    fig, axes = plt.subplots(1, max(1, len(directions)), figsize=(10, 4), sharey=True)
    if len(directions) == 1:
        axes = [axes]
    for ax, direction in zip(axes, directions):
        part = sub[sub["direction"] == direction]
        labels, off_vals, on_vals = [], [], []
        for gcm in gcms:
            labels.append(gcm)
            off_vals.append(
                float(part[(part["gcm_label"] == gcm) & (part["refrigeration"] == "off")]["E_net_tractor_kWh"].mean())
            )
            on_vals.append(
                float(part[(part["gcm_label"] == gcm) & (part["refrigeration"] == "on")]["E_net_tractor_kWh"].mean())
            )
        idx = np.arange(len(labels))
        ax.bar(idx - width / 2, off_vals, width, label="refrig off", color="#4C78A8")
        ax.bar(idx + width / 2, on_vals, width, label="refrig on", color="#F58518")
        ax.set_xticks(idx)
        ax.set_xticklabels(labels, rotation=15, ha="right")
        ax.set_title(direction.replace("_", " "))
        ax.set_xlabel("Gross combination mass")
        ax.grid(True, axis="y", alpha=0.3)
    axes[0].set_ylabel("Net tractor energy (kWh)")
    axes[0].legend(loc="upper left")
    fig.suptitle("Net tractor energy vs GCM × refrigeration (cool, flat, config A)")
    fig.tight_layout()
    fig.savefig(figures_dir / "energy_vs_payload_refrig.png", dpi=120)
    plt.close(fig)

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(9, 6), sharex=True)
    plotted = False
    for row in track_rows:
        xs = [d / 1000.0 for d in row["cumulative_distance_m"]]
        label = f"terrain={row['terrain']} ({row['terrain_source']}; {row['terrain_quality_status']})"
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
    ax2.set_title("Cumulative net tractor energy (GCM heavy, cool, refrig off, A)")
    if not plotted:
        ax1.text(0.5, 0.5, "No track data", transform=ax1.transAxes, ha="center")
    fig.tight_layout()
    fig.savefig(figures_dir / "elevation_cumulative_energy.png", dpi=120)
    plt.close(fig)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--config", type=Path, default=ROOT / "configs" / "energy" / "pilot_scenarios.yaml")
    p.add_argument("--weather-cache", type=Path, default=ROOT / "data" / "raw" / "weather")
    p.add_argument("--fixture-dir", type=Path, default=ROOT / "tests" / "fixtures" / "weather")
    p.add_argument("--processed", type=Path, default=ROOT / "data" / "processed" / "energy")
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

    baseline_json = ROOT / cfg["baseline_json"]
    baseline_distances = {}
    if baseline_json.exists():
        bj = json.loads(baseline_json.read_text(encoding="utf-8"))
        for k, v in bj.get("routes", {}).items():
            baseline_distances[k] = float(v["distance_m"])

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
        geodesic_m = route_geodesic_length_m(geom)
        edge_sum_m = sum(e.length_m for e in edges)
        for _pay_key, pay_cfg in cfg["gcm_scenarios"].items():
            gcm_kg = float(pay_cfg["gcm_kg"])
            payload_kg = cargo_payload_kg(gcm_kg, vehicle)
            for weather_key, weather in weather_days.items():
                for refrig in cfg["refrigeration"]:
                    refrig_label = str(refrig).lower()
                    if refrig_label in ("true", "1"):
                        refrig_label = "on"
                    elif refrig_label in ("false", "0"):
                        refrig_label = "off"
                    refrig_on = refrig_label == "on"
                    for terrain_mode in cfg["terrain"]:
                        terrain, tq = _terrain_for(direction, terrain_mode, geom, args.processed)
                        # DEM mode with invalid quality: still evaluate for energy diagnostics,
                        # but mission_feasible will be indeterminate (None).
                        dem_distance_ok = True
                        if terrain_mode == "dem" and terrain.source != "flat":
                            dem_distance_ok = profile_distance_agrees(terrain, geodesic_m)
                            if not dem_distance_ok:
                                tq = assess_terrain_quality(terrain)
                                # keep status but note mismatch
                                terrain.meta.setdefault("notes", [])
                        for psrc in cfg["power_source"]:
                            result = evaluate_route(
                                edges,
                                vehicle,
                                weather,
                                fridge,
                                gcm_kg=gcm_kg,
                                refrigeration_on=refrig_on,
                                power_source=str(psrc),
                                terrain=terrain,
                                terrain_quality=tq,
                                tags={
                                    "direction": direction,
                                    "gcm_label": pay_cfg["label"],
                                    "weather": weather_key,
                                    "refrigeration": refrig_label,
                                    "terrain": terrain_mode,
                                    "power_source": str(psrc),
                                },
                            )
                            mf = result.mission_feasible
                            row = {
                                "direction": direction,
                                "gcm_label": pay_cfg["label"],
                                "gcm_kg": gcm_kg,
                                "cargo_payload_kg": payload_kg,
                                "weather": weather_key,
                                "weather_date": weather.date,
                                "T_corridor_mean_c": weather.T_corridor_mean_c,
                                "refrigeration": refrig_label,
                                "terrain": terrain_mode,
                                "terrain_source": result.terrain_source,
                                "terrain_quality_status": result.terrain_quality_status,
                                "power_source": str(psrc),
                                "distance_km": result.distance_km,
                                "baseline_distance_km": baseline_distances.get(direction, geodesic_m) / 1000.0,
                                "geodesic_distance_km": geodesic_m / 1000.0,
                                "edge_sum_distance_km": edge_sum_m / 1000.0,
                                "duration_h": result.duration_h,
                                "E_traction_kWh": result.E_traction_kWh,
                                "E_aux_kWh": result.E_aux_kWh,
                                "E_refrig_kWh": result.E_refrig_kWh,
                                "E_net_tractor_kWh": result.E_net_tractor_kWh,
                                "E_trailer_refrig_kWh": result.E_trailer_refrig_j / 3.6e6,
                                "E_regen_accepted_kWh": result.E_regen_accepted_j / 3.6e6,
                                "E_regen_rejected_kWh": result.E_regen_rejected_j / 3.6e6,
                                "SOC_final": result.soc_final,
                                "trailer_SOC_final": result.trailer_soc_final,
                                "minimum_soc": result.minimum_soc,
                                "minimum_trailer_soc": result.minimum_trailer_soc,
                                "power_feasible_bool": result.power_feasible,
                                "soc_feasible_bool": result.soc_feasible,
                                "trailer_soc_feasible_bool": result.trailer_soc_feasible,
                                "continuous_power_exceeded_bool": result.continuous_power_exceeded,
                                "first_violation_distance_km": result.first_violation_distance_km,
                                "first_violation_reason": result.first_violation_reason,
                                "mission_feasible_bool": mf if mf is not None else "",
                                "mission_status": (
                                    "feasible"
                                    if mf is True
                                    else ("infeasible" if mf is False else "indeterminate_invalid_terrain")
                                ),
                                "cruise_kmh": cfg["cruise_kmh"],
                                "profile_distance_ok": dem_distance_ok if terrain_mode == "dem" else True,
                            }
                            rows.append(row)
                            if (
                                direction == "casablanca_to_agadir"
                                and pay_cfg["label"] == "gcm_heavy_40t"
                                and weather_key == "cool"
                                and refrig_label == "off"
                                and str(psrc) == "A"
                                and terrain_mode in ("flat", "dem")
                                and result.terrain_quality_status in ("flat", "valid")
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
    print(df.groupby(["gcm_label", "refrigeration", "terrain", "terrain_quality_status"])[
        ["E_net_tractor_kWh", "mission_status"]
    ].agg({"E_net_tractor_kWh": "mean", "mission_status": lambda s: s.mode().iloc[0] if len(s) else ""}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
