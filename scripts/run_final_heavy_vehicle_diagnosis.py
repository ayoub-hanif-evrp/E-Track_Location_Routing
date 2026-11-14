#!/usr/bin/env python
"""Publication-readiness: diagnose Volvo 15 t H50/H80 discrete infeasibility.

Does NOT retune vehicle YAML. Power sensitivity overrides are in-memory only and
labeled as manufacturer-menu bounds already documented in the Volvo pack.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter, defaultdict
from dataclasses import replace
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from morocco_etruck.energy.transitions import EnergyState, apply_drive  # noqa: E402
from morocco_etruck.energy.vehicle import (  # noqa: E402
    gcm_from_payload,
    load_vehicle,
    validate_gcm,
)
from morocco_etruck.optimization.label_setting import SolverStatus, solve_mrls  # noqa: E402
from morocco_etruck.optimization.multiroute_adapter import (  # noqa: E402
    clone_physics_instance_for_subset,
)
from morocco_etruck.optimization.multiroute_placement import (  # noqa: E402
    load_multiroute_placement_config,
)
from morocco_etruck.optimization.multiroute_placement_evaluation import (  # noqa: E402
    evaluate_multiroute_mission,
    prepare_multiroute_placement_context,
)
from morocco_etruck.optimization.placement_certification import is_peak_motor_reason  # noqa: E402

VEHICLE = ROOT / "configs/vehicles/volvo_fh_electric_4x2_540kwh.yaml"
CFG08 = ROOT / "configs/optimization/multiroute_placement_08.yaml"
FRIDGE = ROOT / "configs/energy/task07b_thermal_nominal.yaml"
ROAD_CENTS = 100.0
PAYLOAD = 15000.0

CELLS = [
    {"id": "H50", "demand": "H50_dem_p15000_soc05", "soc": 0.5},
    {"id": "H80", "demand": "H80_dem_p15000_soc08", "soc": 0.8},
]
OD_FOCUS = ("casa_marrakech", "casa_agadir", "marrakech_agadir")
# Documented OEM Performance menu bounds (kW); YAML mid-menu default remains 400.
POWER_MENU_KW = (300.0, 400.0, 540.0)


def _shortest_node_path(inst) -> list[str] | None:
    from collections import defaultdict as dd
    import heapq

    graph: dict[str, list[tuple[str, int]]] = dd(list)
    for a in inst.arcs:
        graph[a.u].append((a.v, int(a.road_cost)))
    pq = [(0, inst.origin, [inst.origin])]
    seen: dict[str, int] = {}
    while pq:
        cost, node, path = heapq.heappop(pq)
        if node in seen and seen[node] <= cost:
            continue
        seen[node] = cost
        if node == inst.destination:
            return path
        for v, rc in graph[node]:
            heapq.heappush(pq, (cost + rc, v, path + [v]))
    return None


def _continuous_along_path(
    *,
    inst,
    ctx,
    soc_init: float,
    vehicle,
) -> dict[str, Any]:
    if ctx.terrain_mode == "dem" and not ctx.dem_complete:
        return {
            "continuous_feasible": None,
            "class": "unresolved",
            "reason": "dem_incomplete",
            "terminal_soc": None,
        }
    path = _shortest_node_path(inst)
    if not path or len(path) < 2:
        return {
            "continuous_feasible": False,
            "class": "unresolved",
            "reason": "no_shortest_path",
            "terminal_soc": None,
        }
    node_arcs = {(a.u, a.v): a for a in inst.arcs}
    state = EnergyState(soc=float(soc_init), trailer_soc=None)
    t_s = length = 0.0
    for u, v in zip(path[:-1], path[1:]):
        arc = node_arcs.get((u, v))
        if arc is None or not arc.arc_id:
            return {
                "continuous_feasible": None,
                "class": "unresolved",
                "reason": f"missing_arc:{u}->{v}",
                "terminal_soc": state.soc,
            }
        macro = ctx.macros_by_arc_id.get(str(arc.arc_id))
        if macro is None:
            return {
                "continuous_feasible": None,
                "class": "unresolved",
                "reason": f"missing_macro:{arc.arc_id}",
                "terminal_soc": state.soc,
            }
        s_cursor = 0.0
        for edge in macro.micro_edges:
            tr = apply_drive(
                state,
                edge,
                vehicle=vehicle,
                weather=ctx.weather,
                fridge_cfg=ctx.fridge,
                gcm_kg=ctx.gcm_kg,
                refrigeration_on=ctx.refrigeration_on,
                power_source=ctx.power_source,
                terrain=macro.terrain,
                s_cursor_m=s_cursor,
                speed_mps=edge.speed_mps if getattr(edge, "speed_mps", None) else None,
            )
            t_s += tr.dt_s
            length += tr.length_m
            s_cursor += edge.length_m
            if tr.violation_reason == "peak_motor_power_exceeded":
                return {
                    "continuous_feasible": False,
                    "class": "peak_motor",
                    "reason": tr.violation_reason,
                    "terminal_soc": tr.next_state.soc,
                    "drive_time_s": t_s,
                    "length_m": length,
                    "fail_arc": str(arc.arc_id),
                }
            if not tr.soc_feasible:
                reason = tr.violation_reason or "tractor_soc_floor"
                cls = "quantize" if "quantiz" in reason else "soc_floor"
                if "soc" in reason or reason == "tractor_soc_floor":
                    cls = "soc_floor"
                return {
                    "continuous_feasible": False,
                    "class": cls,
                    "reason": reason,
                    "terminal_soc": tr.next_state.soc,
                    "drive_time_s": t_s,
                    "length_m": length,
                    "fail_arc": str(arc.arc_id),
                }
            state = tr.next_state
    return {
        "continuous_feasible": True,
        "class": "continuous_ok",
        "reason": None,
        "terminal_soc": state.soc,
        "drive_time_s": t_s,
        "length_m": length,
    }


def _drive_table_reason_hist(inst) -> dict[str, int]:
    c: Counter[str] = Counter()
    for arc in inst.arcs:
        table = arc.drive_table or {}
        for entry in table.values():
            if entry.feasible:
                c["feasible"] += 1
            else:
                c[str(entry.reason or "unknown")] += 1
    return dict(c)


def _classify_row(
    *,
    cont_class: str,
    cont_ok: bool | None,
    mrls_none: str,
    mrls_ball: str,
    served_ball: bool,
    q: int,
) -> str:
    if cont_class == "peak_motor":
        return "peak_motor"
    if cont_class in {"soc_floor"} and not served_ball:
        # Charging cannot help if continuous no-charge fails on SOC before any station
        # — still check whether Ball discrete differs
        if mrls_ball == "INFEASIBLE" and mrls_none == "INFEASIBLE":
            return "soc_floor"
    if cont_ok is True and mrls_ball == "INFEASIBLE":
        return "discrete_grid_reject"
    if cont_ok is True and mrls_ball == "LIMIT_REACHED":
        return "unresolved"
    if cont_class == "quantize":
        return "quantize"
    if served_ball:
        return "served"
    if mrls_none == "INFEASIBLE" and mrls_ball == "OPTIMAL":
        return "charge_access"
    if mrls_none == "INFEASIBLE" and mrls_ball == "INFEASIBLE" and cont_ok is False:
        return cont_class if cont_class not in {"continuous_ok"} else "soc_floor"
    if mrls_ball == "LIMIT_REACHED":
        return "unresolved"
    return "unresolved"


def diagnose_cell(
    *,
    cell: dict[str, Any],
    q: int,
    power_kw: float | None = None,
) -> list[dict[str, Any]]:
    cfg = load_multiroute_placement_config(CFG08, root=ROOT)
    vehicle = load_vehicle(VEHICLE)
    label_power = float(vehicle.peak_power_w) / 1000.0
    if power_kw is not None:
        w = float(power_kw) * 1000.0
        vehicle = replace(
            vehicle,
            continuous_power_w=w,
            peak_power_w=w,
            peak_regen_power_w=w,
        )
        label_power = float(power_kw)

    gcm = gcm_from_payload(PAYLOAD, vehicle)
    validate_gcm(gcm, vehicle)

    print(
        f"\n=== diagnose {cell['id']} q={q} power={label_power:.0f}kW "
        f"gcm={gcm:.0f} ===",
        flush=True,
    )
    t0 = time.perf_counter()
    # Discrete build always uses YAML vehicle (committed defaults). Power override
    # applies only to continuous scan below — never rewrites YAML.
    context = prepare_multiroute_placement_context(
        cfg,
        root=ROOT,
        demand_name=cell["demand"],
        energy_quantum_kwh=q,
        objective_mode="enroute_incremental_cost",
        vehicle_yaml=VEHICLE,
        road_cost_per_km=ROAD_CENTS,
        fridge_yaml=FRIDGE,
        charger_power_kw=350.0,
        max_alternatives_for_union=2,
    )
    sites = cfg.sites
    all_ids = {s.id for s in sites}
    rows: list[dict[str, Any]] = []

    for mid, prep in context["prepared"].items():
        od = prep.mission.od_id
        if od not in OD_FOCUS:
            continue
        inst = prep.template
        ctx = prep.ctx
        soc_init = float(cell["soc"])

        # Continuous with (possibly overridden) vehicle
        cont = _continuous_along_path(
            inst=inst, ctx=ctx, soc_init=soc_init, vehicle=vehicle
        )
        hist = _drive_table_reason_hist(inst)
        peak_share = sum(
            v for k, v in hist.items() if is_peak_motor_reason(k)
        )
        soc_share = sum(
            v
            for k, v in hist.items()
            if "soc" in k.lower() or "floor" in k.lower()
        )

        r_none = evaluate_multiroute_mission(
            prep,
            installed=set(),
            sites=sites,
            max_seconds=30.0,
            max_expansions=80_000,
        )
        r_ball = evaluate_multiroute_mission(
            prep,
            installed=all_ids,
            sites=sites,
            max_seconds=30.0,
            max_expansions=80_000,
        )

        cause = _classify_row(
            cont_class=str(cont.get("class")),
            cont_ok=cont.get("continuous_feasible"),
            mrls_none=r_none.status,
            mrls_ball=r_ball.status,
            served_ball=bool(r_ball.served),
            q=q,
        )
        # If continuous peak with default tables also show peak, reinforce
        if peak_share > 0 and cont.get("class") == "peak_motor":
            cause = "peak_motor"
        elif (
            cont.get("continuous_feasible") is True
            and r_ball.status == "INFEASIBLE"
            and not r_ball.served
        ):
            cause = "discrete_grid_reject"

        row = {
            "cell_id": cell["id"],
            "od_id": od,
            "mission_id": mid,
            "soc_init": cell["soc"],
            "cargo_payload_kg": PAYLOAD,
            "gcm_kg": gcm,
            "q_kwh": q,
            "power_kw_continuous_scan": label_power,
            "power_override": power_kw is not None and abs(label_power - 400.0) > 1e-6,
            "power_note": (
                "in_memory_menu_bound_only"
                if power_kw is not None
                else "yaml_assumed_400"
            ),
            "dem_complete": bool(ctx.dem_complete),
            "continuous_feasible": cont.get("continuous_feasible"),
            "continuous_class": cont.get("class"),
            "continuous_reason": cont.get("reason"),
            "continuous_terminal_soc": cont.get("terminal_soc"),
            "continuous_fail_arc": cont.get("fail_arc"),
            "drive_table_hist_json": json.dumps(hist, sort_keys=True),
            "drive_table_peak_entries": peak_share,
            "drive_table_soc_entries": soc_share,
            "mrls_none_status": r_none.status,
            "mrls_none_served": bool(r_none.served),
            "mrls_none_uncertified": bool(r_none.uncertified),
            "mrls_ball_status": r_ball.status,
            "mrls_ball_served": bool(r_ball.served),
            "mrls_ball_uncertified": bool(r_ball.uncertified),
            "mrls_ball_reason": r_ball.reason,
            "diagnosis_class": cause,
            "publishable_claim": (
                "infeasible_under_assumed_vehicle_model_and_reduced_network"
            ),
            "prep_sec": time.perf_counter() - t0,
        }
        rows.append(row)
        print(
            f"  {od}: cont={cont.get('class')} none={r_none.status} "
            f"ball={r_ball.status} served={r_ball.served} -> {cause}",
            flush=True,
        )
    return rows


def write_report(df: pd.DataFrame, path: Path) -> None:
    lines = [
        "# Final heavy-vehicle feasibility diagnosis (Volvo 15 t)",
        "",
        "Base Task 08 finding: Volvo FH Electric 475 kWh @ 15 t cargo serves "
        "**0 / 5.5** at SOC 0.5 and 0.8 even with all hypothetical candidate sites "
        "(Ball). This note diagnoses *why* under the **assumed** vehicle model.",
        "",
        "**Publishable phrasing:** these missions are infeasible under this assumed "
        "vehicle configuration and reduced path-union network. "
        "**Not** a claim that Volvo cannot transport 15 tonnes in Morocco.",
        "",
        "## Vehicle configuration under test",
        "",
        "| Field | Value | Provenance |",
        "| --- | ---: | --- |",
        "| Usable battery | 475 kWh | manufacturer (MA page conflict note) |",
        "| Continuous / peak power | 400 / 400 kW | **assumed_variant_pick** (OEM menu 300–540, no cont/peak split) |",
        "| Empty tractor / trailer | 12 t / 8 t | **assumed** |",
        "| GCM at 15 t cargo | 35 t | empty+payload; tech GCW 65 t manufacturer |",
        "| Path union | max_alts=2 DEM | scientific pilot |",
        "| Refrigeration | ON, Task 07B nominal UA | research |",
        "",
        "## Diagnosis matrix",
        "",
        "| Cell | OD | q | Power scan kW | Continuous | MRLS none | MRLS Ball | Class |",
        "| --- | --- | ---: | ---: | --- | --- | --- | --- |",
    ]
    base = df[~df["power_override"]].copy() if "power_override" in df.columns else df
    for _, r in base.sort_values(["cell_id", "od_id", "q_kwh"]).iterrows():
        lines.append(
            f"| {r.cell_id} | {r.od_id} | {int(r.q_kwh)} | {r.power_kw_continuous_scan} | "
            f"{r.continuous_class} | {r.mrls_none_status} | {r.mrls_ball_status} | "
            f"**{r.diagnosis_class}** |"
        )

    # Aggregate verdict
    classes = base["diagnosis_class"].value_counts().to_dict() if not base.empty else {}
    lines.extend(
        [
            "",
            "## Cause summary (default 400 kW YAML, no power override)",
            "",
            "```",
            json.dumps(classes, indent=2),
            "```",
            "",
        ]
    )

    dominant = None
    if classes:
        dominant = max(classes.items(), key=lambda kv: kv[1])[0]

    lines.extend(
        [
            "## Interpretation",
            "",
        ]
    )
    if dominant == "peak_motor":
        lines.append(
            "Leading cause: **peak motor power** on graded DEM micro-edges at GCM 35 t "
            "under the assumed 400 kW continuous/peak rating. Charging sites cannot "
            "bypass a DRIVE power violation on an arc."
        )
    elif dominant == "soc_floor":
        lines.append(
            "Leading cause: **SOC / energy floor** on continuous or discrete drive "
            "before destination; Ball chargers did not restore serviceability for these "
            "path-union missions."
        )
    elif dominant == "discrete_grid_reject":
        lines.append(
            "Leading cause: **discrete energy-grid rejection** — continuous physics along "
            "the shortest path is feasible, but MRLS at the tested q remains INFEASIBLE. "
            "Compare q=10 vs q=5 rows."
        )
    elif dominant == "charge_access":
        lines.append(
            "Leading cause: **charging access** — none-site infeasible, all-sites served."
        )
    else:
        lines.append(
            f"Leading labeled class: `{dominant}`. See matrix; treat as "
            "**configuration-dependent / not field-validated**."
        )

    sens = df[df["power_override"]] if "power_override" in df.columns else pd.DataFrame()
    if not sens.empty:
        lines.extend(
            [
                "",
                "## Manufacturer-menu power sensitivity (diagnostic only)",
                "",
                "In-memory override of continuous=peak=regen at OEM menu bounds "
                "300 / 540 kW already documented in the Volvo YAML. "
                "**Committed vehicle defaults are unchanged.**",
                "",
                "| Cell | OD | Power kW | Continuous class | Note |",
                "| --- | --- | ---: | --- | --- |",
            ]
        )
        for _, r in sens.sort_values(
            ["cell_id", "od_id", "power_kw_continuous_scan"]
        ).iterrows():
            lines.append(
                f"| {r.cell_id} | {r.od_id} | {r.power_kw_continuous_scan} | "
                f"{r.continuous_class} | {r.power_note} |"
            )
        lines.append(
            "\nIf 540 kW removes peak-motor failures while 300 kW worsens them, the "
            "H50/H80 zero-coverage result is **configuration-dependent** on the "
            "assumed power pick — still not a Morocco field conclusion."
        )

    lines.extend(
        [
            "",
            "## What we may / may not claim",
            "",
            "| Claim | Status |",
            "| --- | --- |",
            "| Discrete MRLS + replay: Volvo 15 t H50/H80 unserved under Ball | Supported by Task 08 + this diagnosis |",
            "| Cause class under assumed 400 kW / assumed masses / path-union | Supported by this report |",
            "| Volvo cannot haul 15 t on Moroccan highways | **Unsupported** |",
            "| Assumed 400 kW equals a specific OEM continuous/peak split | **Unsupported** (menu listed, split unpublished) |",
            "",
            f"Generated rows: `{len(df)}`. CSV: `results/final_heavy_vehicle_feasibility_diagnosis.csv`.",
            "",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote {path}", flush=True)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--include-power-sensitivity",
        action="store_true",
        default=True,
        help="Run continuous scans at OEM menu 300/540 kW (default on)",
    )
    p.add_argument("--no-power-sensitivity", action="store_true")
    args = p.parse_args()
    do_sens = bool(args.include_power_sensitivity) and not bool(args.no_power_sensitivity)

    rows: list[dict[str, Any]] = []
    for cell in CELLS:
        for q in (10, 5):
            rows.extend(diagnose_cell(cell=cell, q=q, power_kw=None))
        if do_sens:
            # Continuous-only power sensitivity at q=10 build (tables still YAML 400;
            # continuous scan uses override vehicle).
            for pkw in (300.0, 540.0):
                rows.extend(diagnose_cell(cell=cell, q=10, power_kw=pkw))

    out = ROOT / "results/final_heavy_vehicle_feasibility_diagnosis.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame(rows)
    df.to_csv(out, index=False)
    print(f"Wrote {out} ({len(df)} rows)", flush=True)
    write_report(df, ROOT / "reports/final_heavy_vehicle_feasibility_diagnosis.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
