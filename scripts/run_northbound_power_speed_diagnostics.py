#!/usr/bin/env python
"""PRIORITY 1–2: Northbound Agadir→Casablanca peak-power / grade / speed audit.

Does NOT retune OEM power. Does NOT fabricate chargers. Does NOT smooth DEM.
Compares fixed road-class cruise vs Decree 2-10-420-aware lower-speed scenarios
and power-feasible climb speeds. Outputs CSV + seeds root-cause report facts.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from morocco_etruck.energy.refrigeration import load_refrigeration  # noqa: E402
from morocco_etruck.energy.terrain import edge_dz_from_profile  # noqa: E402
from morocco_etruck.energy.traction import (  # noqa: E402
    max_power_feasible_speed_mps,
    wheel_power_at_speed_w,
)
from morocco_etruck.energy.transitions import EnergyState, apply_drive  # noqa: E402
from morocco_etruck.energy.vehicle import (  # noqa: E402
    gcm_from_payload,
    load_vehicle,
    mass_from_gcm,
    validate_gcm,
)
from morocco_etruck.energy.weather import heading_deg, wind_along_travel_mps  # noqa: E402
from morocco_etruck.optimization.arc_preprocessing import (  # noqa: E402
    simulate_drive_from_soc,
)
from morocco_etruck.optimization.multiroute_adapter import (  # noqa: E402
    load_multiroute_pilot_config,
)
from morocco_etruck.optimization.multiroute_physics import (  # noqa: E402
    build_macro_with_terrain,
    contract_od_path_union,
    load_weather_for_multiroute,
)
from morocco_etruck.road_network import load_graph_from_csv  # noqa: E402

OD_ID = "agadir_casa"
PAYLOAD_KG = 5300.0
VEHICLES = {
    "volvo_475": ROOT / "configs/vehicles/volvo_fh_electric_4x2_540kwh.yaml",
    "eactros_600": ROOT / "configs/vehicles/eactros_600.yaml",
}
FRIDGE = ROOT / "configs/energy/pass2_tomato_firm_ripe.yaml"
OUT_CSV = ROOT / "results/northbound_power_speed_diagnostics.csv"
OUT_JSON = ROOT / "results/northbound_power_speed_diagnostics_summary.json"

# Decree 2-10-420 Arts 17–18 (goods vehicles >19 t) — research interpretation
LEGAL_MOTORWAY_MAX_KMH = 80.0
LEGAL_NON_MOTORWAY_MAX_KMH = 70.0
LEGAL_MOTORWAY_NORMAL_MIN_KMH = 60.0

# Spike audit: short segments with extreme DEM grades
SPIKE_LENGTH_M = 80.0
SPIKE_ABS_GRADE = 0.08


def _highway_class(data: dict[str, Any]) -> str:
    hw = data.get("highway")
    if isinstance(hw, list):
        hw = hw[0] if hw else "default"
    return str(hw or "default").lower()


def _legal_cap_kmh(highway: str) -> float:
    if highway in {"motorway", "motorway_link"}:
        return LEGAL_MOTORWAY_MAX_KMH
    return LEGAL_NON_MOTORWAY_MAX_KMH


def _classify_slow(highway: str, v_kmh: float) -> str:
    if highway in {"motorway", "motorway_link"}:
        if v_kmh + 1e-6 < LEGAL_MOTORWAY_NORMAL_MIN_KMH:
            return "below_motorway_normal_min_60"
        return "within_motorway_normal_band"
    return "non_motorway"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-fail-rows", type=int, default=500)
    args = ap.parse_args()

    pilot = load_multiroute_pilot_config(
        ROOT / "configs/optimization/multiroute_pilot.yaml", root=ROOT
    )
    G = load_graph_from_csv(pilot.nodes_csv, pilot.edges_csv)
    import pandas as pd

    path_rows = pd.read_csv(pilot.path_alternatives_csv).to_dict(orient="records")
    arcs, origin, dest, nodes = contract_od_path_union(
        G, path_rows, OD_ID, speed_policy=pilot.speed_policy
    )
    weather, _assumed = load_weather_for_multiroute(
        root=ROOT, morocco_pilot_yaml=pilot.morocco_pilot_yaml, weather_id="cool"
    )
    fridge = load_refrigeration(FRIDGE)
    dem_meta = json.loads(
        (ROOT / "data/processed/multiroute/elevation/dem_sampling_meta.json").read_text(
            encoding="utf-8"
        )
    )

    rows: list[dict[str, Any]] = []
    summary: dict[str, Any] = {
        "od_id": OD_ID,
        "payload_kg": PAYLOAD_KG,
        "decree": "2-10-420_arts_17_18",
        "dem_source": "copdem_glo30_dsm_not_surveyed_pavement",
        "vehicles": {},
        "provenance": {
            "pilot_yaml": "configs/optimization/multiroute_pilot.yaml",
            "fridge_yaml": str(FRIDGE.relative_to(ROOT)),
            "dem_meta": "data/processed/multiroute/elevation/dem_sampling_meta.json",
            "reproduce": "python scripts/run_northbound_power_speed_diagnostics.py",
        },
    }

    for vname, vpath in VEHICLES.items():
        vehicle = load_vehicle(vpath)
        gcm = gcm_from_payload(PAYLOAD_KG, vehicle)
        validate_gcm(gcm, vehicle)
        mass = mass_from_gcm(gcm)
        vsum: dict[str, Any] = {
            "vehicle_yaml": str(vpath.relative_to(ROOT)),
            "gcm_kg": gcm,
            "mass_kg": mass,
            "peak_power_kw": vehicle.peak_power_w / 1000.0,
            "continuous_power_kw": vehicle.continuous_power_w / 1000.0,
            "n_macros": 0,
            "n_micro_edges": 0,
            "n_fixed_peak_fail": 0,
            "n_fixed_cont_fail": 0,
            "n_spike_candidates": 0,
            "n_adapt_peak_ok": 0,
            "n_adapt_cont_ok": 0,
            "n_still_peak_infeas_at_floor": 0,
            "n_below_motorway_min_60": 0,
            "failing_macro_ids": set(),
            "alts_all_fail_fixed": None,
        }
        fail_budget = args.max_fail_rows

        for darc in arcs:
            macro, tnote, dem_ok = build_macro_with_terrain(
                G,
                darc,
                terrain_mode="dem",
                elevation_dir=pilot.elevation_dir,
                road_cost_per_km=100.0,
                speed_policy=pilot.speed_policy,
            )
            vsum["n_macros"] += 1
            arc_id = str(macro.meta.get("arc_id") or darc.arc_id)
            meta_arc = (dem_meta.get("arcs") or {}).get(arc_id) or {}
            s_cursor = 0.0
            macro_fixed_fail = False

            for ei, edge in enumerate(macro.micro_edges):
                vsum["n_micro_edges"] += 1
                L = float(edge.length_m)
                dz = float(edge_dz_from_profile(macro.terrain, s_cursor, L))
                grade = dz / L if L > 1e-9 else 0.0
                # OSM ids from edge geometry ownership
                # Map micro index back to owning OSM hop when possible
                pair_idx = min(ei, max(0, len(macro.osm_edge_pairs) - 1))
                osm_u = osm_v = osm_key = None
                if macro.osm_edge_pairs:
                    # Approximate ownership: cumulative length mapping
                    cum = 0.0
                    own = macro.osm_edge_pairs[0]
                    for pu, pv in macro.osm_edge_pairs:
                        # use path node hop lengths from graph
                        try:
                            Lg = float(G.edges[pu, pv, 0].get("length", 0.0))
                        except Exception:  # noqa: BLE001
                            Lg = 0.0
                        if cum + Lg >= s_cursor + L * 0.5 or (pu, pv) == macro.osm_edge_pairs[-1]:
                            own = (pu, pv)
                            break
                        cum += Lg
                    osm_u, osm_v = own[0], own[1]
                    osm_key = 0
                highway = str(getattr(edge, "highway", None) or "default").lower() or "default"
                if highway in {"", "none", "default"} and osm_u is not None:
                    try:
                        highway = _highway_class(dict(G.edges[osm_u, osm_v, 0]))
                    except Exception:  # noqa: BLE001
                        highway = str(
                            (macro.meta.get("highway_classes") or ["default"])[0]
                        )

                v_cmd = float(edge.speed_mps)
                v_cmd_kmh = v_cmd * 3.6
                legal_cap = _legal_cap_kmh(highway)
                v_legal = min(v_cmd, legal_cap / 3.6)

                # Neutral weather for power diagnostic at mid-edge
                coords = list(edge.geometry.coords)
                mid_lat = 0.5 * (coords[0][1] + coords[-1][1])
                mid_lon = 0.5 * (coords[0][0] + coords[-1][0])
                wp = weather.nearest(mid_lat, mid_lon)
                rho = wp.air_density_kg_m3(vehicle.air_density_default_kg_m3)
                head = heading_deg(coords[0][0], coords[0][1], coords[-1][0], coords[-1][1])
                wind_along = wind_along_travel_mps(
                    wp.wind_speed_mean_mps, wp.wind_dir_mean_deg, head
                )

                p_fixed = wheel_power_at_speed_w(
                    length_m=L,
                    dz_m=dz,
                    mass_kg=mass,
                    v_mps=v_cmd,
                    wind_along_travel_mps=wind_along,
                    rho_kg_m3=rho,
                    vehicle=vehicle,
                )
                peak_ok_fixed = p_fixed <= vehicle.peak_power_w + 1e-6
                cont_ok_fixed = p_fixed <= vehicle.continuous_power_w + 1e-6
                if not peak_ok_fixed:
                    vsum["n_fixed_peak_fail"] += 1
                    macro_fixed_fail = True
                    vsum["failing_macro_ids"].add(arc_id)
                if not cont_ok_fixed:
                    vsum["n_fixed_cont_fail"] += 1

                is_spike = L <= SPIKE_LENGTH_M and abs(grade) >= SPIKE_ABS_GRADE
                if is_spike:
                    vsum["n_spike_candidates"] += 1

                v_peak, p_at_peak_v = max_power_feasible_speed_mps(
                    length_m=L,
                    dz_m=dz,
                    mass_kg=mass,
                    wind_along_travel_mps=wind_along,
                    rho_kg_m3=rho,
                    vehicle=vehicle,
                    power_limit_w=float(vehicle.peak_power_w),
                    v_hi_mps=v_cmd,
                    v_lo_mps=1.0 / 3.6,
                )
                v_cont, p_at_cont_v = max_power_feasible_speed_mps(
                    length_m=L,
                    dz_m=dz,
                    mass_kg=mass,
                    wind_along_travel_mps=wind_along,
                    rho_kg_m3=rho,
                    vehicle=vehicle,
                    power_limit_w=float(vehicle.continuous_power_w),
                    v_hi_mps=v_cmd,
                    v_lo_mps=1.0 / 3.6,
                )
                if v_peak is not None:
                    vsum["n_adapt_peak_ok"] += 1
                else:
                    vsum["n_still_peak_infeas_at_floor"] += 1
                if v_cont is not None:
                    vsum["n_adapt_cont_ok"] += 1

                v_peak_kmh = (v_peak * 3.6) if v_peak is not None else None
                slow_class = (
                    _classify_slow(highway, v_peak_kmh)
                    if v_peak_kmh is not None
                    else "gradeability_fail_at_1kmh"
                )
                if slow_class == "below_motorway_normal_min_60":
                    vsum["n_below_motorway_min_60"] += 1

                st0 = EnergyState(soc=0.8, trailer_soc=None)
                r_fixed = apply_drive(
                    st0,
                    edge,
                    vehicle=vehicle,
                    weather=weather,
                    fridge_cfg=fridge,
                    gcm_kg=gcm,
                    refrigeration_on=True,
                    power_source="A",
                    terrain=macro.terrain,
                    s_cursor_m=s_cursor,
                    speed_mps=v_cmd,
                )
                r_adapt = apply_drive(
                    st0,
                    edge,
                    vehicle=vehicle,
                    weather=weather,
                    fridge_cfg=fridge,
                    gcm_kg=gcm,
                    refrigeration_on=True,
                    power_source="A",
                    terrain=macro.terrain,
                    s_cursor_m=s_cursor,
                    speed_mps=v_cmd,
                    adapt_speed_to_peak_power=True,
                    adapt_speed_to_continuous_power=False,
                    min_adapt_speed_mps=1.0 / 3.6,
                )
                r_adapt_cont = apply_drive(
                    st0,
                    edge,
                    vehicle=vehicle,
                    weather=weather,
                    fridge_cfg=fridge,
                    gcm_kg=gcm,
                    refrigeration_on=True,
                    power_source="A",
                    terrain=macro.terrain,
                    s_cursor_m=s_cursor,
                    speed_mps=v_cmd,
                    adapt_speed_to_peak_power=True,
                    adapt_speed_to_continuous_power=True,
                    min_adapt_speed_mps=1.0 / 3.6,
                )

                emit = (
                    (not peak_ok_fixed)
                    or is_spike
                    or (v_peak is not None and v_peak + 1e-6 < v_cmd)
                    or (fail_budget > 0 and abs(grade) > 0.05)
                )
                if emit and fail_budget >= 0:
                    if not peak_ok_fixed or is_spike:
                        fail_budget -= 1
                    rows.append(
                        {
                            "vehicle": vname,
                            "od_id": OD_ID,
                            "macro_arc_id": arc_id,
                            "macro_u": darc.u,
                            "macro_v": darc.v,
                            "micro_index": ei,
                            "osm_u": osm_u,
                            "osm_v": osm_v,
                            "osm_key": osm_key,
                            "highway": highway,
                            "length_m": L,
                            "dz_m": dz,
                            "grade": grade,
                            "abs_grade": abs(grade),
                            "is_short_dem_spike_candidate": is_spike,
                            "dem_source": meta_arc.get("source") or macro.terrain.source,
                            "dem_quality": meta_arc.get("quality"),
                            "macro_max_abs_grade_meta": meta_arc.get("max_abs_grade"),
                            "macro_length_m_meta": meta_arc.get("length_m"),
                            "sampling_note": "geometry-owned COP-DEM GLO-30 DSM samples along OSM centerline; not surveyed pavement grade",
                            "v_cmd_kmh": v_cmd_kmh,
                            "v_legal_cap_kmh": legal_cap,
                            "v_legal_capped_kmh": v_legal * 3.6,
                            "P_wheel_fixed_kw": p_fixed / 1000.0,
                            "peak_ok_fixed": peak_ok_fixed,
                            "cont_ok_fixed": cont_ok_fixed,
                            "peak_kw": vehicle.peak_power_w / 1000.0,
                            "cont_kw": vehicle.continuous_power_w / 1000.0,
                            "gcm_kg": gcm,
                            "mass_kg": mass,
                            "v_peak_adapt_kmh": v_peak_kmh,
                            "P_wheel_at_peak_adapt_kw": (
                                None if v_peak is None else p_at_peak_v / 1000.0
                            ),
                            "v_cont_adapt_kmh": (
                                None if v_cont is None else v_cont * 3.6
                            ),
                            "P_wheel_at_cont_adapt_kw": (
                                None if v_cont is None else p_at_cont_v / 1000.0
                            ),
                            "slow_operation_class": slow_class,
                            "apply_fixed_reason": r_fixed.violation_reason,
                            "apply_adapt_peak_reason": r_adapt.violation_reason,
                            "apply_adapt_peak_speed_kmh": (
                                None
                                if r_adapt.speed_mps_used is None
                                else r_adapt.speed_mps_used * 3.6
                            ),
                            "apply_adapt_peak_adapted": r_adapt.speed_adapted,
                            "apply_adapt_cont_reason": r_adapt_cont.violation_reason,
                            "apply_adapt_cont_speed_kmh": (
                                None
                                if r_adapt_cont.speed_mps_used is None
                                else r_adapt_cont.speed_mps_used * 3.6
                            ),
                            "terrain_note": tnote,
                            "dem_ok": dem_ok,
                            "scenario_A_fixed_cruise": "peak_fail"
                            if not peak_ok_fixed
                            else "ok",
                            "scenario_B_legal_cap_only": "same_as_A_if_defaults_at_legal",
                            "scenario_C_peak_adapt": (
                                "ok"
                                if r_adapt.violation_reason != "peak_motor_power_exceeded"
                                else "still_infeasible"
                            ),
                            "scenario_D_cont_adapt": (
                                "ok"
                                if r_adapt_cont.violation_reason
                                != "peak_motor_power_exceeded"
                                else "still_infeasible"
                            ),
                        }
                    )
                s_cursor += L

            # Macro-level continuous sim fixed vs adapt
            ok_f, dt_f, soc_f, _, reason_f, _ = simulate_drive_from_soc(
                macro.micro_edges,
                macro.terrain,
                soc0=0.8,
                trailer_soc0=None,
                vehicle=vehicle,
                weather=weather,
                fridge_cfg=fridge,
                gcm_kg=gcm,
                refrigeration_on=True,
                power_source="A",
            )
            ok_a, dt_a, soc_a, _, reason_a, _ = simulate_drive_from_soc(
                macro.micro_edges,
                macro.terrain,
                soc0=0.8,
                trailer_soc0=None,
                vehicle=vehicle,
                weather=weather,
                fridge_cfg=fridge,
                gcm_kg=gcm,
                refrigeration_on=True,
                power_source="A",
                adapt_speed_to_peak_power=True,
                adapt_speed_to_continuous_power=False,
            )
            rows.append(
                {
                    "vehicle": vname,
                    "od_id": OD_ID,
                    "macro_arc_id": arc_id,
                    "macro_u": darc.u,
                    "macro_v": darc.v,
                    "micro_index": -1,
                    "row_type": "macro_sim",
                    "macro_fixed_ok": ok_f,
                    "macro_fixed_reason": reason_f,
                    "macro_fixed_dt_s": dt_f,
                    "macro_fixed_soc_end": soc_f,
                    "macro_adapt_peak_ok": ok_a,
                    "macro_adapt_peak_reason": reason_a,
                    "macro_adapt_peak_dt_s": dt_a,
                    "macro_adapt_peak_soc_end": soc_a,
                    "macro_fixed_any_micro_peak_fail": macro_fixed_fail,
                    "length_m": macro.length_m,
                    "dem_ok": dem_ok,
                    "gcm_kg": gcm,
                    "peak_kw": vehicle.peak_power_w / 1000.0,
                    "cont_kw": vehicle.continuous_power_w / 1000.0,
                }
            )

        # Path-alternative coverage of fixed failures
        failing = set(vsum["failing_macro_ids"])
        vsum["failing_macro_ids"] = sorted(failing)
        vsum["n_failing_macros"] = len(failing)

        # Per-path: does every alternative contain a fixed peak failure?
        path_fail_all = True
        n_paths = 0
        for row in path_rows:
            if str(row.get("od_id")) != OD_ID:
                continue
            n_paths += 1
            # Conservative: if any failing macro exists on OD, treat path-level as unknown
            # unless we can map; use union-level: if all macros on union fail somewhere
        vsum["n_path_alts_in_csv"] = n_paths
        # If every macro fails fixed → all alts fail; if some macros ok, some alts may work
        all_macros_fail = vsum["n_macros"] > 0 and vsum["n_failing_macros"] == vsum["n_macros"]
        vsum["every_macro_has_fixed_peak_fail"] = all_macros_fail
        vsum["interpretation"] = (
            "fixed_cruise_rejects_climbs; peak-adapt restores micro power on most segments "
            "if n_adapt_peak_ok high; DSM grades not verified pavement"
        )
        summary["vehicles"][vname] = vsum

    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    # Normalize keys for CSV
    keys: list[str] = []
    seen = set()
    for r in rows:
        for k in r:
            if k not in seen:
                seen.add(k)
                keys.append(k)
    with OUT_CSV.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=keys, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow(r)

    # JSON-serializable summary
    def _ser(o: Any) -> Any:
        if isinstance(o, set):
            return sorted(o)
        if isinstance(o, dict):
            return {k: _ser(v) for k, v in o.items()}
        if isinstance(o, list):
            return [_ser(x) for x in o]
        if isinstance(o, float) and (math.isnan(o) or math.isinf(o)):
            return None
        return o

    OUT_JSON.write_text(json.dumps(_ser(summary), indent=2), encoding="utf-8")
    print(f"Wrote {OUT_CSV} ({len(rows)} rows)")
    print(f"Wrote {OUT_JSON}")
    for vn, vs in summary["vehicles"].items():
        print(
            f"  {vn}: micros={vs['n_micro_edges']} fixed_peak_fail={vs['n_fixed_peak_fail']} "
            f"adapt_peak_ok={vs['n_adapt_peak_ok']} below_60={vs['n_below_motorway_min_60']} "
            f"spikes={vs['n_spike_candidates']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
