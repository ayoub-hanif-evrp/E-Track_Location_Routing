"""Fingerprinted DRIVE-table cache (Task 04A / 06A)."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Sequence

DRIVE_TABLE_CACHE_VERSION = "06c.1"
PREPROCESS_MODEL_VERSION = "06c.1_multi_vehicle"


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def fingerprint_payload(parts: dict[str, Any]) -> str:
    blob = json.dumps(parts, sort_keys=True, default=str)
    return _sha256_text(blob)


def speed_schedule_hash(speed_mps_list: Sequence[float | None]) -> str:
    """Digest ordered micro-edge speeds (None → vehicle-cruise fallback at sim time)."""
    return fingerprint_payload(
        {
            "speeds_mps": [
                None if s is None else round(float(s), 6) for s in speed_mps_list
            ]
        }
    )


def speed_policy_digest(speed_policy: dict[str, Any] | None) -> str:
    if not speed_policy:
        return fingerprint_payload({"speed_policy": None})
    return fingerprint_payload({"speed_policy": dict(speed_policy)})


def build_drive_table_fingerprint(
    *,
    vehicle_yaml: Path,
    fridge_yaml: Path,
    weather_points: dict[str, Any],
    terrain_mode: str,
    terrain_source: str,
    terrain_hash: str,
    macro_u: str,
    macro_v: str,
    edge_pairs: list[tuple[Any, Any]],
    length_m: float,
    gcm_kg: float,
    refrigeration_on: bool,
    power_source: str,
    energy_quantum_kwh: int,
    time_step_min: int,
    E_truck_min: int,
    E_truck_cap: int,
    E_trailer_min: int | None,
    E_trailer_cap: int | None,
    speed_schedule: Sequence[float | None] | None = None,
    speed_policy: dict[str, Any] | None = None,
    preprocess_model_version: str = PREPROCESS_MODEL_VERSION,
) -> str:
    return fingerprint_payload(
        {
            "version": DRIVE_TABLE_CACHE_VERSION,
            "preprocess_model_version": preprocess_model_version,
            "vehicle_sha": file_sha256(vehicle_yaml),
            "fridge_sha": file_sha256(fridge_yaml),
            "weather": weather_points,
            "terrain_mode": terrain_mode,
            "terrain_source": terrain_source,
            "terrain_hash": terrain_hash,
            "macro": f"{macro_u}->{macro_v}",
            "edges": [(str(u), str(v)) for u, v in edge_pairs],
            "length_m": round(float(length_m), 3),
            "gcm_kg": float(gcm_kg),
            "refrigeration_on": bool(refrigeration_on),
            "power_source": power_source,
            "q": int(energy_quantum_kwh),
            "dt_min": int(time_step_min),
            "E_truck": [E_truck_min, E_truck_cap],
            "E_trailer": [E_trailer_min, E_trailer_cap],
            "speed_schedule_hash": speed_schedule_hash(speed_schedule or []),
            "speed_policy_digest": speed_policy_digest(speed_policy),
        }
    )


def terrain_sample_hash(
    distances_m: list[float],
    elevations_m: list[float],
    source: str,
    valid_mask: list[bool] | None = None,
) -> str:
    """Digest the full elevation profile (not head/tail only)."""
    return fingerprint_payload(
        {
            "source": source,
            "n": len(distances_m),
            "distances_m": [round(float(x), 6) for x in distances_m],
            "elevations_m": [
                None
                if (isinstance(z, float) and z != z)
                else (round(float(z), 6) if z is not None else None)
                for z in elevations_m
            ],
            "valid_mask": list(valid_mask) if valid_mask is not None else None,
        }
    )


def load_cached_table(path: Path, expected_fp: str):
    """Return deserialized drive table dict or None if missing/stale."""
    from morocco_etruck.optimization.problem import DriveTableEntry

    if not path.exists():
        return None
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or raw.get("fingerprint") != expected_fp:
        return None
    entries = raw.get("entries") or {}
    table = {}
    for k, v in entries.items():
        a, b = k.split(",", 1)
        key = (int(a), None if b == "None" else int(b))
        table[key] = DriveTableEntry(**v)
    return table


def save_cached_table(path: Path, fingerprint: str, table: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    ser = {
        "fingerprint": fingerprint,
        "version": DRIVE_TABLE_CACHE_VERSION,
        "entries": {
            f"{k[0]},{k[1]}": {
                "feasible": v.feasible,
                "dt_steps": v.dt_steps,
                "E_end_truck": v.E_end_truck,
                "E_end_trailer": v.E_end_trailer,
                "reason": v.reason,
            }
            for k, v in table.items()
        },
    }
    path.write_text(json.dumps(ser), encoding="utf-8")
