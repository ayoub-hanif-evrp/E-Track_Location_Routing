#!/usr/bin/env python3
"""Ordered DEM elevation profile reconstruction for final evidence.

Reconstructs continuous journey elevation from OD-local decision arcs ordered
along a specific path alternative (not unsorted arc bags / length-sort stitches).
"""
from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Sequence

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from morocco_etruck.energy.terrain import load_profile  # noqa: E402
from morocco_etruck.optimization.multiroute_adapter import (  # noqa: E402
    load_multiroute_pilot_config,
)
from morocco_etruck.optimization.multiroute_physics import (  # noqa: E402
    _is_subsequence,
    contract_od_path_union,
)
from morocco_etruck.road_network import load_graph_from_csv  # noqa: E402

DEM_DIR = ROOT / "data/processed/multiroute/elevation"
PATHS_CSV = ROOT / "data/processed/multiroute/path_alternatives.csv"
PILOT_YAML = ROOT / "configs/optimization/multiroute_pilot.yaml"

_CACHE: dict[str, Any] = {}


def _graph_and_paths():
    if "G" not in _CACHE:
        cfg = load_multiroute_pilot_config(PILOT_YAML, root=ROOT)
        _CACHE["cfg"] = cfg
        _CACHE["G"] = load_graph_from_csv(cfg.nodes_csv, cfg.edges_csv)
        _CACHE["path_rows"] = pd.read_csv(PATHS_CSV).to_dict(orient="records")
        _CACHE["dem_meta"] = json.loads(
            (DEM_DIR / "dem_sampling_meta.json").read_text(encoding="utf-8")
        )
    return _CACHE["G"], _CACHE["path_rows"], _CACHE["cfg"], _CACHE["dem_meta"]


@dataclass
class OrderedElevationProfile:
    od_id: str
    method: str
    path_length_m: float
    arc_ids: list[str]
    distances_m: np.ndarray
    elevations_m: np.ndarray
    arc_boundaries_m: list[float] = field(default_factory=list)
    missing_arc_ids: list[str] = field(default_factory=list)
    invalid_arc_ids: list[str] = field(default_factory=list)
    dem_coverage_frac: float = 0.0
    stitched_length_m: float = 0.0
    length_error_m: float = 0.0
    cum_gain_m: float = 0.0
    cum_loss_m: float = 0.0
    max_abs_grade: float = float("nan")
    continuity_ok: bool = True
    notes: list[str] = field(default_factory=list)

    def to_frame(self) -> pd.DataFrame:
        return pd.DataFrame(
            {
                "distance_m": self.distances_m,
                "distance_km": self.distances_m / 1000.0,
                "elevation_m": self.elevations_m,
            }
        )


def _ordered_arcs_for_path(arcs, path: list[int]):
    """Return decision arcs that lie on ``path``, ordered by start index."""
    scored = []
    for arc in arcs:
        pn = list(arc.path_nodes)
        if not _is_subsequence(pn, path):
            continue
        # start index of arc on path
        start = None
        for i in range(len(path) - len(pn) + 1):
            if path[i : i + len(pn)] == pn:
                start = i
                break
        if start is None:
            continue
        scored.append((start, arc))
    scored.sort(key=lambda t: t[0])
    return [a for _, a in scored]


def _gain_loss(z: np.ndarray) -> tuple[float, float]:
    if len(z) < 2:
        return 0.0, 0.0
    dz = np.diff(z.astype(float))
    gain = float(dz[dz > 0].sum()) if len(dz) else 0.0
    loss = float((-dz[dz < 0]).sum()) if len(dz) else 0.0
    return gain, loss


def _max_abs_grade(dist: np.ndarray, z: np.ndarray) -> float:
    if len(dist) < 2:
        return float("nan")
    dd = np.diff(dist.astype(float))
    dz = np.diff(z.astype(float))
    ok = dd > 1e-6
    if not np.any(ok):
        return float("nan")
    g = np.abs(dz[ok] / dd[ok])
    return float(np.nanmax(g)) if len(g) else float("nan")


def reconstruct_od_elevation(
    od_id: str,
    *,
    method: str = "shortest_distance",
    drop_junction_duplicate: bool = True,
) -> OrderedElevationProfile:
    """Build ordered elevation for one OD path alternative."""
    G, path_rows, cfg, dem_meta = _graph_and_paths()
    od_rows = [r for r in path_rows if str(r.get("od_id")) == od_id]
    if not od_rows:
        raise ValueError(f"No path alternatives for {od_id}")
    chosen = next((r for r in od_rows if str(r.get("method")) == method), None)
    if chosen is None:
        chosen = od_rows[0]
        method = str(chosen.get("method") or method)
    path = [int(x) for x in json.loads(chosen["node_path_json"])]
    path_len = float(chosen["length_m"])

    # Contract using up to 2 alts (same as DEM writer / physics)
    short = [r for r in od_rows if str(r.get("method")) == "shortest_distance"]
    rest = sorted(
        [r for r in od_rows if str(r.get("method")) != "shortest_distance"],
        key=lambda r: -float(r.get("jaccard_distance_vs_shortest") or 0.0),
    )
    union_rows = (short[:1] + rest)[:2] or od_rows[:2]
    arcs, _, _, _ = contract_od_path_union(
        G, union_rows, od_id, speed_policy=cfg.speed_policy
    )
    ordered = _ordered_arcs_for_path(arcs, path)
    notes: list[str] = []
    if not ordered:
        notes.append("no_decision_arcs_on_path")
        return OrderedElevationProfile(
            od_id=od_id,
            method=method,
            path_length_m=path_len,
            arc_ids=[],
            distances_m=np.array([]),
            elevations_m=np.array([]),
            notes=notes,
        )

    xs: list[np.ndarray] = []
    zs: list[np.ndarray] = []
    offset = 0.0
    boundaries = [0.0]
    missing: list[str] = []
    invalid: list[str] = []
    arc_ids: list[str] = []
    prev_end_z: float | None = None
    continuity_ok = True
    covered_len = 0.0
    # Gain/loss/grade accumulated *within* arcs only — never across junction jumps
    # or fabricated bridges over missing DEM segments.
    gain_total = 0.0
    loss_total = 0.0
    max_grade = float("nan")
    junction_jumps: list[float] = []

    meta_arcs = dem_meta.get("arcs", {})
    for arc in ordered:
        arc_ids.append(arc.arc_id)
        path_p = DEM_DIR / f"arc_{arc.arc_id}.json"
        m = meta_arcs.get(arc.arc_id, {})
        q = str(m.get("quality") or "")
        if q and q != "valid":
            invalid.append(arc.arc_id)
            notes.append(f"invalid_dem:{arc.arc_id}:{q}")
        if not path_p.exists():
            missing.append(arc.arc_id)
            # advance offset by arc length; do NOT invent elevations
            offset += float(arc.length_m)
            boundaries.append(offset)
            prev_end_z = None  # break continuity across missing segment
            notes.append(f"missing_profile:{arc.arc_id}")
            continue
        try:
            sample = load_profile(path_p)
            dist = np.asarray(sample.distances_m, dtype=float)
            elev = np.asarray(sample.elevations_m, dtype=float)
        except Exception as exc:  # noqa: BLE001
            missing.append(arc.arc_id)
            offset += float(arc.length_m)
            boundaries.append(offset)
            prev_end_z = None
            notes.append(f"load_fail:{arc.arc_id}:{exc}")
            continue
        if len(dist) == 0 or len(elev) == 0:
            missing.append(arc.arc_id)
            offset += float(arc.length_m)
            boundaries.append(offset)
            prev_end_z = None
            continue
        # localize distance to start at 0
        d_loc = dist - float(dist[0])
        # continuity check at junctions (diagnostic only; excluded from grade stats)
        if prev_end_z is not None and np.isfinite(elev[0]) and np.isfinite(prev_end_z):
            jump = abs(float(elev[0]) - float(prev_end_z))
            if jump > 5.0:  # meters — soft continuity threshold
                continuity_ok = False
                junction_jumps.append(jump)
                notes.append(f"elevation_jump_{jump:.1f}m_at_{arc.arc_id}")
        # Per-arc physical stats (full local samples, before junction dedupe)
        g_arc, l_arc = _gain_loss(elev)
        gain_total += g_arc
        loss_total += l_arc
        mg = _max_abs_grade(d_loc, elev)
        if np.isfinite(mg):
            max_grade = mg if not np.isfinite(max_grade) else max(max_grade, mg)
            if mg > 0.20:
                notes.append(f"steep_grade_{mg:.3f}_on_{arc.arc_id}")
        start_i = 1 if (drop_junction_duplicate and xs and len(d_loc) > 1) else 0
        d_use = d_loc[start_i:] + offset
        z_use = elev[start_i:]
        xs.append(d_use)
        zs.append(z_use)
        covered_len += float(arc.length_m)
        offset = float(d_use[-1]) if len(d_use) else offset + float(arc.length_m)
        boundaries.append(offset)
        prev_end_z = float(elev[-1]) if np.isfinite(elev[-1]) else None

    if xs:
        distances = np.concatenate(xs)
        elevations = np.concatenate(zs)
    else:
        distances = np.array([])
        elevations = np.array([])

    if junction_jumps:
        notes.append(
            f"junction_jumps_excluded_from_gain_loss_grade:n={len(junction_jumps)};"
            f"max_jump_m={max(junction_jumps):.1f}"
        )
    stitched = float(distances[-1]) if len(distances) else 0.0
    return OrderedElevationProfile(
        od_id=od_id,
        method=method,
        path_length_m=path_len,
        arc_ids=arc_ids,
        distances_m=distances,
        elevations_m=elevations,
        arc_boundaries_m=boundaries,
        missing_arc_ids=missing,
        invalid_arc_ids=invalid,
        dem_coverage_frac=(covered_len / path_len) if path_len > 0 else 0.0,
        stitched_length_m=stitched,
        length_error_m=stitched - path_len,
        cum_gain_m=gain_total,
        cum_loss_m=loss_total,
        max_abs_grade=max_grade,
        continuity_ok=continuity_ok,
        notes=notes,
    )


def reconstruct_elevation_from_arc_ids(
    arc_ids: Sequence[str],
    *,
    od_id: str = "executed",
    method: str = "executed_trace",
    drop_junction_duplicate: bool = True,
) -> OrderedElevationProfile:
    """Ordered elevation for an explicit executed DRIVE arc sequence."""
    notes: list[str] = []
    xs: list[np.ndarray] = []
    zs: list[np.ndarray] = []
    offset = 0.0
    boundaries = [0.0]
    missing: list[str] = []
    invalid: list[str] = []
    prev_end_z: float | None = None
    continuity_ok = True
    covered_len = 0.0
    path_len = 0.0
    gain_total = 0.0
    loss_total = 0.0
    max_grade = float("nan")
    junction_jumps: list[float] = []
    _, _, _, dem_meta = _graph_and_paths()
    meta_arcs = dem_meta.get("arcs", {})

    for aid in arc_ids:
        aid = str(aid)
        path_p = DEM_DIR / f"arc_{aid}.json"
        m = meta_arcs.get(aid, {})
        arc_len = float(m.get("length_m") or 0.0)
        q = str(m.get("quality") or "")
        if q and q != "valid":
            invalid.append(aid)
            notes.append(f"invalid_dem:{aid}:{q}")
        if not path_p.exists():
            missing.append(aid)
            notes.append(f"missing_profile:{aid}")
            # Do not invent geometry; still advance if meta length known
            if arc_len > 0:
                offset += arc_len
                path_len += arc_len
                boundaries.append(offset)
            prev_end_z = None
            continue
        try:
            sample = load_profile(path_p)
            dist = np.asarray(sample.distances_m, dtype=float)
            elev = np.asarray(sample.elevations_m, dtype=float)
        except Exception as exc:  # noqa: BLE001
            missing.append(aid)
            notes.append(f"load_fail:{aid}:{exc}")
            prev_end_z = None
            continue
        if len(dist) == 0 or len(elev) == 0:
            missing.append(aid)
            prev_end_z = None
            continue
        d_loc = dist - float(dist[0])
        if arc_len <= 0:
            arc_len = float(d_loc[-1]) if len(d_loc) else 0.0
        path_len += arc_len
        if prev_end_z is not None and np.isfinite(elev[0]) and np.isfinite(prev_end_z):
            jump = abs(float(elev[0]) - float(prev_end_z))
            if jump > 5.0:
                continuity_ok = False
                junction_jumps.append(jump)
                notes.append(f"elevation_jump_{jump:.1f}m_at_{aid}")
        g_arc, l_arc = _gain_loss(elev)
        gain_total += g_arc
        loss_total += l_arc
        mg = _max_abs_grade(d_loc, elev)
        if np.isfinite(mg):
            max_grade = mg if not np.isfinite(max_grade) else max(max_grade, mg)
        start_i = 1 if (drop_junction_duplicate and xs and len(d_loc) > 1) else 0
        d_use = d_loc[start_i:] + offset
        z_use = elev[start_i:]
        xs.append(d_use)
        zs.append(z_use)
        covered_len += arc_len
        offset = float(d_use[-1]) if len(d_use) else offset + arc_len
        boundaries.append(offset)
        prev_end_z = float(elev[-1]) if np.isfinite(elev[-1]) else None

    if junction_jumps:
        notes.append(
            f"junction_jumps_excluded_from_gain_loss_grade:n={len(junction_jumps)};"
            f"max_jump_m={max(junction_jumps):.1f}"
        )
    distances = np.concatenate(xs) if xs else np.array([])
    elevations = np.concatenate(zs) if zs else np.array([])
    stitched = float(distances[-1]) if len(distances) else 0.0
    return OrderedElevationProfile(
        od_id=od_id,
        method=method,
        path_length_m=path_len,
        arc_ids=[str(a) for a in arc_ids],
        distances_m=distances,
        elevations_m=elevations,
        arc_boundaries_m=boundaries,
        missing_arc_ids=missing,
        invalid_arc_ids=invalid,
        dem_coverage_frac=(covered_len / path_len) if path_len > 0 else 0.0,
        stitched_length_m=stitched,
        length_error_m=stitched - path_len,
        cum_gain_m=gain_total,
        cum_loss_m=loss_total,
        max_abs_grade=max_grade,
        continuity_ok=continuity_ok,
        notes=notes,
    )


def reconstruct_all_od_methods(
    od_ids: Sequence[str] | None = None,
) -> pd.DataFrame:
    """Summary table: one row per (od_id, method)."""
    _, path_rows, _, _ = _graph_and_paths()
    if od_ids is None:
        od_ids = sorted({str(r["od_id"]) for r in path_rows})
    rows = []
    for od in od_ids:
        methods = sorted(
            {
                str(r.get("method") or "")
                for r in path_rows
                if str(r.get("od_id")) == od
            }
        )
        for method in methods:
            if not method:
                continue
            prof = reconstruct_od_elevation(od, method=method)
            rows.append(
                {
                    "od_id": od,
                    "method": method,
                    "path_length_m": prof.path_length_m,
                    "path_length_km": prof.path_length_m / 1000.0,
                    "n_arcs": len(prof.arc_ids),
                    "n_missing_profiles": len(prof.missing_arc_ids),
                    "n_invalid_profiles": len(prof.invalid_arc_ids),
                    "dem_coverage_frac": prof.dem_coverage_frac,
                    "stitched_length_m": prof.stitched_length_m,
                    "length_error_m": prof.length_error_m,
                    "length_error_pct": (
                        100.0 * prof.length_error_m / prof.path_length_m
                        if prof.path_length_m
                        else float("nan")
                    ),
                    "cum_gain_m": prof.cum_gain_m,
                    "cum_loss_m": prof.cum_loss_m,
                    "max_abs_grade": prof.max_abs_grade,
                    "continuity_ok": prof.continuity_ok,
                    "arc_ids": ",".join(prof.arc_ids),
                    "missing_arc_ids": ",".join(prof.missing_arc_ids),
                    "invalid_arc_ids": ",".join(prof.invalid_arc_ids),
                    "notes": ";".join(prof.notes),
                }
            )
    return pd.DataFrame(rows)


def audit_decision_arc_dem_coverage() -> pd.DataFrame:
    """Coverage of DEM profiles vs OD-local decision arcs (not mere file counts)."""
    G, path_rows, cfg, dem_meta = _graph_and_paths()
    meta_arcs = dem_meta.get("arcs", {})
    rows = []
    ods = sorted({str(r["od_id"]) for r in path_rows})
    for od in ods:
        od_rows = [r for r in path_rows if str(r.get("od_id")) == od]
        short = [r for r in od_rows if str(r.get("method")) == "shortest_distance"]
        rest = sorted(
            [r for r in od_rows if str(r.get("method")) != "shortest_distance"],
            key=lambda r: -float(r.get("jaccard_distance_vs_shortest") or 0.0),
        )
        union_rows = (short[:1] + rest)[:2] or od_rows[:2]
        arcs, _, _, _ = contract_od_path_union(
            G, union_rows, od, speed_policy=cfg.speed_policy
        )
        for arc in arcs:
            p = DEM_DIR / f"arc_{arc.arc_id}.json"
            m = meta_arcs.get(arc.arc_id, {})
            rows.append(
                {
                    "od_id": od,
                    "arc_id": arc.arc_id,
                    "u": arc.u,
                    "v": arc.v,
                    "length_m": arc.length_m,
                    "profile_exists": p.exists(),
                    "meta_quality": m.get("quality"),
                    "meta_od_id_provenance": m.get("od_id"),
                    "source": m.get("source"),
                }
            )
    return pd.DataFrame(rows)


def investigate_invalid_profiles() -> pd.DataFrame:
    G, path_rows, cfg, dem_meta = _graph_and_paths()
    rows = []
    for aid, m in (dem_meta.get("arcs") or {}).items():
        if str(m.get("quality")) == "valid":
            continue
        p = DEM_DIR / f"arc_{aid}.json"
        detail = {
            "arc_id": aid,
            "od_id": m.get("od_id"),
            "quality": m.get("quality"),
            "length_m": m.get("length_m"),
            "source": m.get("source"),
            "profile_exists": p.exists(),
            "z_min": m.get("z_min"),
            "z_max": m.get("z_max"),
            "max_abs_grade": m.get("max_abs_grade"),
        }
        if p.exists():
            try:
                raw = json.loads(p.read_text(encoding="utf-8"))
                q = (raw.get("meta") or {}).get("quality") or {}
                detail["profile_status"] = q.get("status")
                detail["profile_notes"] = ";".join(q.get("notes") or [])
                detail["n_samples"] = (raw.get("meta") or {}).get("n_samples")
                detail["n_valid"] = (raw.get("meta") or {}).get("n_valid")
            except Exception as exc:  # noqa: BLE001
                detail["profile_notes"] = str(exc)
        rows.append(detail)
    return pd.DataFrame(rows)
