#!/usr/bin/env python3
"""R-Figure 1 — Infrastructure coverage by vehicle and SOC scenario."""
from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
EXP = ROOT / "results/final_evidence/experiments/primary_comparison"
FIG = ROOT / "results/final_evidence/figures/results"
SRC = FIG / "source_data"

INFRA_ORDER = ["I0_none", "I1_benguerir_ca", "I2_benguerir_larache"]
INFRA_LABELS = ["I0 (none)", "I1 (Benguerir CA)", "I2 (+Larache RT)"]
VEH_COLOR = {"eactros_600": "#0072B2", "volvo_475": "#E69F00"}


def main() -> int:
    summary_path = EXP / "primary_summary.csv"
    if not summary_path.exists():
        print("Missing", summary_path)
        return 1
    FIG.mkdir(parents=True, exist_ok=True)
    SRC.mkdir(parents=True, exist_ok=True)
    df = pd.read_csv(summary_path)
    df.to_csv(SRC / "R-Fig1_primary_summary.csv", index=False)

    scenarios = [s for s in ["stressed_mixed", "common_soc_80"] if s in set(df.soc_scenario)]
    vehicles = [v for v in ["eactros_600", "volvo_475"] if v in set(df.vehicle_key)]
    if not scenarios or not vehicles:
        print("Incomplete summary")
        return 1

    fig, axes = plt.subplots(1, len(scenarios), figsize=(5.2 * len(scenarios), 4.2), sharey=True)
    if len(scenarios) == 1:
        axes = [axes]
    fig.patch.set_facecolor("white")

    x = np.arange(len(INFRA_ORDER))
    width = 0.35
    for ax, soc in zip(axes, scenarios):
        ax.set_facecolor("white")
        sub = df[df.soc_scenario == soc]
        for i, veh in enumerate(vehicles):
            vals = []
            unres = []
            for infra in INFRA_ORDER:
                row = sub[(sub.vehicle_key == veh) & (sub.infra_config_id == infra)]
                if len(row):
                    vals.append(int(row.iloc[0]["ops_served"]))
                    unres.append(int(row.iloc[0].get("n_limit_reached", 0) or 0))
                else:
                    vals.append(0)
                    unres.append(0)
            offset = (i - 0.5 * (len(vehicles) - 1)) * width
            bars = ax.bar(
                x + offset,
                vals,
                width=width,
                color=VEH_COLOR.get(veh, "#999999"),
                label=veh,
                edgecolor="black",
                linewidth=0.4,
            )
            for b, v, u in zip(bars, vals, unres):
                ax.text(b.get_x() + b.get_width() / 2, v + 0.15, f"{v}/14", ha="center", va="bottom", fontsize=8)
                if u:
                    ax.scatter(
                        b.get_x() + b.get_width() / 2,
                        v + 0.8,
                        marker="D",
                        c="#D55E00",
                        s=30,
                        zorder=5,
                    )
        ax.set_xticks(x)
        ax.set_xticklabels(INFRA_LABELS, fontsize=8)
        ax.set_ylim(0, 15)
        ax.set_ylabel("Operationally served missions" if ax is axes[0] else "")
        title = "Stressed mixed SOC" if soc == "stressed_mixed" else "Common 80% departure SOC"
        ax.set_title(title)
        ax.axhline(14, color="#999999", ls=":", lw=0.8)
        ax.legend(fontsize=8, loc="upper left")
        ax.grid(axis="y", linestyle=":", linewidth=0.4)

    fig.suptitle("R-Figure 1 — Infrastructure coverage by vehicle and departure-SOC scenario", fontsize=11)
    base = FIG / "R-Figure1_infrastructure_coverage"
    fig.savefig(base.with_suffix(".pdf"))
    fig.savefig(base.with_suffix(".png"), dpi=400)
    fig.savefig(base.with_suffix(".svg"))
    plt.close(fig)
    print("Wrote", base)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
