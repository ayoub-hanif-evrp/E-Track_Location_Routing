"""MRLS memoization for placement enumeration and B&B (Task 04B/05A)."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Hashable

from morocco_etruck.optimization.drive_table_cache import (
    DRIVE_TABLE_CACHE_VERSION,
    file_sha256,
    fingerprint_payload,
)


CacheKey = tuple[Hashable, ...]


@dataclass
class CachedMissionResult:
    status: str
    served: bool
    uncertified: bool
    objective_cents: int | None
    charge_kwh: int
    charges: str
    path: str
    continuous_replay_ok: bool
    discrete_replay_ok: bool
    reason: str | None = None


@dataclass
class PlacementMemo:
    """In-memory mission/active-set memo shared across subsets and budgets."""

    energy_model_fingerprint: str
    _store: dict[CacheKey, CachedMissionResult] = field(default_factory=dict)
    hits: int = 0
    misses: int = 0
    puts: int = 0

    def make_key(
        self,
        *,
        mission_id: str,
        active_station_keys: frozenset[str] | set[str],
        price_mode: str,
        q: int,
        time_step_min: int,
    ) -> CacheKey:
        return (
            mission_id,
            frozenset(active_station_keys),
            price_mode,
            self.energy_model_fingerprint,
            int(q),
            int(time_step_min),
        )

    def get(self, key: CacheKey) -> CachedMissionResult | None:
        hit = self._store.get(key)
        if hit is None:
            self.misses += 1
            return None
        self.hits += 1
        return hit

    def put(self, key: CacheKey, value: CachedMissionResult) -> None:
        self._store[key] = value
        self.puts += 1

    def invalidate(self) -> None:
        self._store.clear()
        self.hits = 0
        self.misses = 0
        self.puts = 0

    def stats(self) -> dict[str, Any]:
        return {
            "hits": self.hits,
            "misses": self.misses,
            "puts": self.puts,
            "size": len(self._store),
            "energy_model_fingerprint": self.energy_model_fingerprint,
        }


def build_mission_energy_fingerprint(
    *,
    vehicle_yaml: Path | None = None,
    fridge_yaml: Path | None = None,
    version: str = DRIVE_TABLE_CACHE_VERSION,
    q: int,
    time_step_min: int,
    gcm: str = "",
    terrain_mode: str = "",
    weather_id: str = "",
    refrigeration: str = "",
    power_source: str = "",
    direction: str = "",
    terrain_hash: str = "",
    extra: dict[str, Any] | None = None,
) -> str:
    """
    Fingerprint physical + scenario inputs for MRLS memo invalidation.

    Must change when vehicle/fridge, grid, GCM, terrain, weather, refrigeration,
    power source, direction, or terrain profile hash change.
    """
    parts: dict[str, Any] = {
        "version": version,
        "q": int(q),
        "dt": int(time_step_min),
        "gcm": gcm,
        "terrain_mode": terrain_mode,
        "weather_id": weather_id,
        "refrigeration": refrigeration,
        "power_source": power_source,
        "direction": direction,
        "terrain_hash": terrain_hash,
    }
    if vehicle_yaml is not None and Path(vehicle_yaml).exists():
        parts["vehicle_sha"] = file_sha256(Path(vehicle_yaml))
    if fridge_yaml is not None and Path(fridge_yaml).exists():
        parts["fridge_sha"] = file_sha256(Path(fridge_yaml))
    if extra:
        parts["extra"] = extra
    return fingerprint_payload(parts)


def default_energy_fingerprint(
    *,
    version: str,
    q: int,
    time_step_min: int,
    vehicle_yaml: Path | None = None,
    fridge_yaml: Path | None = None,
    gcm: str = "",
    terrain_mode: str = "",
    weather_id: str = "",
    refrigeration: str = "",
    power_source: str = "",
    direction: str = "",
    terrain_hash: str = "",
) -> str:
    """Backward-compatible wrapper; prefer full mission fields when available."""
    return build_mission_energy_fingerprint(
        vehicle_yaml=vehicle_yaml,
        fridge_yaml=fridge_yaml,
        version=version,
        q=q,
        time_step_min=time_step_min,
        gcm=gcm,
        terrain_mode=terrain_mode,
        weather_id=weather_id,
        refrigeration=refrigeration,
        power_source=power_source,
        direction=direction,
        terrain_hash=terrain_hash,
    )


def portfolio_energy_fingerprint(
    missions: list[Any],
    *,
    version: str,
    q: int,
    time_step_min: int,
    vehicle_yaml: Path | None = None,
    fridge_yaml: Path | None = None,
) -> str:
    """Aggregate fingerprint over a mission portfolio (shared memo scope)."""
    mission_parts = [
        {
            "id": m.id,
            "gcm": m.gcm,
            "terrain": m.terrain,
            "weather": m.weather,
            "refrigeration": m.refrigeration,
            "power_source": m.power_source,
            "direction": m.direction,
            "weight": float(m.weight),
        }
        for m in missions
    ]
    return build_mission_energy_fingerprint(
        vehicle_yaml=vehicle_yaml,
        fridge_yaml=fridge_yaml,
        version=version,
        q=q,
        time_step_min=time_step_min,
        extra={"missions": mission_parts},
    )
