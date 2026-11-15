#!/usr/bin/env python
"""Generate publication figures from committed CSV results (no hardcoded claims)."""

from __future__ import annotations

import csv
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIG = ROOT / "paper" / "figures"
FIG.mkdir(parents=True, exist_ok=True)


def _read(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as f:
        return list(csv.DictReader(f))


def main() -> int:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    audit = _read(ROOT / "results/final_action_rounding_audit.csv")
    hist = _read(ROOT / "results/moroccan_energy_grid_convergence.csv")
    rob = _read(ROOT / "results/final_moroccan_robustness_matrix.csv")
    trace = _read(ROOT / "results/final_physical_trace_metrics.csv")
    bb = _read(ROOT / "results/bb_relaxed_bound_before_after.csv")

    # Fig 3 — q convergence: feasibility / charge / floor loss / labels
    qs, chg, loss, labs, feas = [], [], [], [], []
    src = audit or [
        r
        for r in hist
        if str(r.get("panel", "")).startswith("northbound")
    ]
    for r in src:
        try:
            q = int(float(r.get("q")))
        except (TypeError, ValueError):
            continue
        qs.append(q)
        chg.append(float(r.get("disc_charge_kwh") or r.get("charge_kwh") or 0))
        loss.append(float(r.get("audit_floor_loss_kwh") or r.get("cum_drive_rounding_loss_kwh") or 0))
        labs.append(float(r.get("mrls_labels_generated") or 0))
        feas.append(1 if str(r.get("status") or r.get("ball_status")) == "OPTIMAL" else 0)

    if qs:
        fig, ax = plt.subplots(1, 2, figsize=(9, 3.6))
        ax[0].plot(qs, chg, "o-", label="Discrete charge kWh")
        ax[0].plot(qs, loss, "s--", label="Action-exact floor loss kWh")
        ax[0].set_xlabel("Battery quantum q (kWh)")
        ax[0].set_ylabel("Energy (kWh)")
        ax[0].legend(fontsize=8)
        ax[0].set_title("Charge energy vs flooring loss")
        ax[1].bar(qs, labs, width=0.6)
        ax[1].set_xlabel("q (kWh)")
        ax[1].set_ylabel("MRLS labels generated")
        ax[1].set_title("Computational burden")
        fig.suptitle("Agadir→Casablanca eActros — q panel (canonical max_alts=4)")
        fig.tight_layout()
        fig.savefig(FIG / "fig03_q_charge_and_labels.png", dpi=150)
        plt.close(fig)

    # Fig 4 — robustness site outcomes
    if rob:
        labels = [r.get("scenario_id", "")[:28] for r in rob]
        served = [1 if str(r.get("ball_served")).lower() in ("true", "1") else 0 for r in rob]
        fig, ax = plt.subplots(figsize=(10, 4))
        ax.barh(range(len(labels)), served, color=["#2a9d8f" if s else "#e76f51" for s in served])
        ax.set_yticks(range(len(labels)))
        ax.set_yticklabels(labels, fontsize=7)
        ax.set_xlabel("Served under Ball (1=yes)")
        ax.set_title("Moroccan robustness matrix — service outcomes")
        fig.tight_layout()
        fig.savefig(FIG / "fig04_robustness_service.png", dpi=150)
        plt.close(fig)

    # Fig 5 — energy stack from trace
    if trace:
        r = next((x for x in trace if str(x.get("q")) == "5"), trace[0])
        parts = [
            ("Traction", float(r.get("E_traction_kwh") or 0)),
            ("Aux drive", float(r.get("E_aux_drive_kwh") or 0)),
            ("Refrig drive", float(r.get("E_refrig_drive_kwh") or 0)),
            ("Regen credit", float(r.get("E_regen_credit_kwh") or 0)),
        ]
        fig, ax = plt.subplots(figsize=(6, 3.5))
        ax.bar([p[0] for p in parts], [p[1] for p in parts])
        ax.set_ylabel("kWh")
        ax.set_title("Continuous energy components (q=5 COMPLETE trace)")
        fig.tight_layout()
        fig.savefig(FIG / "fig05_energy_components.png", dpi=150)
        plt.close(fig)

    # Fig 2 — SOC summary bars (full profile needs micro dump; publish min/arrival)
    if audit:
        fig, ax = plt.subplots(figsize=(6, 3.5))
        qs2 = [int(r["q"]) for r in audit]
        ax.plot(qs2, [float(r["auth_min_soc"]) for r in audit], "o-", label="Min SOC (micro)")
        ax.plot(qs2, [float(r["auth_arrival_soc"]) for r in audit], "s--", label="Arrival SOC")
        ax.set_xlabel("q (kWh)")
        ax.set_ylabel("SOC")
        ax.legend()
        ax.set_title("Microsegment min SOC vs arrival (authoritative replay)")
        fig.tight_layout()
        fig.savefig(FIG / "fig02_soc_min_arrival.png", dpi=150)
        plt.close(fig)

    # Fig 6 — B&B vs enum runtime
    cold = [r for r in bb if r.get("cache_mode") == "cold"]
    if cold:
        fig, ax = plt.subplots(figsize=(6, 3.5))
        names = [r.get("budget_name") for r in cold]
        ax.bar([i - 0.15 for i in range(len(names))], [float(r.get("enum_sec") or 0) for r in cold], width=0.3, label="Enum")
        ax.bar([i + 0.15 for i in range(len(names))], [float(r.get("bb_sec") or 0) for r in cold], width=0.3, label="B&B")
        ax.set_xticks(range(len(names)))
        ax.set_xticklabels(names)
        ax.set_ylabel("Seconds (cold cache)")
        ax.set_title("Synthetic 8-site shared-road — not Moroccan traffic")
        ax.legend()
        fig.tight_layout()
        fig.savefig(FIG / "fig06_bb_vs_enum.png", dpi=150)
        plt.close(fig)

    # Fig 1 placeholder note
    note = FIG / "fig01_corridor_map_README.txt"
    note.write_text(
        "Corridor map: use existing OSM/DEM artifacts or GIS export; "
        "do not imply chargers are installed. Candidates: Benguerir/Settat AC direction.\n",
        encoding="utf-8",
    )
    print(f"Wrote figures under {FIG}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
