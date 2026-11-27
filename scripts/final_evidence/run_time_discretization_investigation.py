#!/usr/bin/env python3
"""P0 — Temporal discretization investigation (HOS continuous-driving ceil inflation).

Family A: global time-grid refinement (ts∈{5,2,1}) with wall-clock deadline scaling.
Family B: offline ceil/floor/round screen on frozen energy-only physical durations.
"""
from __future__ import annotations

import dataclasses
import json
import math
import subprocess
import sys
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import morocco_etruck.optimization.multiroute_placement_evaluation as mpe  # noqa: E402
import run_stage_c_hos_national as stage_c  # noqa: E402
from morocco_etruck.energy.vehicle import load_vehicle  # noqa: E402
from morocco_etruck.optimization.label_setting import solve_mrls  # noqa: E402
from morocco_etruck.optimization.multiroute_adapter import (  # noqa: E402
    clone_physics_instance_for_subset,
    load_multiroute_pilot_config,
)
from morocco_etruck.optimization.multiroute_placement import (  # noqa: E402
    load_multiroute_placement_config,
)
from morocco_etruck.optimization.multiroute_replay import (  # noqa: E402
    continuous_replay_multiroute,
)
from morocco_etruck.optimization.resource_transitions import _hos_limits  # noqa: E402
from run_final_operational_correction import evaluate_mission_operational  # noqa: E402
from run_high_impact_realism_sprint import VEHICLES  # noqa: E402
from run_paper_scientific_results_campaign import _temp_demand_cfg  # noqa: E402

OUT = ROOT / "results/final_evidence/experiments/time_discretization"
TAB = ROOT / "results/final_evidence/tables/results"
FIG = ROOT / "results/final_evidence/figures/results"
SRC = FIG / "source_data"

OD = "marrakech_agadir"
SOC = 0.8
PAYLOAD = 5300.0
INSTALLED = {"y_benguerir_ca", "y_larache_rt"}
BASE_TS = 5
BASE_DEADLINE = 240


def _git_sha() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT).decode().strip()
    except Exception:  # noqa: BLE001
        return "unknown"


def _ceil_steps(dt_s: float, ts: int) -> int:
    return max(1, int(math.ceil(dt_s / (ts * 60.0))))


def _floor_steps(dt_s: float, ts: int) -> int:
    return max(1, int(math.floor(dt_s / (ts * 60.0) + 1e-12)))


def _round_steps(dt_s: float, ts: int) -> int:
    return max(1, int(round(dt_s / (ts * 60.0))))


def _patch_pilot_time_step(ts: int):
    orig = mpe.load_multiroute_pilot_config
    deadline = int(round(BASE_DEADLINE * BASE_TS / float(ts)))

    def wrapped(path, *, root=None):
        pilot = orig(path, root=root if root is not None else ROOT)
        return dataclasses.replace(
            pilot,
            time_step_min=int(ts),
            deadline_steps=int(deadline),
        )

    mpe.load_multiroute_pilot_config = wrapped
    return orig, deadline


def _prepare(vehicle_key: str, ts: int):
    orig_loader, deadline = _patch_pilot_time_step(ts)
    try:
        cfg_path = _temp_demand_cfg(OD, float(PAYLOAD), float(SOC))
        cfg = load_multiroute_placement_config(cfg_path, root=ROOT)
        vpath = VEHICLES[vehicle_key]
        vehicle = load_vehicle(vpath)
        context = mpe.prepare_multiroute_placement_context(
            cfg,
            root=ROOT,
            demand_name="frontier_cell",
            energy_quantum_kwh=2,
            objective_mode="enroute_incremental_cost",
            vehicle_yaml=vpath,
            road_cost_per_km=stage_c.ROAD_CENTS,
            fridge_yaml=stage_c.FRIDGE,
            charger_power_kw=350.0,
            max_alternatives_for_union=2,
            probe_serviceability=False,
            deadline_steps=deadline,
        )
        pilot = context["pilot"]
        path_rows = pd.read_csv(pilot.path_alternatives_csv).to_dict(orient="records")
        masks = stage_c._mission_masks(context, path_rows)
        return cfg, vehicle, context, masks, deadline
    finally:
        mpe.load_multiroute_pilot_config = orig_loader


def _site_keys(cfg, installed: set[str]) -> set[str]:
    key_of = {s.id: s.station_key for s in cfg.sites}
    return {key_of[i] for i in installed if i in key_of}


def _energy_only_solve(prep, cfg, installed, mask, ts_label: int):
    present = _site_keys(cfg, installed) & set(prep.template.stations)
    inst = clone_physics_instance_for_subset(
        prep.template,
        active_stations=present,
        allowed_arc_ids=mask,
        name=f"energy|ts{ts_label}|{prep.mission.id}",
    )
    inst.hos_in_search = False
    res = solve_mrls(inst, max_seconds=600.0, max_expansions=2_000_000)
    crep, extras = continuous_replay_multiroute(
        prep.ctx,
        inst,
        res.actions or [],
        discrete_cost=res.objective,
        discrete_t=res.final_label.t if res.final_label else None,
        discrete_E_truck=res.final_label.E_truck if res.final_label else None,
        emit_trace=True,
    )
    return res, inst, crep, extras


def _join_rows(res, extras, ts: int, max_drive: int) -> list[dict]:
    phys_by_arc: dict[str, dict] = {}
    if extras is not None:
        for a in extras.action_trace or []:
            if (a.get("action_type") or a.get("type")) == "DRIVE" and a.get("arc_id"):
                phys_by_arc[str(a["arc_id"])] = a
    rows = []
    cum_p = cum_d = 0.0
    idx = 0
    for a in res.actions or []:
        if str(a.get("type") or "") != "DRIVE":
            continue
        aid = str(a.get("arc_id") or "")
        dt_steps = int(a.get("dt_steps") or 0)
        p = phys_by_arc.get(aid, {})
        dt_s = float(p.get("dt_s") or 0.0)
        dt_p = dt_s / 60.0
        dt_d = dt_steps * ts
        cum_p += dt_p
        cum_d += dt_d
        idx += 1
        rows.append(
            {
                "family": "A_global_time_grid",
                "vehicle_key": "volvo_475",
                "od_id": OD,
                "infra": "I2_benguerir_larache",
                "time_step_min": ts,
                "drive_index": idx,
                "arc_id": aid,
                "u": p.get("u"),
                "v": p.get("v"),
                "length_m": p.get("length_m"),
                "dt_s_phys": dt_s,
                "dt_phys_min": dt_p,
                "dt_steps_solver": dt_steps,
                "dt_disc_min": dt_d,
                "ceil_slack_min": dt_d - dt_p,
                "cum_phys_min": cum_p,
                "cum_disc_min": cum_d,
                "crosses_270_phys": cum_p > 270 + 1e-9,
                "crosses_270_disc": cum_d > 270 + 1e-9,
                "hos_max_continuous_steps": max_drive,
                "hos_max_continuous_min": max_drive * ts,
            }
        )
    return rows


def per_arc_and_sweep() -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    orig_speed = stage_c._patch_realistic_speed_policy()
    per_arc_all: list[dict] = []
    sweep: list[dict] = []
    summary: dict[str, Any] = {"git_sha": _git_sha(), "od_id": OD, "soc": SOC}
    try:
        for ts in (5, 2, 1):
            print(f"[P0] prepare volvo ts={ts}", flush=True)
            cfg, vehicle, context, masks, deadline = _prepare("volvo_475", ts)
            mid = context["missions"][0].id
            prep = context["prepared"][mid]
            mask = frozenset(masks[mid]["all"])
            assert int(prep.template.time_step_min) == ts, (
                prep.template.time_step_min,
                ts,
            )
            print(f"[P0] energy-only solve ts={ts} deadline_steps={deadline}", flush=True)
            res, inst, crep, extras = _energy_only_solve(prep, cfg, INSTALLED, mask, ts)
            max_drive, _min_break, _max_daily = _hos_limits(inst)
            rows = _join_rows(res, extras, ts, max_drive)
            per_arc_all.extend(rows)
            cum_p = float(rows[-1]["cum_phys_min"]) if rows else 0.0
            cum_d = float(rows[-1]["cum_disc_min"]) if rows else 0.0
            phys_durs = [float(r["dt_s_phys"]) for r in rows]
            pol = {}
            for name, fn in (
                ("ceil", _ceil_steps),
                ("floor", _floor_steps),
                ("round", _round_steps),
            ):
                steps = [fn(dt, ts) for dt in phys_durs]
                disc_min = sum(s * ts for s in steps)
                pol[name] = {
                    "sum_steps": int(sum(steps)),
                    "sum_disc_min": disc_min,
                    "exceeds_270": disc_min > 270 + 1e-9,
                    "exceeds_hos_max_steps": int(sum(steps)) > max_drive,
                }

            print(f"[P0] ops solve ts={ts}", flush=True)
            mr = evaluate_mission_operational(
                prep=prep,
                cfg=cfg,
                installed=set(INSTALLED),
                mask=mask,
                vehicle=vehicle,
                fridge_path=stage_c.FRIDGE,
                max_seconds=600.0,
                max_expansions=2_000_000,
                include_energy_only=True,
                capture_energy_trace=True,
            )
            sweep.append(
                {
                    "family": "A_global_time_grid",
                    "vehicle_key": "volvo_475",
                    "od_id": OD,
                    "soc_frac": SOC,
                    "infra_config_id": "I2_benguerir_larache",
                    "time_step_min": ts,
                    "deadline_steps": deadline,
                    "deadline_wall_h": deadline * ts / 60.0,
                    "energy_status": res.status.value,
                    "ops_status": mr.get("status"),
                    "operationally_served": bool(mr.get("operationally_served")),
                    "energy_drive_min": mr.get("energy_drive_min"),
                    "drive_min_phys": mr.get("drive_min_phys"),
                    "sum_dt_phys_min": cum_p,
                    "sum_dt_disc_min": cum_d,
                    "n_drive_arcs": len(rows),
                    "hos_max_continuous_steps": max_drive,
                    "hos_max_continuous_min": max_drive * ts,
                    "phys_under_270_disc_over": (cum_p <= 270 + 1e-9) and (cum_d > 270 + 1e-9),
                    "family_b_ceil_exceeds_270": pol["ceil"]["exceeds_270"],
                    "family_b_floor_exceeds_270": pol["floor"]["exceeds_270"],
                    "family_b_round_exceeds_270": pol["round"]["exceeds_270"],
                    "family_b_ceil_sum_disc_min": pol["ceil"]["sum_disc_min"],
                    "family_b_floor_sum_disc_min": pol["floor"]["sum_disc_min"],
                    "family_b_round_sum_disc_min": pol["round"]["sum_disc_min"],
                    "crep_ok": bool(getattr(crep, "ok", False)),
                    "solve_sec": mr.get("solve_sec"),
                    "hos_ok": mr.get("hos_ok"),
                    "daily_driving_ok": mr.get("daily_driving_ok"),
                }
            )
            print(
                f"  energy={res.status.value} ops={mr.get('status')} "
                f"served={mr.get('operationally_served')} "
                f"phys={cum_p:.2f} disc={cum_d:.2f} max_hos={max_drive * ts}",
                flush=True,
            )
            if ts == 5:
                summary["ts5"] = {
                    "sum_phys_min": cum_p,
                    "sum_disc_min": cum_d,
                    "inflation_min": cum_d - cum_p,
                    "n_drive_arcs": len(rows),
                    "phys_under_270_disc_over": (cum_p <= 270 + 1e-9) and (cum_d > 270 + 1e-9),
                    "family_b": pol,
                }
    finally:
        mpe.load_multiroute_pilot_config = orig_speed

    return pd.DataFrame(per_arc_all), pd.DataFrame(sweep), summary


def screen_primary_traces(ts: int = 5) -> pd.DataFrame:
    prim = pd.read_csv(
        ROOT / "results/final_evidence/experiments/primary_comparison/primary_missions.csv"
    )
    rows = []
    for _, r in prim.iterrows():
        status = str(r.status)
        energy = str(r.get("energy_status") or "")
        tr = r.get("action_trace_json")
        acts = []
        if isinstance(tr, str) and tr.strip() and status == "OPTIMAL":
            acts = json.loads(tr)
        phys = [
            float(a.get("dt_s") or 0.0)
            for a in acts
            if (a.get("action_type") or a.get("type")) == "DRIVE"
        ]
        if not phys and not (energy == "OPTIMAL" and status != "OPTIMAL"):
            continue
        sum_phys = sum(phys) / 60.0 if phys else None
        if phys:
            ceil_steps = [_ceil_steps(dt, ts) for dt in phys]
            sum_disc = sum(s * ts for s in ceil_steps)
        else:
            sum_disc = None
        rows.append(
            {
                "vehicle_key": r.vehicle_key,
                "soc_scenario": r.soc_scenario,
                "infra_config_id": r.infra_config_id,
                "od_id": r.od_id,
                "status": status,
                "energy_status": energy,
                "operationally_served": bool(r.operationally_served),
                "n_drive_arcs": len(phys),
                "sum_phys_drive_min": sum_phys,
                "sum_ceil_disc_min": sum_disc,
                "ceil_inflation_min": (
                    sum_disc - sum_phys
                    if sum_phys is not None and sum_disc is not None
                    else None
                ),
                "phys_under_270": (sum_phys is not None and sum_phys <= 270 + 1e-9),
                "disc_over_270": (sum_disc is not None and sum_disc > 270 + 1e-9),
                "potential_ceil_exclusion": bool(
                    sum_phys is not None
                    and sum_disc is not None
                    and sum_phys <= 270 + 1e-9
                    and sum_disc > 270 + 1e-9
                ),
                "near_threshold_phys_250_270": bool(
                    sum_phys is not None and 250 <= sum_phys <= 270 + 1e-9
                ),
                "energy_ok_ops_inf": bool(energy == "OPTIMAL" and status != "OPTIMAL"),
                "drive_min_phys_col": r.get("drive_min_phys"),
                "wait_min_phys": r.get("wait_min_phys"),
                "charge_min_phys": r.get("charge_min_phys"),
            }
        )
    return pd.DataFrame(rows)


def casa_tangier_wait_excerpt() -> pd.DataFrame:
    prim = pd.read_csv(
        ROOT / "results/final_evidence/experiments/primary_comparison/primary_missions.csv"
    )
    rows = []
    for _, r in prim.iterrows():
        if r.od_id not in {"casa_tangier", "tangier_casa"}:
            continue
        if r.vehicle_key != "eactros_600":
            continue
        tr = r.get("action_trace_json")
        if not isinstance(tr, str) or not tr.strip():
            rows.append(
                {
                    "od_id": r.od_id,
                    "soc_scenario": r.soc_scenario,
                    "infra_config_id": r.infra_config_id,
                    "status": r.status,
                    "note": "no_trace",
                }
            )
            continue
        acts = json.loads(tr)
        t = 0.0
        drive_since = 0.0
        block_stat = 0.0
        for i, a in enumerate(acts):
            typ = a.get("action_type") or a.get("type")
            dt = float(a.get("dt_s") or 0.0)
            node = a.get("site") or a.get("node") or a.get("v") or a.get("u")
            if typ == "DRIVE":
                drive_since += dt / 60.0
                block_stat = 0.0
            elif typ in {"CHARGE", "WAIT"}:
                block_stat += dt / 60.0
            rows.append(
                {
                    "od_id": r.od_id,
                    "soc_scenario": r.soc_scenario,
                    "infra_config_id": r.infra_config_id,
                    "status": r.status,
                    "action_index": i,
                    "action_type": typ,
                    "node": node,
                    "dt_s": dt,
                    "dt_min": dt / 60.0,
                    "t_end_min": (t + dt) / 60.0,
                    "drive_since_break_min_approx": drive_since,
                    "stationary_block_min_approx": block_stat,
                    "wait_min_phys": r.wait_min_phys,
                    "charge_min_phys": r.charge_min_phys,
                    "drive_min_phys": r.drive_min_phys,
                    "note": "",
                }
            )
            t += dt
            if typ in {"CHARGE", "WAIT"} and block_stat >= 45.0 - 1e-9:
                drive_since = 0.0
                block_stat = 0.0
    return pd.DataFrame(rows)


def plot_accumulation(per_arc: pd.DataFrame) -> None:
    import matplotlib.pyplot as plt

    FIG.mkdir(parents=True, exist_ok=True)
    SRC.mkdir(parents=True, exist_ok=True)
    sub = per_arc[per_arc.time_step_min == 5]
    if not len(sub):
        return
    fig, ax = plt.subplots(figsize=(7.2, 4.2), constrained_layout=True)
    fig.patch.set_facecolor("white")
    y_p = [0.0] + sub.cum_phys_min.tolist()
    y_d = [0.0] + sub.cum_disc_min.tolist()
    x = list(range(len(y_p)))
    ax.plot(x, y_p, "-o", color="#0072B2", label="Physical cum. drive (min)")
    ax.plot(x, y_d, "-s", color="#D55E00", label="Discrete ceil cum. drive (min)")
    ax.axhline(270, color="#999999", ls="--", lw=1.2, label="4.5 h continuous limit")
    ax.set_xlabel("After N drive arcs (0 = start)")
    ax.set_ylabel("Accumulated driving time (min)")
    ax.set_title("Volvo Marrakech→Agadir @80% I2 — physical vs 5-min ceil HOS resource")
    ax.grid(True, ls=":", lw=0.4)
    ax.legend(fontsize=8)
    base = FIG / "R-Figure10b_time_discretization_hos_accumulation"
    fig.savefig(base.with_suffix(".pdf"))
    fig.savefig(base.with_suffix(".png"), dpi=400)
    plt.close(fig)
    sub.to_csv(SRC / "R-Fig10b_hos_accumulation.csv", index=False)
    print("Wrote", base)


def write_hos_policy_notes() -> None:
    text = """# Moroccan HOS policy screen (Path A) — source documentation

## Legal source

- Bulletin officiel No. 5878 bis (2010), Décret 2-10-314, Articles 15–19.
- https://www.sgg.gov.ma/BO/bo_fr/2010/bo_5878-bis_fr.pdf
- Verify page 1724 and any subsequent amendments before regulatory citation.

## Modeled policy (simplified single-duty screen)

| Rule | Modeled value | Notes |
|---|---|---|
| Daily driving | ≤ 9 h | Art. 17 analogue |
| Continuous driving | ≤ 4.5 h | Art. 18 analogue |
| Qualifying break | ≥ 45 min uninterrupted | Conservative vs split ≥15 min parts |
| Daily rest | ≥ 12 h | Art. 16; Path A does **not** implement overnight reset |
| Charging as break | Stationary rest at eligible nodes only | Real law requires driver relieved of other work |

## Path A scope statement

- Conservative **modeled** operational policy — not a full regulatory compliance certificate.
- Split breaks (Art. 19) are not fully implemented as alternative qualifying structures in search.
- Hypothetical rest/charging nodes ≠ verified legal parking facilities.
- A 24 h journey gate is a coarse out-of-scope screen, **not** proof of 12 h daily-rest compliance.
- Single-duty scenarios assume departure immediately after a completed daily rest.

## Numerical interaction (P0)

Drive arcs enter the HOS resource via `ceil(physical_duration / time_step)` steps
(`arc_preprocessing._ceil_time_steps`), while the continuous-driving limit defaults to
`round(270 / time_step_min)` steps. Multi-arc ceil inflation can exclude itineraries whose
physical driving duration remains below 270 minutes.
"""
    (OUT / "hos_policy_notes.md").write_text(text, encoding="utf-8")


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    TAB.mkdir(parents=True, exist_ok=True)
    write_hos_policy_notes()

    print("[P0] screening primary traces", flush=True)
    screen = screen_primary_traces(5)
    screen.to_csv(OUT / "primary_ceil_inflation_screen.csv", index=False)
    affected = screen[screen.potential_ceil_exclusion | screen.energy_ok_ops_inf]
    affected.to_csv(OUT / "affected_case_inventory.csv", index=False)
    print(
        f"  screened={len(screen)} potential_ceil_exclusion="
        f"{int(screen.potential_ceil_exclusion.sum())} energy_ok_ops_inf="
        f"{int(screen.energy_ok_ops_inf.sum())}",
        flush=True,
    )

    print("[P0] Casa-Tangier wait excerpt", flush=True)
    wait = casa_tangier_wait_excerpt()
    wait.to_csv(OUT / "casa_tangier_wait_schedule_excerpt.csv", index=False)

    print("[P0] per-arc + time-step sweep (Volvo MA)", flush=True)
    per_arc, sweep, summary = per_arc_and_sweep()
    per_arc.to_csv(OUT / "per_arc_physical_vs_discrete.csv", index=False)
    per_arc.to_csv(TAB / "R-T14_time_discretization_per_arc.csv", index=False)
    sweep.to_csv(OUT / "hos_timestep_sweep.csv", index=False)
    sweep.to_csv(TAB / "R-T14_time_discretization_sweep.csv", index=False)
    (OUT / "ceil_inflation_summary.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )
    plot_accumulation(per_arc)

    lines = [
        "# P0 — Temporal discretization findings",
        "",
        f"Baseline: `{_git_sha()}` / tag `evidence-freeze-518bc11`.",
        "",
        "## Volvo Marrakech→Agadir @80% I2",
        "",
    ]
    if len(sweep):
        lines.append(sweep.to_string(index=False))
        lines.append("")
    lines.extend(
        [
            "## Interpretation",
            "",
            "If phys≤270 and disc>270 at ts=5, exclusion is **numerical ceil-inflation**",
            "under HOS-in-search, not a physical continuous-driving exceedance.",
            "Family A refinements (ts=2,1) may restore ops; label mixed-ts tables explicitly.",
            "",
            "Casa–Tangier waiting: see `casa_tangier_wait_schedule_excerpt.csv`.",
            "Do not claim waiting is legally mandatory unless the physical HOS audit requires it",
            "independent of rounding.",
            "",
            "See also `hos_policy_notes.md`.",
            "",
        ]
    )
    (OUT / "P0_time_discretization_notes.md").write_text("\n".join(lines), encoding="utf-8")
    print(sweep.to_string(index=False) if len(sweep) else "no sweep rows")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
