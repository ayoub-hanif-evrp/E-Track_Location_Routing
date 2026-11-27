#!/usr/bin/env python3
"""R-Figure 3 — Mission-level feasibility matrix."""
from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.colors import ListedColormap
from matplotlib.patches import Patch

ROOT = Path(__file__).resolve().parents[2]
PANEL = ROOT / "results/final_evidence/experiments/primary_i0_i3_panel/primary_i0_i3_missions.csv"
FALLBACK = ROOT / "results/final_evidence/experiments/primary_comparison/primary_missions.csv"
FIG = ROOT / "results/final_evidence/figures/results"
SRC = FIG / "source_data"

STATE = {
    "feasible": 3,
    "infeasible": 1,
    "unresolved": 2,
    "audit_failed": 0,
    "missing": -1,
}
# colorblind-ish discrete
CMAP = ListedColormap(["#999999", "#D55E00", "#F0E442", "#009E73", "#FFFFFF"])
# indices: audit_failed=0, infeasible=1, unresolved=2, feasible=3, missing mapped separately


def _state(row) -> int:
    status = str(row.get("status", ""))
    ops = bool(row.get("operationally_served")) if pd.notna(row.get("operationally_served")) else False
    if status == "LIMIT_REACHED":
        return STATE["unresolved"]
    if status == "INFEASIBLE":
        return STATE["infeasible"]
    if status == "OPTIMAL" and ops:
        return STATE["feasible"]
    if status == "OPTIMAL" and not ops:
        return STATE["audit_failed"]
    return STATE["missing"]


def main() -> int:
    path = PANEL if PANEL.exists() else FALLBACK
    if not path.exists():
        print("Missing", path)
        return 1
    FIG.mkdir(parents=True, exist_ok=True)
    SRC.mkdir(parents=True, exist_ok=True)
    df = pd.read_csv(path)
    df["cell"] = (
        df["vehicle_key"].astype(str)
        + "|"
        + df["soc_scenario"].astype(str)
        + "|"
        + df["infra_config_id"].astype(str)
    )
    df["state"] = df.apply(_state, axis=1)
    ods = sorted(df["od_id"].unique())
    cells = []
    for veh in ["eactros_600", "volvo_475"]:
        for soc in ["stressed_mixed", "common_soc_80"]:
            for infra in [
                "I0_none",
                "I1_benguerir_ca",
                "I2_benguerir_larache",
                "I3_benguerir_ca_larache_benguerir_ac",
            ]:
                cells.append(f"{veh}|{soc}|{infra}")
    # Keep only cells present
    present = [c for c in cells if c in set(df["cell"])]
    mat = np.full((len(ods), len(present)), -1, dtype=float)
    for j, cell in enumerate(present):
        sub = df[df.cell == cell].set_index("od_id")
        for i, od in enumerate(ods):
            if od in sub.index:
                mat[i, j] = float(sub.loc[od, "state"])
    pd.DataFrame(mat, index=ods, columns=present).to_csv(SRC / "R-Fig3_feasibility_matrix.csv")

    fig, ax = plt.subplots(figsize=(max(8, 0.55 * len(present) + 3), 0.35 * len(ods) + 2))
    fig.patch.set_facecolor("white")
    # map -1 to NaN for white
    plot = np.ma.masked_where(mat < 0, mat)
    im = ax.imshow(plot, aspect="auto", cmap=CMAP, vmin=0, vmax=3)
    ax.set_yticks(range(len(ods)))
    ax.set_yticklabels(ods, fontsize=8)
    ax.set_xticks(range(len(present)))
    ax.set_xticklabels(
        [c.replace("stressed_mixed", "stress").replace("common_soc_80", "soc80") for c in present],
        rotation=90,
        fontsize=7,
    )
    ax.set_title("R-Figure 3 — Mission feasibility matrix")
    legend = [
        Patch(facecolor="#009E73", label="Feasible (ops)"),
        Patch(facecolor="#D55E00", label="Infeasible"),
        Patch(facecolor="#F0E442", label="Unresolved (LIMIT)"),
        Patch(facecolor="#999999", label="Audit-failed"),
    ]
    ax.legend(handles=legend, loc="upper left", bbox_to_anchor=(1.02, 1), fontsize=8)
    fig.tight_layout()
    base = FIG / "R-Figure3_feasibility_matrix"
    fig.savefig(base.with_suffix(".pdf"))
    fig.savefig(base.with_suffix(".png"), dpi=400)
    fig.savefig(base.with_suffix(".svg"))
    plt.close(fig)
    print("Wrote", base, "cells=", len(present))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
