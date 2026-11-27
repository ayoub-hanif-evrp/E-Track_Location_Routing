#!/usr/bin/env python3
"""R-Figure 11 — Refrigeration energy contribution near boundary missions."""
from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
FE = ROOT / "results/final_evidence"
FIG = FE / "figures/results"
SRC = FIG / "source_data"
C = {"blue": "#0072B2", "orange": "#E69F00", "green": "#009E73", "grey": "#999999"}


def main() -> None:
    FIG.mkdir(parents=True, exist_ok=True)
    SRC.mkdir(parents=True, exist_ok=True)
    p = FE / "experiments/journal_p2_p4/refrigeration_controlled_missions.csv"
    df = pd.read_csv(p)
    df = df[(df.vehicle_key == "eactros_600") & (df.operationally_served == True)].copy()  # noqa: E712
    order = ["refrig_off", "tomato_9C_cool", "tomato_9C_hot", "tomato_UA_x1p5_hot"]
    labels = ["Off", "9°C cool", "9°C hot", "UA×1.5 hot"]
    fig, axes = plt.subplots(1, 2, figsize=(9.5, 3.8), constrained_layout=True)
    for ax, od, title in zip(
        axes,
        ["casa_marrakech", "casa_agadir"],
        ["Casablanca–Marrakech", "Casablanca–Agadir"],
    ):
        sub = df[df.od_id == od].set_index("variant").reindex(order)
        x = range(len(order))
        er = sub.E_refrig_kwh.fillna(0.0).tolist()
        et = sub.E_traction_kwh.tolist()
        share = [100.0 * a / b if b and b == b else 0 for a, b in zip(er, et)]
        ax.bar(x, er, color=C["blue"], label="E_refrig (kWh)")
        ax2 = ax.twinx()
        ax2.plot(x, share, "o-", color=C["orange"], label="% of traction")
        ax.set_xticks(list(x))
        ax.set_xticklabels(labels, fontsize=8)
        ax.set_ylabel("Refrigeration energy (kWh)")
        ax2.set_ylabel("Share of traction (%)")
        ax.set_title(title)
        ax.grid(True, axis="y", ls=":", lw=0.4)
        # annotate min SOC
        for i, ms in enumerate(sub.min_soc.tolist()):
            if ms == ms:
                ax.text(i, er[i] + max(er) * 0.03, f"SOC={ms:.3f}", ha="center", fontsize=7)
    fig.suptitle(
        "R-Figure 11 — Refrigeration electrical demand near SOC thresholds (eActros, I1)",
        fontsize=11,
    )
    df.to_csv(SRC / "R-Fig11_refrigeration_controlled.csv", index=False)
    base = FIG / "R-Figure11_refrigeration_contribution"
    fig.savefig(base.with_suffix(".pdf"))
    fig.savefig(base.with_suffix(".png"), dpi=400)
    plt.close(fig)
    (FIG / "R-Figure11_description.md").write_text(
        "R-Figure 11: Controlled refrigeration variants (off / 9°C cool / 9°C hot / UA×1.5 hot) "
        "on Casa–Marrakech and Casa–Agadir near departure-SOC thresholds. Bars = refrigerator "
        "kWh; orange = share of traction. All shown cells remain operationally served; "
        "refrigeration does not change I1 infrastructure requirements here.\n",
        encoding="utf-8",
    )
    print("Wrote", base)


if __name__ == "__main__":
    main()
