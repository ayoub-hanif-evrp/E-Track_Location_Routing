#!/usr/bin/env python3
"""D-Figure 5 — Elevation/terrain characterization for representative corridors."""
from __future__ import annotations

import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
FIG = ROOT / "results/final_evidence/figures/dataset"
SRC = FIG / "source_data"
DEM = ROOT / "data/processed/multiroute/elevation"

# Representative corridors (both directions where available)
CORRIDORS = [
    ("casa_agadir", "Casablanca → Agadir"),
    ("agadir_casa", "Agadir → Casablanca"),
    ("casa_marrakech", "Casablanca → Marrakech"),
    ("rabat_fes", "Rabat → Fès"),
]


def _profiles_for_od(od: str) -> list[dict]:
    meta = json.loads((DEM / "dem_sampling_meta.json").read_text(encoding="utf-8"))
    arcs = meta.get("arcs", {})
    out = []
    for aid, m in arcs.items():
        if m.get("od_id") != od:
            continue
        p = DEM / f"arc_{aid}.json"
        if not p.exists():
            continue
        prof = json.loads(p.read_text(encoding="utf-8"))
        z = prof.get("elevations_m") or prof.get("z") or prof.get("elevation_m")
        dist = prof.get("distances_m") or prof.get("s_m") or prof.get("cum_distance_m")
        if not z:
            continue
        z = np.asarray(z, dtype=float)
        if dist is None:
            # approximate uniform along length
            length = float(m.get("length_m") or 0.0)
            dist = np.linspace(0.0, length, len(z))
        else:
            dist = np.asarray(dist, dtype=float)
        out.append({"arc_id": aid, "dist": dist, "z": z, "meta": m})
    return out


def _stitch(profiles: list[dict]) -> tuple[np.ndarray, np.ndarray]:
    """Naive stitch by concatenating arc profiles with cumulative distance offset."""
    if not profiles:
        return np.array([]), np.array([])
    # Sort by starting elevation span length descending then arc id for stability
    profiles = sorted(profiles, key=lambda p: (-float(p["meta"].get("length_m") or 0), p["arc_id"]))
    # Better: use order from decision graph is hard; concatenate all samples with offset by length sum
    xs, zs = [], []
    offset = 0.0
    for p in profiles:
        d = np.asarray(p["dist"], dtype=float)
        if len(d) == 0:
            continue
        d0 = d - d[0] + offset
        xs.append(d0)
        zs.append(p["z"])
        offset = float(d0[-1])
    if not xs:
        return np.array([]), np.array([])
    return np.concatenate(xs), np.concatenate(zs)


def main() -> None:
    FIG.mkdir(parents=True, exist_ok=True)
    SRC.mkdir(parents=True, exist_ok=True)
    dem_arcs = pd.read_csv(ROOT / "results/final_evidence/dataset/dem_arc_meta_summary.csv")

    fig, axes = plt.subplots(2, 2, figsize=(11, 7), constrained_layout=True)
    fig.patch.set_facecolor("white")
    for ax, (od, title) in zip(axes.ravel(), CORRIDORS):
        profs = _profiles_for_od(od)
        x, z = _stitch(profs)
        ax.set_facecolor("white")
        if len(x):
            ax.plot(x / 1000.0, z, color="#0072B2", lw=1.2)
            dz = np.diff(z)
            gain = float(dz[dz > 0].sum()) if len(dz) else 0.0
            loss = float((-dz[dz < 0]).sum()) if len(dz) else 0.0
            ax.set_title(f"{title}\n+{gain:.0f} m / −{loss:.0f} m (stitched arcs)")
            pd.DataFrame({"distance_km": x / 1000.0, "elevation_m": z}).to_csv(
                SRC / f"D-Fig5_{od}_profile.csv", index=False
            )
        else:
            ax.set_title(f"{title}\n(no profiles)")
            ax.text(0.5, 0.5, "No DEM profiles", ha="center", transform=ax.transAxes)
        ax.set_xlabel("Distance along stitched arcs (km)")
        ax.set_ylabel("Elevation (m)")
        ax.grid(True, ls=":", lw=0.4)

    # Extra panel note: dataset-level grade hist already in D-Fig6; add compact inset summary
    fig.suptitle("D-Figure 5 — DEM elevation profiles (representative corridors)", fontsize=12)
    base = FIG / "D-Figure5_elevation_profiles"
    fig.savefig(base.with_suffix(".pdf"))
    fig.savefig(base.with_suffix(".png"), dpi=400)
    fig.savefig(base.with_suffix(".svg"))
    plt.close(fig)

    # Grade distribution companion
    fig2, ax = plt.subplots(figsize=(5.5, 3.8))
    g = dem_arcs["max_abs_grade"].dropna() * 100
    ax.hist(g, bins=30, color="#56B4E9", edgecolor="white")
    ax.set_xlabel("Arc max |grade| (%)")
    ax.set_ylabel("Count")
    ax.set_title("Dataset-level road gradient distribution")
    g.describe().to_frame("max_abs_grade_pct").to_csv(SRC / "D-Fig5_grade_distribution.csv")
    base2 = FIG / "D-Figure5b_gradient_distribution"
    fig2.savefig(base2.with_suffix(".pdf"))
    fig2.savefig(base2.with_suffix(".png"), dpi=400)
    plt.close(fig2)
    print("Wrote", base, base2)


if __name__ == "__main__":
    main()
