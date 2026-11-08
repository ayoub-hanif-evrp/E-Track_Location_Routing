"""MRLS memoization for placement enumeration and B&B (Task 04B)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Hashable


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


def default_energy_fingerprint(*, version: str, q: int, time_step_min: int) -> str:
    return f"{version}|q={int(q)}|dt={int(time_step_min)}"
