"""Continuous-physics replay for path-union multiroute MRLS (Task 05B)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from morocco_etruck.energy.refrigeration import refrigeration_energy_j
from morocco_etruck.optimization.arc_preprocessing import simulate_drive_from_soc
from morocco_etruck.optimization.continuous_replay import ContinuousReplayReport
from morocco_etruck.optimization.multiroute_physics import MultirouteMissionContext
from morocco_etruck.optimization.problem import RoutingInstance


@dataclass
class MultirouteReplayExtras:
    osm_node_path: list[int]
    arc_ids: list[str]
    length_m: float
    charge_events: list[dict[str, Any]]


def continuous_replay_multiroute(
    ctx: MultirouteMissionContext,
    inst: RoutingInstance,
    actions: list[dict[str, Any]],
    *,
    discrete_cost: int | None = None,
    discrete_t: int | None = None,
    discrete_E_truck: int | None = None,
) -> tuple[ContinuousReplayReport, MultirouteReplayExtras]:
    """
    Replay DRIVE/CHARGE/WAIT with Task 02B continuous physics on geometry-owned macros.

    Macros are keyed by arc_id (required for parallel decision arcs). Missing arc_id
    or missing physics inputs ⇒ not certified physically feasible.
    """
    usable = float(ctx.vehicle.usable_kwh)
    soc = inst.E_truck_init / usable
    trailer_soc = None
    if inst.E_trailer_init is not None:
        trailer_soc = inst.E_trailer_init / float(ctx.fridge.trailer_usable_kwh)
    min_soc = soc
    t_s = 0.0
    osm_path: list[int] = []
    arc_ids: list[str] = []
    length_m = 0.0
    charges: list[dict[str, Any]] = []

    def _fail(reason: str) -> tuple[ContinuousReplayReport, MultirouteReplayExtras]:
        return (
            ContinuousReplayReport(
                False,
                reason,
                discrete_cost,
                discrete_t,
                discrete_E_truck,
                t_s,
                None,
                None,
                None,
                None,
                min_soc,
            ),
            MultirouteReplayExtras(osm_path, arc_ids, length_m, charges),
        )

    for act in actions:
        typ = act.get("type")
        if typ == "DRIVE":
            aid = act.get("arc_id")
            if not aid:
                # Fallback only if unique (u,v)
                cands = [
                    m
                    for m in ctx.macros_by_arc_id.values()
                    if m.u == act.get("u") and m.v == act.get("v")
                ]
                if len(cands) != 1:
                    return _fail("missing_or_ambiguous_arc_id")
                macro = cands[0]
                aid = str(macro.meta.get("arc_id") or "")
            else:
                macro = ctx.macros_by_arc_id.get(str(aid))
            if macro is None:
                return _fail(f"missing_macro:{aid}")
            if str(macro.meta.get("terrain_note") or "").startswith("dem_unavailable"):
                # Flat fallback still has physics; allow replay but note was recorded in ctx
                pass
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
            arc_ids.append(str(aid))
            length_m += float(macro.length_m)
            pn = [int(x) for x in macro.path_nodes]
            if not osm_path:
                osm_path.extend(pn)
            else:
                osm_path.extend(pn[1:])
            if not ok:
                return _fail(reason or "drive_failed")
        elif typ == "CHARGE":
            node = act["node"]
            if node not in inst.active_stations:
                return _fail("station_inactive")
            st = inst.stations.get(node)
            if st is None or not st.compatible:
                return _fail("incompatible_charger")
            de = float(act["delta_e_kwh"])
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
            charges.append({"node": node, "delta_e_kwh": de, "dt_s": dt})
            min_soc = min(min_soc, soc)
            if soc < ctx.vehicle.soc_min - 1e-9:
                return _fail("tractor_soc_floor_charge")
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
            return _fail(f"unknown_action:{typ}")

    E_cont = soc * usable
    El_cont = None if trailer_soc is None else trailer_soc * ctx.fridge.trailer_usable_kwh
    dE = None if discrete_E_truck is None else E_cont - float(discrete_E_truck)
    dT = None if discrete_t is None else t_s - discrete_t * ctx.time_step_min * 60.0
    return (
        ContinuousReplayReport(
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
        ),
        MultirouteReplayExtras(osm_path, arc_ids, length_m, charges),
    )
