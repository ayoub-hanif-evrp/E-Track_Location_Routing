"""Continuous-physics replay of discrete Moroccan MRLS solutions."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from morocco_etruck.energy.refrigeration import refrigeration_energy_j
from morocco_etruck.optimization.arc_preprocessing import simulate_drive_from_soc
from morocco_etruck.optimization.morocco_adapter import MoroccoMissionContext
from morocco_etruck.optimization.problem import RoutingInstance


@dataclass
class ContinuousReplayReport:
    ok: bool
    reason: str | None
    discrete_cost: int | None
    discrete_t_steps: int | None
    discrete_E_truck: int | None
    continuous_duration_s: float
    continuous_E_truck_kwh: float | None
    continuous_E_trailer_kwh: float | None
    delta_energy_kwh: float | None
    delta_time_s: float | None
    min_soc: float | None


def continuous_replay(
    ctx: MoroccoMissionContext,
    inst: RoutingInstance,
    actions: list[dict[str, Any]],
    *,
    discrete_cost: int | None = None,
    discrete_t: int | None = None,
    discrete_E_truck: int | None = None,
) -> ContinuousReplayReport:
    """
    Replay DRIVE/CHARGE/WAIT with Task 02B continuous apply_drive + charge model.

    Uses the same underlying physics helpers as DRIVE-table preprocessing
    (numerical reconstruction of the action sequence). This is NOT independent
    empirical validation against measured truck logs.

    Charging uses station power×η for duration, aux_w / TRU for stationary load,
    and the same efficiency for battery vs grid energy definitions as discrete MRLS.

    If the discrete solution fails continuous floors / peak power → ok=False
    (invalid for Moroccan mission claims).
    """
    usable = float(ctx.vehicle.usable_kwh)
    soc = inst.E_truck_init / usable
    trailer_soc = None
    if inst.E_trailer_init is not None:
        trailer_soc = inst.E_trailer_init / float(ctx.fridge.trailer_usable_kwh)
    min_soc = soc
    t_s = 0.0
    # Index by arc_id when present; (u,v) only when unique.
    by_id: dict[str, Any] = {}
    for m in ctx.macros:
        aid = str((m.meta or {}).get("arc_id") or "")
        if aid:
            by_id[aid] = m
    current_node = inst.origin

    for act in actions:
        typ = act.get("type")
        if typ == "DRIVE":
            u, v = act["u"], act["v"]
            if current_node != u:
                return ContinuousReplayReport(
                    False,
                    f"drive_from_wrong_node:{current_node}!={u}",
                    discrete_cost,
                    discrete_t,
                    discrete_E_truck,
                    t_s,
                    None,
                    None,
                    None,
                    None,
                    min_soc,
                )
            aid = act.get("arc_id")
            macro = None
            if aid is not None and str(aid).strip():
                macro = by_id.get(str(aid))
                if macro is None:
                    return ContinuousReplayReport(
                        False,
                        f"missing_or_ambiguous_arc_id:{aid}",
                        discrete_cost,
                        discrete_t,
                        discrete_E_truck,
                        t_s,
                        None,
                        None,
                        None,
                        None,
                        min_soc,
                    )
                if macro.u != u or macro.v != v:
                    return ContinuousReplayReport(
                        False,
                        f"arc_id_endpoint_mismatch:{macro.u}->{macro.v}!={u}->{v}",
                        discrete_cost,
                        discrete_t,
                        discrete_E_truck,
                        t_s,
                        None,
                        None,
                        None,
                        None,
                        min_soc,
                    )
            else:
                cands = [m for m in ctx.macros if m.u == u and m.v == v]
                if len(cands) != 1:
                    return ContinuousReplayReport(
                        False,
                        "ambiguous_parallel_arc" if cands else f"missing_macro:{(u, v)}",
                        discrete_cost,
                        discrete_t,
                        discrete_E_truck,
                        t_s,
                        None,
                        None,
                        None,
                        None,
                        min_soc,
                    )
                macro = cands[0]
            current_node = v
            ok, dt, soc, trailer_soc, reason, _e = simulate_drive_from_soc(
                macro.micro_edges,
                macro.terrain,
                soc0=soc,
                trailer_soc0=trailer_soc,
                vehicle=ctx.vehicle,
                weather=ctx.weather,
                fridge_cfg=ctx.fridge,
                gcm_kg=ctx.gcm_kg,
                refrigeration_on=ctx.refrigeration_on,
                power_source=ctx.power_source,
            )
            t_s += dt
            min_soc = min(min_soc, soc)
            if not ok:
                return ContinuousReplayReport(
                    False, reason, discrete_cost, discrete_t, discrete_E_truck,
                    t_s, soc * usable,
                    None if trailer_soc is None else trailer_soc * ctx.fridge.trailer_usable_kwh,
                    None, None, min_soc,
                )
        elif typ == "CHARGE":
            node = act["node"]
            if node != current_node:
                return ContinuousReplayReport(
                    False,
                    f"charge_wrong_node:{current_node}!={node}",
                    discrete_cost,
                    discrete_t,
                    discrete_E_truck,
                    t_s,
                    None,
                    None,
                    None,
                    None,
                    min_soc,
                )
            if node not in inst.active_stations:
                return ContinuousReplayReport(
                    False, "station_inactive", discrete_cost, discrete_t, discrete_E_truck,
                    t_s, None, None, None, None, min_soc,
                )
            st = inst.stations.get(node)
            if st is None or not st.compatible:
                return ContinuousReplayReport(
                    False, "incompatible_charger", discrete_cost, discrete_t, discrete_E_truck,
                    t_s, None, None, None, None, min_soc,
                )
            de = float(act["delta_e_kwh"])
            # Match discrete duration (integer steps) when provided
            if "steps" in act:
                dt = int(act["steps"]) * ctx.time_step_min * 60.0
            else:
                batt_kw = st.power_kw * st.eta
                dt = (de / batt_kw) * 3600.0 if batt_kw > 0 else 0.0
            aux_w = float(inst.aux_w) if inst.aux_w > 0 else float(ctx.vehicle.P_aux_w)
            e_aux_kwh = aux_w * dt / 3.6e6
            if inst.tru_mean_w > 0 and ctx.refrigeration_on:
                e_ref_kwh = float(inst.tru_mean_w) * dt / 3.6e6
            else:
                mid = next(iter(ctx.weather.points.values()))
                e_ref_kwh = refrigeration_energy_j(
                    duration_s=dt,
                    T_amb_c=mid.T_mean_c,
                    params=ctx.fridge,
                    refrigeration_on=ctx.refrigeration_on,
                ) / 3.6e6
            E_tr = soc * usable + de
            if ctx.power_source == "A":
                E_tr -= e_aux_kwh + e_ref_kwh
            else:
                E_tr -= e_aux_kwh
                if trailer_soc is not None and ctx.refrigeration_on:
                    trailer_soc = (
                        trailer_soc * ctx.fridge.trailer_usable_kwh - e_ref_kwh
                    ) / ctx.fridge.trailer_usable_kwh
            E_tr = min(usable * ctx.vehicle.soc_max, E_tr)
            soc = E_tr / usable
            t_s += dt
            if discrete_t is not None and t_s > (inst.deadline_steps + 1e-9) * ctx.time_step_min * 60.0:
                return ContinuousReplayReport(
                    False, "deadline", discrete_cost, discrete_t, discrete_E_truck,
                    t_s, soc * usable,
                    None if trailer_soc is None else trailer_soc * ctx.fridge.trailer_usable_kwh,
                    None, None, min_soc,
                )
            min_soc = min(min_soc, soc)
            if soc < ctx.vehicle.soc_min - 1e-9:
                return ContinuousReplayReport(
                    False, "tractor_soc_floor_charge", discrete_cost, discrete_t, discrete_E_truck,
                    t_s, soc * usable,
                    None if trailer_soc is None else trailer_soc * ctx.fridge.trailer_usable_kwh,
                    None, None, min_soc,
                )
            if trailer_soc is not None and trailer_soc < ctx.fridge.trailer_soc_min - 1e-9:
                return ContinuousReplayReport(
                    False, "trailer_soc_floor_charge", discrete_cost, discrete_t, discrete_E_truck,
                    t_s, soc * usable, trailer_soc * ctx.fridge.trailer_usable_kwh,
                    None, None, min_soc,
                )
        elif typ == "WAIT":
            steps = int(act["steps"])
            dt = steps * ctx.time_step_min * 60.0
            mid = next(iter(ctx.weather.points.values()))
            e_aux = ctx.vehicle.P_aux_w * dt
            e_ref = refrigeration_energy_j(
                duration_s=dt,
                T_amb_c=mid.T_mean_c,
                params=ctx.fridge,
                refrigeration_on=ctx.refrigeration_on,
            )
            if ctx.power_source == "A":
                soc = (soc * usable - (e_aux + e_ref) / 3.6e6) / usable
            else:
                soc = (soc * usable - e_aux / 3.6e6) / usable
                if trailer_soc is not None and ctx.refrigeration_on:
                    trailer_soc = (
                        trailer_soc * ctx.fridge.trailer_usable_kwh - e_ref / 3.6e6
                    ) / ctx.fridge.trailer_usable_kwh
            t_s += dt
            min_soc = min(min_soc, soc)
        else:
            return ContinuousReplayReport(
                False, f"unknown_action:{typ}", discrete_cost, discrete_t, discrete_E_truck,
                t_s, None, None, None, None, min_soc,
            )

    if current_node != inst.destination:
        return ContinuousReplayReport(
            False,
            f"not_at_destination:{current_node}!={inst.destination}",
            discrete_cost,
            discrete_t,
            discrete_E_truck,
            t_s,
            soc * usable,
            None if trailer_soc is None else trailer_soc * ctx.fridge.trailer_usable_kwh,
            None,
            None,
            min_soc,
        )
    E_cont = soc * usable
    El_cont = None if trailer_soc is None else trailer_soc * ctx.fridge.trailer_usable_kwh
    dE = None if discrete_E_truck is None else E_cont - float(discrete_E_truck)
    dT = None if discrete_t is None else t_s - discrete_t * ctx.time_step_min * 60.0
    return ContinuousReplayReport(
        True,
        None,
        discrete_cost,
        discrete_t,
        discrete_E_truck,
        t_s,
        E_cont,
        El_cont,
        dE,
        dT,
        min_soc,
    )
