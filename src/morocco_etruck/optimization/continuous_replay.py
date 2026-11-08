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
    macros = {(m.u, m.v): m for m in ctx.macros}

    for act in actions:
        typ = act.get("type")
        if typ == "DRIVE":
            key = (act["u"], act["v"])
            macro = macros.get(key)
            if macro is None:
                return ContinuousReplayReport(
                    False, f"missing_macro:{key}", discrete_cost, discrete_t, discrete_E_truck,
                    t_s, None, None, None, None, min_soc,
                )
            ok, dt, soc, trailer_soc, reason = simulate_drive_from_soc(
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
            de = float(act["delta_e_kwh"])
            st = inst.stations[act["node"]]
            batt_kw = st.power_kw * st.eta
            dt = (de / batt_kw) * 3600.0 if batt_kw > 0 else 0.0
            mid = next(iter(ctx.weather.points.values()))
            e_aux_kwh = ctx.vehicle.P_aux_w * dt / 3.6e6
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
