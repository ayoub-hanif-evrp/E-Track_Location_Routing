#!/usr/bin/env python3
"""P3 — Casa–Marrakech three-outcome terrain figure (flat fixed / DEM fixed / DEM flex)."""
from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
FE = ROOT / "results/final_evidence"
FIG = FE / "figures/results"
SRC = FIG / "source_data"
C = {"blue": "#0072B2", "vermillion": "#D55E00", "green": "#009E73", "orange": "#E69F00", "grey": "#999999"}


def main() -> int:
    FIG.mkdir(parents=True, exist_ok=True)
    SRC.mkdir(parents=True, exist_ok=True)
    m = pd.read_csv(FE / "experiments/dem_vs_flat/dem_vs_flat_missions.csv")
    cm = m[(m.od_id == "casa_marrakech") & (m.soc_frac == 0.5)].copy()

    panels = [
        ("flat", "fixed_short", "Flat-road fixed route"),
        ("dem", "fixed_short", "DEM-aware fixed route"),
        ("dem", "reoptimized_multi", "DEM-aware flexible route"),
    ]
    rows = []
    fig, axes = plt.subplots(1, 3, figsize=(12.5, 4.2), constrained_layout=True)
    fig.patch.set_facecolor("white")
    for ax, (terrain, mode, title) in zip(axes, panels):
        hit = cm[(cm.terrain_mode == terrain) & (cm.route_mode == mode)]
        ax.set_facecolor("#fafafa")
        if not len(hit):
            ax.set_title(title + "\n(missing)")
            ax.axis("off")
            continue
        r = hit.iloc[0]
        served = bool(r.operationally_served)
        status = str(r.status)
        road = r.road_km if pd.notna(r.road_km) else None
        traction = r.E_traction_kwh if pd.notna(getattr(r, "E_traction_kwh", None)) else None
        charge = r.E_charge_kwh if pd.notna(getattr(r, "E_charge_kwh", None)) else None
        color = C["green"] if served else C["vermillion"]
        ax.bar([0], [1 if served else 0.35], color=color, width=0.55, edgecolor="black", lw=0.5)
        ax.set_ylim(0, 1.35)
        ax.set_xticks([])
        ax.set_yticks([])
        label = "FEASIBLE" if served else f"INFEASIBLE\n({status})"
        ax.text(0, 1.05, label, ha="center", va="bottom", fontsize=11, fontweight="bold", color=color)
        detail = [
            f"route_mode={mode}",
            f"terrain={terrain}",
            f"road_km={road:.2f}" if road is not None else "road_km=n/a (no OPTIMAL trace)",
            f"traction_kWh={traction:.1f}" if traction is not None else "traction_kWh=n/a",
            f"charge_kWh={charge:.1f}" if charge is not None else "charge_kWh=n/a",
            f"installed={r.installed or 'none'}",
        ]
        ax.text(0, 0.45 if served else 0.12, "\n".join(detail), ha="center", va="bottom", fontsize=8)
        ax.set_title(title, fontsize=10)
        rows.append(
            {
                "panel": title,
                "terrain_mode": terrain,
                "route_mode": mode,
                "status": status,
                "operationally_served": served,
                "road_km": road,
                "E_traction_kwh": traction,
                "E_charge_kwh": charge,
                "installed": r.installed,
                "route_id": r.route_id if pd.notna(getattr(r, "route_id", None)) else "",
            }
        )
    fig.suptitle(
        "Casa–Marrakech @ 50% SOC — flat fixed vs DEM fixed vs DEM flexible (Benguerir CA)",
        fontsize=11,
    )
    base = FIG / "R-Figure9b_casa_marrakech_terrain_triptych"
    fig.savefig(base.with_suffix(".pdf"))
    fig.savefig(base.with_suffix(".png"), dpi=400)
    fig.savefig(base.with_suffix(".svg"))
    plt.close(fig)
    pd.DataFrame(rows).to_csv(SRC / "R-Fig9b_casa_marrakech_triptych.csv", index=False)
    (FIG / "R-Figure9b_description.md").write_text(
        "Three-outcome Casa–Marrakech contrast at 50% SOC: flat fixed feasible without charging; "
        "DEM fixed infeasible (no zero-energy claim); DEM flexible may restore service via "
        "Benguerir charging / route selection. Energy fields are missing when no OPTIMAL trace.\n",
        encoding="utf-8",
    )
    print("Wrote", base)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
