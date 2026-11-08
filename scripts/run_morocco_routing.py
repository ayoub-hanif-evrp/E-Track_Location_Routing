#!/usr/bin/env python3
"""Task 03B — Moroccan corridor charging-stop experiments (S1–S5)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from morocco_etruck.optimization.continuous_replay import continuous_replay  # noqa: E402
from morocco_etruck.optimization.label_setting import SolverStatus, solve_mrls  # noqa: E402
from morocco_etruck.optimization.morocco_adapter import (  # noqa: E402
    build_mission_context,
    build_routing_instance,
    corridor_map_features,
    load_pilot_config,
    resolve_active_stations,
)
from morocco_etruck.optimization.replay import replay_solution  # noqa: E402
from morocco_etruck.road_network import load_graph_from_csv  # noqa: E402


def _charge_total(actions: list) -> int:
    return sum(int(a.get("delta_e_kwh", 0)) for a in actions if a.get("type") == "CHARGE")


def _charge_nodes(actions: list) -> str:
    return ";".join(
        f"{a['node']}:{a['delta_e_kwh']}" for a in actions if a.get("type") == "CHARGE"
    )


def _baseline_no_charge(inst, ctx) -> dict:
    """Fixed path, no charging comparator."""
    from morocco_etruck.optimization.resource_transitions import Label, apply_drive

    lab = Label(
        node=inst.origin,
        t=0,
        E_truck=inst.E_truck_init,
        E_trailer=inst.E_trailer_init,
        cost=0,
        pred_id=None,
        action={"type": "START"},
        label_id=0,
        can_charge=False,
    )
    nid = 1
    ok = True
    reason = None
    for arc in inst.arcs:
        r = apply_drive(inst, lab, arc, nid)
        if not r.ok or r.label is None:
            ok = False
            reason = r.reason
            break
        lab = r.label
        nid += 1
    return {
        "baseline_no_charge_ok": ok,
        "baseline_no_charge_reason": reason,
        "baseline_no_charge_E_truck": lab.E_truck if ok else None,
        "baseline_no_charge_cost": lab.cost if ok else None,
        "baseline_no_charge_t": lab.t if ok else None,
    }


def _heuristic_full_first(inst, ctx, active: set[str]) -> dict:
    """Charge full at first reachable active station, then drive."""
    from morocco_etruck.optimization.resource_transitions import (
        Label,
        apply_charge,
        apply_drive,
    )

    if not active:
        return {"heuristic_ok": False, "heuristic_reason": "no_active"}
    lab = Label(
        node=inst.origin,
        t=0,
        E_truck=inst.E_truck_init,
        E_trailer=inst.E_trailer_init,
        cost=0,
        pred_id=None,
        action={"type": "START"},
        label_id=0,
        can_charge=inst.origin in active,
    )
    nid = 1
    charged = False
    for arc in inst.arcs:
        if lab.node in active and lab.can_charge and not charged:
            head = inst.E_truck_cap - lab.E_truck
            q = inst.energy_quantum_kwh
            de = (head // q) * q
            if de > 0:
                r = apply_charge(inst, lab, de, nid)
                if r.ok and r.label is not None:
                    lab = r.label
                    nid += 1
                    charged = True
        r = apply_drive(inst, lab, arc, nid)
        if not r.ok or r.label is None:
            return {"heuristic_ok": False, "heuristic_reason": r.reason}
        lab = r.label
        nid += 1
    return {
        "heuristic_ok": True,
        "heuristic_reason": None,
        "heuristic_cost": lab.cost,
        "heuristic_E_truck": lab.E_truck,
        "heuristic_t": lab.t,
    }


def expand_jobs(cfg: dict) -> list[dict]:
    jobs = []
    directions = cfg.get("experiment_directions", ["casablanca_to_agadir"])
    gcms = cfg.get("experiment_gcms", ["light"])
    terrains = cfg.get("experiment_terrains", ["flat"])
    weather = cfg.get("experiment_weather", "cool")
    for scen in cfg["scenarios"]:
        for direction in directions:
            for gcm in gcms:
                for terrain in terrains:
                    variants = scen.get("variants") or [
                        {
                            "power_source": scen.get(
                                "power_source",
                                cfg["default_mission"]["power_source"],
                            ),
                            "refrigeration": scen.get(
                                "refrigeration",
                                cfg["default_mission"]["refrigeration"],
                            ),
                        }
                    ]
                    for var in variants:
                        refrig = var.get(
                            "refrigeration",
                            scen.get(
                                "refrigeration",
                                cfg["default_mission"]["refrigeration"],
                            ),
                        )
                        if refrig is True:
                            refrig = "on"
                        elif refrig is False:
                            refrig = "off"
                        else:
                            refrig = str(refrig)
                        jobs.append(
                            {
                                "scenario_id": scen["id"],
                                "family": scen["family"],
                                "intent": scen["intent"],
                                "active_policy": scen["active_policy"],
                                "preferred_station": scen.get("preferred_station"),
                                "price_mode": scen.get("price_mode", "uniform"),
                                "direction": direction,
                                "gcm": gcm,
                                "terrain": terrain,
                                "weather": weather,
                                "power_source": var.get(
                                    "power_source",
                                    cfg["default_mission"]["power_source"],
                                ),
                                "refrigeration": refrig,
                                "energy_quantum_kwh": int(cfg["energy_quantum_kwh"]),
                            }
                        )
    # Sensitivity: 1 kWh on S1 flat light Casa→Agadir only
    jobs.append(
        {
            "scenario_id": "S1",
            "family": "no_chargers",
            "intent": "Grid sensitivity 1 kWh",
            "active_policy": "none",
            "preferred_station": None,
            "price_mode": "uniform",
            "direction": "casablanca_to_agadir",
            "gcm": "light",
            "terrain": "flat",
            "weather": weather,
            "power_source": "A",
            "refrigeration": "off",
            "energy_quantum_kwh": int(cfg.get("energy_quantum_sensitivity_kwh", 1)),
        }
    )
    return jobs


def _write_corridor_png(geojson_path: Path, png_path: Path) -> None:
    """Simple map: OSM baseline path + hypothetical stops."""
    import matplotlib.pyplot as plt

    fc = json.loads(geojson_path.read_text(encoding="utf-8"))
    fig, ax = plt.subplots(figsize=(8, 10))
    for feat in fc["features"]:
        props = feat.get("properties") or {}
        geom = feat["geometry"]
        if geom["type"] == "LineString":
            xs = [c[0] for c in geom["coordinates"]]
            ys = [c[1] for c in geom["coordinates"]]
            ax.plot(xs, ys, color="#1f4e79", linewidth=1.5, label=props.get("legend", "baseline"))
        elif geom["type"] == "Point":
            ax.scatter(
                geom["coordinates"][0],
                geom["coordinates"][1],
                s=60,
                c="#c45c26",
                zorder=5,
                label=props.get("key", "stop"),
            )
            ax.annotate(
                props.get("key", ""),
                (geom["coordinates"][0], geom["coordinates"][1]),
                textcoords="offset points",
                xytext=(4, 4),
                fontsize=8,
            )
    handles, labels = ax.get_legend_handles_labels()
    uniq = dict(zip(labels, handles))
    ax.legend(uniq.values(), uniq.keys(), loc="best", fontsize=7)
    ax.set_xlabel("Longitude")
    ax.set_ylabel("Latitude")
    ax.set_title("A3 corridor + hypothetical chargers\n(OSM road vs assumed access)")
    ax.set_aspect("equal", adjustable="datalim")
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    png_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(png_path, dpi=140)
    plt.close(fig)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--config",
        type=Path,
        default=ROOT / "configs/optimization/morocco_pilot.yaml",
    )
    p.add_argument("--max-jobs", type=int, default=None)
    p.add_argument("--flat-only", action="store_true")
    p.add_argument("--heavy-only", action="store_true", help="Only heavy GCM jobs")
    args = p.parse_args()

    cfg = load_pilot_config(args.config)
    if args.flat_only:
        cfg["experiment_terrains"] = ["flat"]
    if args.heavy_only:
        cfg["experiment_gcms"] = ["heavy"]

    out_csv = ROOT / cfg["outputs"]["csv"]
    fig_dir = ROOT / cfg["outputs"]["figures_dir"]
    map_path = ROOT / cfg["outputs"]["map_geojson"]
    table_cache = ROOT / cfg["outputs"]["table_cache_dir"]
    fig_dir.mkdir(parents=True, exist_ok=True)

    print("Loading road graph…", flush=True)
    G = load_graph_from_csv(
        ROOT / cfg["nodes_csv"],
        ROOT / cfg["edges_csv"],
    )

    jobs = expand_jobs(cfg)
    if args.max_jobs is not None:
        jobs = jobs[: args.max_jobs]

    rows = []
    map_written = False
    for i, job in enumerate(jobs):
        print(
            f"[{i+1}/{len(jobs)}] {job['scenario_id']} {job['direction']} "
            f"gcm={job['gcm']} terrain={job['terrain']} q={job['energy_quantum_kwh']} "
            f"src={job['power_source']} refrig={job['refrigeration']}",
            flush=True,
        )
        try:
            ctx = build_mission_context(
                cfg,
                direction=job["direction"],
                gcm=job["gcm"],
                weather_id=job["weather"],
                terrain=job["terrain"],
                refrigeration=job["refrigeration"],
                power_source=job["power_source"],
                energy_quantum_kwh=job["energy_quantum_kwh"],
                root=ROOT,
                G=G,
            )
            if not map_written and job["direction"] == "casablanca_to_agadir" and job["terrain"] == "flat":
                map_path.write_text(
                    json.dumps(corridor_map_features(ctx), indent=2),
                    encoding="utf-8",
                )
                map_written = True

            active = resolve_active_stations(
                ctx,
                active_policy=job["active_policy"],
                preferred_station=job.get("preferred_station"),
            )
            inst = build_routing_instance(
                ctx,
                active_stations=active,
                price_mode=job["price_mode"],
                name=f"{job['scenario_id']}_{job['direction']}",
                table_cache_dir=table_cache,
            )
            # DEM invalid → report honestly
            dem_invalid = any(
                m.terrain_quality_status == "invalid" for m in ctx.macros
            ) and job["terrain"] == "dem"

            base = _baseline_no_charge(inst, ctx)
            heur = _heuristic_full_first(inst, ctx, active)

            if dem_invalid:
                # Still try solve; peak-power infeasibility may appear as empty tables
                pass

            result = solve_mrls(inst, use_dominance=True, max_seconds=120.0, max_expansions=500_000)
            disc_ok = False
            cont_ok = False
            cont_reason = None
            dE = dT = None
            min_e = None
            if result.status in (SolverStatus.OPTIMAL,) or (
                result.final_label is not None and result.status != SolverStatus.INFEASIBLE
            ):
                if result.actions:
                    rep = replay_solution(inst, result.actions, expected_cost=result.objective)
                    disc_ok = rep.ok
                    if result.status == SolverStatus.OPTIMAL or result.final_label:
                        cr = continuous_replay(
                            ctx,
                            inst,
                            result.actions,
                            discrete_cost=result.objective,
                            discrete_t=result.final_label.t if result.final_label else None,
                            discrete_E_truck=result.final_label.E_truck if result.final_label else None,
                        )
                        cont_ok = cr.ok
                        cont_reason = cr.reason
                        dE = cr.delta_energy_kwh
                        dT = cr.delta_time_s
                        min_e = cr.min_soc
                        if result.final_label:
                            min_e = min_e  # continuous min SOC

            # Feasible fraction of drive table from O
            first_arc = inst.arcs[0] if inst.arcs else None
            n_feas = 0
            n_tab = 0
            if first_arc and first_arc.drive_table:
                n_tab = len(first_arc.drive_table)
                n_feas = sum(1 for e in first_arc.drive_table.values() if e.feasible)

            rows.append(
                {
                    "scenario_id": job["scenario_id"],
                    "family": job["family"],
                    "intent": job["intent"],
                    "direction": job["direction"],
                    "gcm": job["gcm"],
                    "gcm_label": ctx.gcm_label,
                    "terrain": job["terrain"],
                    "weather": job["weather"],
                    "power_source": job["power_source"],
                    "refrigeration": job["refrigeration"],
                    "energy_quantum_kwh": job["energy_quantum_kwh"],
                    "time_step_min": inst.time_step_min,
                    "active_stations": ",".join(sorted(active)),
                    "price_mode": job["price_mode"],
                    "n_macros": len(ctx.macros),
                    "macro_km": round(sum(m.length_m for m in ctx.macros) / 1000.0, 3),
                    "terrain_quality": ";".join(m.terrain_quality_status for m in ctx.macros),
                    "dem_invalid": dem_invalid,
                    "status": result.status.value,
                    "objective_cents": result.objective,
                    "path": "->".join(result.path_nodes),
                    "charge_kwh": _charge_total(result.actions),
                    "charges": _charge_nodes(result.actions),
                    "final_t_steps": result.final_label.t if result.final_label else None,
                    "final_E_truck": result.final_label.E_truck if result.final_label else None,
                    "final_E_trailer": result.final_label.E_trailer if result.final_label else None,
                    "labels_generated": result.stats.get("labels_generated"),
                    "labels_expanded": result.stats.get("labels_expanded"),
                    "labels_dominated": result.stats.get("labels_dominated"),
                    "runtime_s": round(float(result.stats.get("runtime_s", 0.0)), 4),
                    "discrete_replay_ok": disc_ok,
                    "continuous_replay_ok": cont_ok,
                    "continuous_replay_reason": cont_reason,
                    "delta_energy_kwh": dE,
                    "delta_time_s": dT,
                    "min_continuous_soc": min_e,
                    "first_arc_table_feasible": n_feas,
                    "first_arc_table_size": n_tab,
                    **base,
                    **heur,
                    "station_snap_m": ";".join(
                        f"{s.key}:{s.snap_distance_m:.1f}" for s in ctx.stations
                    ),
                    "hypothetical_access": True,
                }
            )
        except Exception as exc:  # noqa: BLE001 — record and continue matrix
            rows.append(
                {
                    "scenario_id": job["scenario_id"],
                    "family": job["family"],
                    "direction": job["direction"],
                    "terrain": job["terrain"],
                    "status": "ERROR",
                    "error": str(exc),
                }
            )
            print(f"  ERROR: {exc}")

    df = pd.DataFrame(rows)
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out_csv, index=False)
    print(f"Wrote {out_csv} ({len(df)} rows)", flush=True)
    if map_written:
        print(f"Wrote {map_path}", flush=True)
        png = fig_dir / "morocco_routing_corridor_map.png"
        try:
            _write_corridor_png(map_path, png)
            print(f"Wrote {png}", flush=True)
        except Exception as exc:  # noqa: BLE001
            print(f"Map PNG skipped: {exc}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
