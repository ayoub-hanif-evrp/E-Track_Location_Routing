#!/usr/bin/env python
"""PASS 2A — Northbound Moroccan refrigerated agricultural proxy benchmark.

Case A: Agadir→Casablanca corridor research proxy (not observed shipment OD).
Commodity: firm-ripe tomatoes (UNECE 8–10 °C band).
Chargers: settat_ac, benguerir_ac only (no fabricated amskroud_ac).
Legal: gross_mass_within_limit_axle_unverified.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from morocco_etruck.energy.vehicle import (  # noqa: E402
    empty_combination_kg,
    gcm_from_payload,
    load_vehicle,
    validate_gcm,
)
from morocco_etruck.optimization.label_setting import SolverStatus  # noqa: E402
from morocco_etruck.optimization.multiroute_adapter import (  # noqa: E402
    clone_physics_instance_for_subset,
)
from morocco_etruck.optimization.multiroute_placement import (  # noqa: E402
    load_multiroute_placement_config,
)
from morocco_etruck.optimization.multiroute_placement_evaluation import (  # noqa: E402
    all_optimal_site_sets,
    evaluate_multiroute_mission,
    prepare_multiroute_placement_context,
    run_multiroute_branch_and_bound,
    run_multiroute_enumeration,
)
from morocco_etruck.optimization.multiroute_replay import (  # noqa: E402
    continuous_replay_multiroute,
)
from morocco_etruck.optimization.replay import replay_solution  # noqa: E402

VEHICLES = {
    "volvo_475": ROOT / "configs/vehicles/volvo_fh_electric_4x2_540kwh.yaml",
    "eactros_600": ROOT / "configs/vehicles/eactros_600.yaml",
    "volvo_460": ROOT / "configs/vehicles/volvo_fh_electric_4x2_540kwh_usable460.yaml",
}
CFG = ROOT / "configs/optimization/multiroute_placement_pass2a.yaml"
FRIDGE = ROOT / "configs/energy/pass2_tomato_firm_ripe.yaml"
ROAD_CENTS = 100.0
MOROCCAN_PTRA_ARTIC_40T = 40000.0

CELLS = [
    {"id": "A80", "demand": "A_nb_tomato_p5300_soc08", "soc": 0.8, "payload": 5300.0},
    {"id": "A50", "demand": "A_nb_tomato_p5300_soc05", "soc": 0.5, "payload": 5300.0},
    {"id": "AH80", "demand": "A_nb_tomato_p15000_soc08", "soc": 0.8, "payload": 15000.0},
]


def _file_sha(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()[:16]


def _legal_screen(vehicle, payload: float) -> dict[str, Any]:
    empty = empty_combination_kg(vehicle)
    gcm = gcm_from_payload(payload, vehicle)
    validate_gcm(gcm, vehicle)
    return {
        "empty_combination_kg": empty,
        "gcm_realized_kg": gcm,
        "manufacturer_gcw_kg": float(vehicle.gcm_limit_kg),
        "moroccan_ptra_artic_40t_kg": MOROCCAN_PTRA_ARTIC_40T,
        "gross_within_moroccan_40t": gcm <= MOROCCAN_PTRA_ARTIC_40T + 1e-6,
        "gross_within_manufacturer_gcw": gcm <= float(vehicle.gcm_limit_kg) + 1e-6,
        "legal_mass_status": "gross_mass_within_limit_axle_unverified",
        "axle_compliance": "unverified",
    }


def _path_set_sensitivity(cfg, root: Path, demand: str, vpath: Path) -> list[dict]:
    """Bounded max_alts=2 vs max_alts=4 comparison on A80 baseline only."""
    rows = []
    for max_alts in (2, 4):
        t0 = time.perf_counter()
        try:
            ctx = prepare_multiroute_placement_context(
                cfg,
                root=root,
                demand_name=demand,
                energy_quantum_kwh=10,
                objective_mode="enroute_incremental_cost",
                vehicle_yaml=vpath,
                road_cost_per_km=ROAD_CENTS,
                fridge_yaml=FRIDGE,
                charger_power_kw=350.0,
                max_alternatives_for_union=max_alts,
            )
        except Exception as exc:  # noqa: BLE001
            rows.append(
                {
                    "experiment": "path_set_sensitivity",
                    "max_alts": max_alts,
                    "status": "BUILD_ERROR",
                    "error": str(exc),
                }
            )
            continue
        prep = next(iter(ctx["prepared"].values()))
        dem_ok = bool(prep.ctx.dem_complete)
        r = evaluate_multiroute_mission(
            prep,
            installed=set(),
            sites=cfg.sites,
            max_seconds=60.0,
            max_expansions=100_000,
        )
        note = "ok"
        if not dem_ok:
            note = "dem_incomplete_for_this_path_union"
        elif r.status == "INFEASIBLE":
            note = "infeasible_under_assumed_power_and_path_union"
        rows.append(
            {
                "experiment": "path_set_sensitivity",
                "max_alts": max_alts,
                "dem_complete": dem_ok,
                "n_arcs": len(prep.template.arcs),
                "mrls_status": r.status,
                "served": bool(r.served),
                "uncertified": bool(r.uncertified),
                "objective_cents": r.objective_cents,
                "sec": time.perf_counter() - t0,
                "note": note,
            }
        )
    return rows


def run_routing_detail(
    *,
    cell: dict,
    vkey: str,
    q: int = 10,
) -> list[dict]:
    cfg = load_multiroute_placement_config(CFG, root=ROOT)
    vpath = VEHICLES[vkey]
    vehicle = load_vehicle(vpath)
    legal = _legal_screen(vehicle, cell["payload"])
    rows: list[dict] = []
    print(
        f"\n=== route {cell['id']} veh={vkey} q={q} payload={cell['payload']} ===",
        flush=True,
    )
    t0 = time.perf_counter()
    context = prepare_multiroute_placement_context(
        cfg,
        root=ROOT,
        demand_name=cell["demand"],
        energy_quantum_kwh=q,
        objective_mode="enroute_incremental_cost",
        vehicle_yaml=vpath,
        road_cost_per_km=ROAD_CENTS,
        fridge_yaml=FRIDGE,
        charger_power_kw=350.0,
        max_alternatives_for_union=2,
    )
    prep = next(iter(context["prepared"].values()))
    if not prep.ctx.dem_complete:
        return [
            {
                "cell_id": cell["id"],
                "vehicle_key": vkey,
                "status": "DEM_INCOMPLETE",
                "blocker": "northbound DEM incomplete — stop without fabricating",
                **legal,
            }
        ]
    sites = cfg.sites
    all_ids = {s.id for s in sites}
    # Verify no CA (southbound) keys accidentally active
    for s in sites:
        assert s.station_key.endswith("_ac"), s.station_key
        assert "amskroud" not in s.station_key

    for install_name, installed in (
        ("none", set()),
        ("settat_only", {"y_settat_ac"}),
        ("benguerir_only", {"y_benguerir_ac"}),
        ("both", all_ids),
    ):
        r = evaluate_multiroute_mission(
            prep,
            installed=installed,
            sites=sites,
            max_seconds=90.0,
            max_expansions=120_000,
        )
        disc_ok = cont_ok = None
        cont_reason = None
        if r.served and r.path:
            active = {
                s.station_key for s in sites if s.id in installed
            }
            inst = clone_physics_instance_for_subset(
                prep.template, active_stations=active
            )
            # Rebuild a minimal solve path for replay via evaluate fields
            disc_ok = bool(r.discrete_replay_ok)
            cont_ok = bool(r.continuous_replay_ok)
            cont_reason = r.reason
        rows.append(
            {
                "cell_id": cell["id"],
                "demand_name": cell["demand"],
                "vehicle_key": vkey,
                "usable_kwh": float(vehicle.usable_kwh),
                "soc_init": cell["soc"],
                "cargo_payload_kg": cell["payload"],
                "commodity": "firm_ripe_fresh_tomatoes",
                "setpoint_c": 9.0,
                "setpoint_source": "UNECE_firm_ripe_tomato_8_10C_midband",
                "od_id": "agadir_casa",
                "od_evidence_class": "corridor_research_proxy",
                "q_kwh": q,
                "install_set": install_name,
                "installed_sites": ",".join(sorted(installed)),
                "station_keys": ",".join(
                    sorted(s.station_key for s in sites if s.id in installed)
                ),
                "dem_complete": True,
                "terrain_mode": "dem",
                "mrls_status": r.status,
                "served": bool(r.served),
                "uncertified": bool(r.uncertified),
                "objective_cents": r.objective_cents,
                "charge_kwh": r.charge_kwh,
                "charges": r.charges,
                "path": r.path,
                "discrete_replay_ok": disc_ok if disc_ok is not None else r.discrete_replay_ok,
                "continuous_replay_ok": cont_ok if cont_ok is not None else r.continuous_replay_ok,
                "reason": r.reason or cont_reason,
                "n_arcs": len(prep.template.arcs),
                "charger_power_label": "hypothetical_350kW_not_verified_operating",
                "missing_amskroud_ac": True,
                "prep_sec": time.perf_counter() - t0,
                **legal,
            }
        )
        print(
            f"  {install_name}: {r.status} served={r.served} "
            f"replay_d={r.discrete_replay_ok} c={r.continuous_replay_ok}",
            flush=True,
        )
    return rows


def run_placement(cell: dict, vkey: str, q: int = 10) -> list[dict]:
    cfg = load_multiroute_placement_config(CFG, root=ROOT)
    vpath = VEHICLES[vkey]
    vehicle = load_vehicle(vpath)
    legal = _legal_screen(vehicle, cell["payload"])
    print(f"\n=== place {cell['id']} veh={vkey} ===", flush=True)
    t0 = time.perf_counter()
    context = prepare_multiroute_placement_context(
        cfg,
        root=ROOT,
        demand_name=cell["demand"],
        energy_quantum_kwh=q,
        objective_mode="enroute_incremental_cost",
        vehicle_yaml=vpath,
        road_cost_per_km=ROAD_CENTS,
        fridge_yaml=FRIDGE,
        charger_power_kw=350.0,
        max_alternatives_for_union=2,
    )
    prep = next(iter(context["prepared"].values()))
    if not prep.ctx.dem_complete:
        return [
            {
                "cell_id": cell["id"],
                "vehicle_key": vkey,
                "status": "DEM_INCOMPLETE",
                **legal,
            }
        ]
    rows = []
    for bud in cfg.budgets:
        bname = bud["name"]
        enum_rows, e_inc, _ = run_multiroute_enumeration(
            cfg,
            root=ROOT,
            demand_name=cell["demand"],
            capex_name="equal",
            budget_name=bname,
            context=context,
        )
        bb, _ = run_multiroute_branch_and_bound(
            cfg,
            root=ROOT,
            demand_name=cell["demand"],
            capex_name="equal",
            budget_name=bname,
            context=context,
        )
        b_inc = bb.incumbent
        agree = False
        if e_inc is not None and b_inc is not None:
            agree = (
                abs(e_inc.coverage_serviceable - b_inc.coverage_serviceable) <= 1e-9
                and abs(e_inc.secondary_cost - b_inc.secondary_cost) <= 1e-6
            )
        elif e_inc is None and b_inc is None:
            agree = True
        opt_sets = all_optimal_site_sets(enum_rows)
        rows.append(
            {
                "cell_id": cell["id"],
                "demand_name": cell["demand"],
                "vehicle_key": vkey,
                "usable_kwh": float(vehicle.usable_kwh),
                "soc_init": cell["soc"],
                "cargo_payload_kg": cell["payload"],
                "commodity": "firm_ripe_fresh_tomatoes",
                "od_id": "agadir_casa",
                "od_evidence_class": "corridor_research_proxy",
                "q_kwh": q,
                "budget_name": bname,
                "coverage_serviceable": (
                    None if b_inc is None else b_inc.coverage_serviceable
                ),
                "weight_total": 1.0,
                "best_sites_bb": (
                    "" if b_inc is None else ",".join(sorted(b_inc.site_ids))
                ),
                "best_sites_enum": (
                    "" if e_inc is None else ",".join(sorted(e_inc.site_ids))
                ),
                "secondary_cost": None if b_inc is None else b_inc.secondary_cost,
                "objective_agreement": agree,
                "optimality_status": bb.optimality_status.value,
                "all_optimal_site_sets": "|".join(opt_sets),
                "n_optimal_site_sets": len(opt_sets),
                "charger_candidates": "y_settat_ac,y_benguerir_ac",
                "missing_amskroud_ac": True,
                "continuous_cause_hint": "peak_motor_under_assumed_400kW_on_dem_macros",
                "prep_sec": time.perf_counter() - t0,
                **legal,
            }
        )
        print(
            f"  {bname}: cov={rows[-1]['coverage_serviceable']} "
            f"sites={rows[-1]['best_sites_bb']} agree={agree}",
            flush=True,
        )
    return rows


def write_pass2a_reports(
    route_df: pd.DataFrame, place_df: pd.DataFrame, sens_df: pd.DataFrame
) -> None:
    hashes = {
        "placement_yaml": _file_sha(CFG),
        "fridge_yaml": _file_sha(FRIDGE),
        "dem_meta": _file_sha(
            ROOT / "data/processed/multiroute/elevation/dem_sampling_meta.json"
        ),
    }
    legal_md = f"""# PASS 2A — Refrigerated cargo and legal screen

## Commodity

| Field | Value |
| --- | --- |
| Commodity | Firm-ripe fresh tomatoes |
| Setpoint | 9 °C (UNECE firm-ripe band ≈ 8–10 °C mid-point) |
| Source | UNECE ECE_TRADE_470 good-practice guidance |
| Status | Category reference — **not** measured Moroccan trailer setpoints |
| Precooled | Assumed true |
| UA / COP / infiltration | Assumed research parameters (unchanged magnitudes) |
| Config A tractor→TRU | **Unverified** compatibility |

## Legal mass screen (Decree 2-10-421 Art. 3)

Assumed 4×2 tractor + three-axle refrigerated semi → articulated **40 t** PTRA screen.
Axle-group limits (Art. 4) **not** computed — geometry unavailable.

| Payload | Empty (assumed) | GCM | ≤40 t Moroccan | ≤ manufacturer GCW | Status |
| --- | ---: | ---: | --- | --- | --- |
"""
    for payload in (5300.0, 15000.0):
        for vkey, vpath in VEHICLES.items():
            if vkey == "volvo_460" and payload != 5300.0:
                continue
            veh = load_vehicle(vpath)
            L = _legal_screen(veh, payload)
            legal_md += (
                f"| {payload:.0f} / {vkey} | {L['empty_combination_kg']:.0f} | "
                f"{L['gcm_realized_kg']:.0f} | {L['gross_within_moroccan_40t']} | "
                f"{L['gross_within_manufacturer_gcw']} | "
                f"`{L['legal_mass_status']}` |\n"
            )
    legal_md += (
        "\n**Do not use `legally_certified`.** OSM topology ≠ HGV legal access certificate.\n"
        f"\nInput hashes: `{json.dumps(hashes)}`\n"
    )
    (ROOT / "reports/pass2_refrigerated_cargo_and_legal_screen.md").write_text(
        legal_md, encoding="utf-8"
    )

    lines = [
        "# PASS 2A — Northbound Moroccan benchmark",
        "",
        "## Problem definition (honest)",
        "",
        "**Primary Case A:** prospective battery-electric refrigerated agricultural freight "
        "from Agadir/Souss-Massa toward Casablanca / northern export logistics.",
        "",
        "- Computational OD: `agadir_casa` labeled **`corridor_research_proxy`.",
        "- Tanger Med evidence supports Souss-Massa agricultural export importance; "
        "it does **not** prove this OD is an observed refrigerated shipment terminating at Casablanca.",
        "- Historical southbound Task 07/08 retained as secondary Case B (not mixed here).",
        "- No double-counted Agadir→Marrakech leg.",
        "",
        "## Network / DEM / chargers",
        "",
        "- DEM: Copernicus GLO-30 sampled **independently** for `agadir_casa` macros "
        "(not reversed southbound arrays). Merged into `dem_sampling_meta.json`.",
        "- Candidates: `settat_ac`, `benguerir_ac` only — hypothetical future truck sites.",
        "- `amskroud_ac`: **unavailable / unresolved** — not fabricated.",
        "- Path-union default `max_alts=2`; bounded sensitivity vs 4 alternatives below.",
        "",
        f"Input hashes: `{json.dumps(hashes)}`",
        "",
        "## Path-set sensitivity (Volvo 475, A80, q=10, no chargers)",
        "",
    ]
    if not sens_df.empty:
        lines.append("| max_alts | dem | n_arcs | MRLS | served | note |")
        lines.append("| ---: | --- | ---: | --- | --- | --- |")
        for _, r in sens_df.iterrows():
            lines.append(
                f"| {r.get('max_alts')} | {r.get('dem_complete')} | {r.get('n_arcs')} | "
                f"{r.get('mrls_status')} | {r.get('served')} | {r.get('note')} |"
            )
    lines.extend(["", "## Routing summary (q=10)", ""])
    if not route_df.empty:
        lines.append(
            "| Cell | Vehicle | Install | Status | Served | Disc replay | Cont replay |"
        )
        lines.append("| --- | --- | --- | --- | --- | --- | --- |")
        for _, r in route_df.iterrows():
            if r.get("status") == "DEM_INCOMPLETE":
                lines.append(
                    f"| {r.cell_id} | {r.vehicle_key} | — | DEM_INCOMPLETE | — | — | — |"
                )
                continue
            lines.append(
                f"| {r.cell_id} | {r.vehicle_key} | {r.install_set} | {r.mrls_status} | "
                f"{r.served} | {r.discrete_replay_ok} | {r.continuous_replay_ok} |"
            )
    lines.extend(["", "## Placement summary (enum ↔ B&B)", ""])
    if not place_df.empty:
        lines.append("| Cell | Vehicle | Budget | Coverage | Sites | Agree | Status |")
        lines.append("| --- | --- | --- | ---: | --- | --- | --- |")
        for _, r in place_df.iterrows():
            lines.append(
                f"| {r.cell_id} | {r.vehicle_key} | {r.budget_name} | "
                f"{r.coverage_serviceable} | {r.best_sites_bb} | "
                f"{r.objective_agreement} | {r.optimality_status} |"
            )
    lines.extend(
        [
            "",
            "## Reproduction",
            "",
            "```bash",
            "python scripts/fetch_multiroute_dem.py --od-ids agadir_casa --merge-meta --max-alts 2",
            "python scripts/run_pass2a_northbound_benchmark.py",
            "```",
            "",
            "CSVs: `results/pass2_northbound_routing.csv`, `results/pass2_northbound_placement.csv`.",
            "",
        ]
    )
    (ROOT / "reports/pass2_northbound_moroccan_benchmark.md").write_text(
        "\n".join(lines), encoding="utf-8"
    )
    print("Wrote PASS 2A reports", flush=True)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--stages",
        default="all",
        help="routing,placement,sensitivity,all",
    )
    args = p.parse_args()
    stages = {s.strip() for s in args.stages.split(",") if s.strip()}
    if "all" in stages:
        stages = {"routing", "placement", "sensitivity"}

    route_rows: list[dict] = []
    place_rows: list[dict] = []
    sens_rows: list[dict] = []

    if "sensitivity" in stages:
        cfg = load_multiroute_placement_config(CFG, root=ROOT)
        sens_rows = _path_set_sensitivity(
            cfg, ROOT, "A_nb_tomato_p5300_soc08", VEHICLES["volvo_475"]
        )

    if "routing" in stages:
        # Baseline A80 all vehicles; A50 + AH80 Volvo primary + eActros comparator
        for cell in CELLS:
            vehs = ("volvo_475", "eactros_600")
            if cell["id"] == "A80":
                vehs = ("volvo_475", "eactros_600", "volvo_460")
            for vkey in vehs:
                route_rows.extend(run_routing_detail(cell=cell, vkey=vkey, q=10))

    if "placement" in stages:
        for cell in CELLS:
            vehs = ("volvo_475", "eactros_600")
            if cell["id"] == "A80":
                vehs = ("volvo_475", "eactros_600", "volvo_460")
            for vkey in vehs:
                place_rows.extend(run_placement(cell=cell, vkey=vkey, q=10))

    if route_rows:
        out = ROOT / "results/pass2_northbound_routing.csv"
        pd.DataFrame(route_rows).to_csv(out, index=False)
        print(f"Wrote {out} ({len(route_rows)} rows)", flush=True)
    if place_rows:
        out = ROOT / "results/pass2_northbound_placement.csv"
        pd.DataFrame(place_rows).to_csv(out, index=False)
        print(f"Wrote {out} ({len(place_rows)} rows)", flush=True)
    if sens_rows:
        out = ROOT / "results/pass2_path_set_sensitivity.csv"
        pd.DataFrame(sens_rows).to_csv(out, index=False)
        print(f"Wrote {out}", flush=True)

    write_pass2a_reports(
        pd.DataFrame(route_rows),
        pd.DataFrame(place_rows),
        pd.DataFrame(sens_rows),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
