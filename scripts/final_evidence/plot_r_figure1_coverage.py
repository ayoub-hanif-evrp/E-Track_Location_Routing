#!/usr/bin/env python3
"""R-Figure 1 — Infrastructure coverage by vehicle and SOC scenario (I0–I3)."""
from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
PANEL = ROOT / "results/final_evidence/experiments/primary_i0_i3_panel"
FALLBACK = ROOT / "results/final_evidence/tables/results/R-T02_infrastructure_coverage.csv"
FIG = ROOT / "results/final_evidence/figures/results"
SRC = FIG / "source_data"

INFRA_ORDER = [
    "I0_none",
    "I1_benguerir_ca",
    "I2_benguerir_larache",
    "I3_benguerir_ca_larache_benguerir_ac",
]
INFRA_LABELS = [
    "I0\n(none)",
    "I1\n(+Benguerir CA)",
    "I2\n(+Larache RT)",
    "I3\n(+Benguerir AC)",
]
VEH_COLOR = {"eactros_600": "#0072B2", "volvo_475": "#E69F00"}


def main() -> int:
    summary_path = PANEL / "primary_i0_i3_summary.csv"
    if not summary_path.exists():
        summary_path = FALLBACK
    if not summary_path.exists():
        print("Missing coverage summary")
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

    fig, axes = plt.subplots(1, len(scenarios), figsize=(6.2 * len(scenarios), 4.4), sharey=True)
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
            for infra in INFRA_ORDER:
                row = sub[(sub.vehicle_key == veh) & (sub.infra_config_id == infra)]
                vals.append(int(row.iloc[0]["ops_served"]) if len(row) else 0)
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
            for b, v in zip(bars, vals):
                ax.text(
                    b.get_x() + b.get_width() / 2,
                    v + 0.15,
                    f"{v}/14",
                    ha="center",
                    va="bottom",
                    fontsize=8,
                )
        ax.set_xticks(x)
        ax.set_xticklabels(INFRA_LABELS, fontsize=8)
        ax.set_ylim(0, 15)
        ax.set_ylabel("Operationally served missions" if ax is axes[0] else "")
        ax.set_title(soc.replace("_", " "))
        ax.axhline(14, color="#999999", ls=":", lw=0.8)
        ax.grid(True, axis="y", ls=":", lw=0.4)
        ax.legend(fontsize=8, loc="lower right")
    fig.suptitle(
        "R-Figure 1 — Coverage ladder I0–I3 (directional installations; not claimed optimal)",
        fontsize=11,
    )
    base = FIG / "R-Figure1_infrastructure_coverage"
    fig.savefig(base.with_suffix(".pdf"))
    fig.savefig(base.with_suffix(".png"), dpi=400)
    fig.savefig(base.with_suffix(".svg"))
    plt.close(fig)
    (FIG / "R-Figure1_description.md").write_text(
        "R-Figure 1: operational coverage for eActros/Volvo under stressed and common-SOC "
        "scenarios across I0–I3. Bars count operationally served missions out of 14. "
        "I3 adds a third directional installation (Benguerir AC). No global optimality or "
        "minimum-infrastructure claim.\n",
        encoding="utf-8",
    )
    print("Wrote", base)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
