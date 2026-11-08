"""Fingerprinted DRIVE-table cache (Task 04A)."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

DRIVE_TABLE_CACHE_VERSION = "04a.1"


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def fingerprint_payload(parts: dict[str, Any]) -> str:
    blob = json.dumps(parts, sort_keys=True, default=str)
    return _sha256_text(blob)


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
) -> str:
    return fingerprint_payload(
        {
            "version": DRIVE_TABLE_CACHE_VERSION,
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
        }
    )


def terrain_sample_hash(distances_m: list[float], elevations_m: list[float], source: str) -> str:
    return fingerprint_payload(
        {
            "source": source,
            "n": len(distances_m),
            "d0": distances_m[0] if distances_m else None,
            "d1": distances_m[-1] if distances_m else None,
            "z_head": elevations_m[:5],
            "z_tail": elevations_m[-5:],
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
