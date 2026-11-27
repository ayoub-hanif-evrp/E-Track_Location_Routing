#!/usr/bin/env python3
"""R-Figure 12 — Charging power vs SOC taper envelope + matched mission comparison."""
from __future__ import annotations

import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from morocco_etruck.energy.vehicle import conservative_ccs_taper_factor  # noqa: E402

FE = ROOT / "results/final_evidence"
FIG = FE / "figures/results"
SRC = FIG / "source_data"
C = {"blue": "#0072B2", "orange": "#E69F00", "green": "#009E73", "vermillion": "#D55E00"}


def main() -> None:
    FIG.mkdir(parents=True, exist_ok=True)
    SRC.mkdir(parents=True, exist_ok=True)
    soc = np.linspace(0.0, 1.0, 201)
    factor = np.array([conservative_ccs_taper_factor(float(s)) for s in soc])
    p_name = 350.0
    p_tap = p_name * factor
    p_const = np.full_like(soc, p_name)

    fig, axes = plt.subplots(1, 2, figsize=(10.5, 4.2), constrained_layout=True)
    ax = axes[0]
    ax.plot(soc * 100, p_const, color=C["blue"], lw=2, label="Constant (nameplate)")
    ax.plot(soc * 100, p_tap, color=C["orange"], lw=2, label="Research taper envelope")
    ax.axvline(60, color=C["green"], ls=":", lw=1)
    ax.set_xlabel("SOC (%)")
    ax.set_ylabel("Accepted charge power (kW)")
    ax.set_title("(a) Charging power vs SOC")
    ax.legend(fontsize=8)
    ax.grid(True, ls=":", lw=0.4)
    ax.text(0.02, 0.02, "Not an OEM-measured curve", transform=ax.transAxes, fontsize=7)

    ax2 = axes[1]
    offline_p = FE / "experiments/charging_taper_comparison/identical_soc_interval_continuous.csv"
    cmp_p = FE / "experiments/charging_taper_comparison/constant_vs_taper_missions.csv"
    plotted = False
    if offline_p.exists():
        off = pd.read_csv(offline_p)
        labels, const_m, tap_m = [], [], []
        for _, r in off.iterrows():
            labels.append(f"{str(r['vehicle_key'])[:3]} {r['od_id']}\nSOC{float(r['soc_frac']):.1f}")
            const_m.append(float(r.get("minutes_constant_continuous") or 0))
            tap_m.append(float(r.get("minutes_taper_continuous") or 0))
        x = np.arange(len(labels))
        w = 0.35
        if labels:
            ax2.bar(x - w / 2, const_m, w, color=C["blue"], label="Constant (cont.)")
            ax2.bar(x + w / 2, tap_m, w, color=C["orange"], label="Taper (cont.)")
            # overlay discrete reopt markers when available
            if "minutes_reopt_constant_discrete" in off.columns:
                ax2.scatter(
                    x - w / 2,
                    off["minutes_reopt_constant_discrete"].astype(float),
                    marker="D",
                    s=28,
                    color=C["blue"],
                    edgecolors="k",
                    linewidths=0.4,
                    zorder=3,
                    label="Discrete reopt",
                )
                ax2.scatter(
                    x + w / 2,
                    off["minutes_reopt_taper_discrete"].astype(float),
                    marker="D",
                    s=28,
                    color=C["orange"],
                    edgecolors="k",
                    linewidths=0.4,
                    zorder=3,
                )
            ax2.set_xticks(x)
            ax2.set_xticklabels(labels, fontsize=7)
            ax2.set_ylabel("Charging duration (min)")
            ax2.legend(fontsize=7)
            off.to_csv(SRC / "R-Fig12_charging_comparison.csv", index=False)
            plotted = True
    elif cmp_p.exists():
        df = pd.read_csv(cmp_p)
        labels, const_m, tap_m = [], [], []
        for (vk, od, soc_f), g in df.groupby(["vehicle_key", "od_id", "soc_frac"]):
            g = g.set_index("apply_taper")
            if True in g.index and False in g.index:
                labels.append(f"{vk[:3]} {od}\nSOC{soc_f:.1f}")
                const_m.append(float(g.loc[False].get("charge_min_phys") or 0))
                tap_m.append(float(g.loc[True].get("charge_min_phys") or 0))
        x = np.arange(len(labels))
        w = 0.35
        if labels:
            ax2.bar(x - w / 2, const_m, w, color=C["blue"], label="Constant")
            ax2.bar(x + w / 2, tap_m, w, color=C["orange"], label="Taper")
            ax2.set_xticks(x)
            ax2.set_xticklabels(labels, fontsize=7)
            ax2.set_ylabel("Charging duration (min)")
            ax2.legend(fontsize=8)
            df.to_csv(SRC / "R-Fig12_charging_comparison.csv", index=False)
            plotted = True
    if not plotted:
        ax2.text(0.5, 0.5, "Awaiting comparison runs", ha="center", va="center")
    ax2.set_title("(b) Identical SOC-interval duration")
    ax2.grid(True, axis="y", ls=":", lw=0.4)

    pd.DataFrame(
        {"soc_frac": soc, "taper_factor": factor, "P_const_kw": p_const, "P_taper_kw": p_tap}
    ).to_csv(SRC / "R-Fig12_taper_envelope.csv", index=False)
    fig.suptitle(
        "R-Figure 12 — Constant vs research SOC-dependent charging taper",
        fontsize=11,
    )
    base = FIG / "R-Figure12_charging_constant_vs_taper"
    fig.savefig(base.with_suffix(".pdf"))
    fig.savefig(base.with_suffix(".png"), dpi=400)
    plt.close(fig)
    (FIG / "R-Figure12_description.md").write_text(
        "R-Figure 12: (a) research taper envelope vs constant nameplate power "
        "(not OEM-measured); (b) continuous minutes for identical SOC intervals "
        "with discrete 5-min reoptimization markers when available.\n",
        encoding="utf-8",
    )
    print("Wrote", base)


if __name__ == "__main__":
    main()
