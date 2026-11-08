"""Open-Meteo historical weather fetch/cache and wind projection."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests

OPEN_METEO_ARCHIVE = "https://archive-api.open-meteo.com/v1/archive"


@dataclass(frozen=True)
class WeatherPointDay:
    """Mean daily conditions at one corridor point for one calendar day."""

    point_id: str
    lat: float
    lon: float
    date: str
    T_mean_c: float
    wind_speed_mean_mps: float
    wind_dir_mean_deg: float  # meteorological: direction FROM which wind blows
    pressure_mean_hpa: float | None = None

    def air_density_kg_m3(self, default: float = 1.225) -> float:
        if self.pressure_mean_hpa is None:
            return default
        # Ideal gas approx at T_mean
        T_k = self.T_mean_c + 273.15
        if T_k <= 0:
            return default
        R_specific = 287.05  # J/(kg·K) dry air
        return (self.pressure_mean_hpa * 100.0) / (R_specific * T_k)


@dataclass
class CorridorWeatherDay:
    """Three corridor points for one scenario day."""

    day_id: str
    date: str
    points: dict[str, WeatherPointDay]

    def nearest(self, lat: float, lon: float) -> WeatherPointDay:
        best = None
        best_d = float("inf")
        for p in self.points.values():
            d = (p.lat - lat) ** 2 + (p.lon - lon) ** 2
            if d < best_d:
                best_d = d
                best = p
        assert best is not None
        return best

    @property
    def T_corridor_mean_c(self) -> float:
        return sum(p.T_mean_c for p in self.points.values()) / len(self.points)


def wind_along_travel_mps(
    wind_speed_mps: float,
    wind_from_deg: float,
    travel_heading_deg: float,
) -> float:
    """
    Project wind onto travel heading.

    Meteorological wind_from_deg: direction the wind blows FROM (0=N, 90=E).
    Travel heading: direction of motion (0=N, 90=E).
    Positive return = tailwind component along travel.
    """
    wind_to_deg = (wind_from_deg + 180.0) % 360.0
    delta = math.radians(wind_to_deg - travel_heading_deg)
    return wind_speed_mps * math.cos(delta)


def heading_deg(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    """Initial bearing from (lat1,lon1) to (lat2,lon2), degrees clockwise from north."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dlon = math.radians(lon2 - lon1)
    x = math.sin(dlon) * math.cos(phi2)
    y = math.cos(phi1) * math.sin(phi2) - math.sin(phi1) * math.cos(phi2) * math.cos(dlon)
    return (math.degrees(math.atan2(x, y)) + 360.0) % 360.0


def _mean(xs: list[float]) -> float:
    return sum(xs) / len(xs) if xs else float("nan")


def circular_mean_deg(angles_deg: list[float]) -> float:
    """Circular mean of compass angles in degrees (handles 0°/360° wrap)."""
    if not angles_deg:
        return float("nan")
    sx = sum(math.sin(math.radians(a)) for a in angles_deg)
    sy = sum(math.cos(math.radians(a)) for a in angles_deg)
    return (math.degrees(math.atan2(sx, sy)) + 360.0) % 360.0


def vector_mean_wind(
    speeds_mps: list[float],
    dirs_from_deg: list[float],
) -> tuple[float, float]:
    """
    Mean wind via vector components of the FROM-direction meteorological convention.

    Returns (mean_speed_mps, mean_from_dir_deg).
    Limitation: this is still a daily aggregate, not a time-resolved wind field.
    """
    n = min(len(speeds_mps), len(dirs_from_deg))
    if n == 0:
        return float("nan"), float("nan")
    # Wind TO vector = opposite of FROM
    ux = 0.0
    uy = 0.0
    for i in range(n):
        to_deg = (dirs_from_deg[i] + 180.0) % 360.0
        ux += speeds_mps[i] * math.sin(math.radians(to_deg))
        uy += speeds_mps[i] * math.cos(math.radians(to_deg))
    ux /= n
    uy /= n
    mean_speed = math.hypot(ux, uy)
    mean_to = (math.degrees(math.atan2(ux, uy)) + 360.0) % 360.0
    mean_from = (mean_to + 180.0) % 360.0
    return mean_speed, mean_from


def fetch_point_day(
    lat: float,
    lon: float,
    date: str,
    *,
    point_id: str = "point",
    session: requests.Session | None = None,
) -> WeatherPointDay:
    sess = session or requests.Session()
    params = {
        "latitude": lat,
        "longitude": lon,
        "start_date": date,
        "end_date": date,
        "hourly": "temperature_2m,wind_speed_10m,wind_direction_10m,surface_pressure",
        "wind_speed_unit": "ms",
        "timezone": "UTC",
    }
    r = sess.get(OPEN_METEO_ARCHIVE, params=params, timeout=60)
    r.raise_for_status()
    data = r.json()
    hourly = data["hourly"]
    temps = [float(x) for x in hourly["temperature_2m"] if x is not None]
    wspd = [float(x) for x in hourly["wind_speed_10m"] if x is not None]
    wdir = [float(x) for x in hourly["wind_direction_10m"] if x is not None]
    pres = [float(x) for x in hourly.get("surface_pressure", []) if x is not None]
    wind_speed, wind_dir = vector_mean_wind(wspd, wdir)
    return WeatherPointDay(
        point_id=point_id,
        lat=lat,
        lon=lon,
        date=date,
        T_mean_c=_mean(temps),
        wind_speed_mean_mps=wind_speed,
        wind_dir_mean_deg=wind_dir,
        pressure_mean_hpa=_mean(pres) if pres else None,
    )


def cache_path_for(cache_dir: Path, point_id: str, date: str) -> Path:
    return cache_dir / f"{point_id}_{date}.json"


def load_or_fetch_point(
    point_id: str,
    lat: float,
    lon: float,
    date: str,
    cache_dir: Path,
    *,
    session: requests.Session | None = None,
    allow_fetch: bool = True,
) -> WeatherPointDay:
    cache_dir.mkdir(parents=True, exist_ok=True)
    path = cache_path_for(cache_dir, point_id, date)
    if path.exists():
        raw = json.loads(path.read_text(encoding="utf-8"))
        return WeatherPointDay(**raw)
    if not allow_fetch:
        raise FileNotFoundError(f"Weather fixture missing: {path}")
    wp = fetch_point_day(lat, lon, date, point_id=point_id, session=session)
    path.write_text(
        json.dumps(
            {
                "point_id": wp.point_id,
                "lat": wp.lat,
                "lon": wp.lon,
                "date": wp.date,
                "T_mean_c": wp.T_mean_c,
                "wind_speed_mean_mps": wp.wind_speed_mean_mps,
                "wind_dir_mean_deg": wp.wind_dir_mean_deg,
                "pressure_mean_hpa": wp.pressure_mean_hpa,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return wp


def load_corridor_day_from_cache(
    day_id: str,
    date: str,
    points_cfg: dict[str, dict[str, Any]],
    cache_dir: Path,
) -> CorridorWeatherDay:
    pts: dict[str, WeatherPointDay] = {}
    for pid, cfg in points_cfg.items():
        path = cache_path_for(cache_dir, pid, date)
        raw = json.loads(path.read_text(encoding="utf-8"))
        pts[pid] = WeatherPointDay(**raw)
    return CorridorWeatherDay(day_id=day_id, date=date, points=pts)


def select_hot_cool_dates(
    series: list[tuple[str, float]],
) -> tuple[str, str]:
    """Pick hottest and coolest dates from (date, T_mean) list."""
    if not series:
        raise ValueError("empty temperature series")
    hot = max(series, key=lambda x: x[1])[0]
    cool = min(series, key=lambda x: x[1])[0]
    return hot, cool
