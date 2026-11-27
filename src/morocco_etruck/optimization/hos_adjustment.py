"""Chronological Moroccan HOS rest adjustment on physical action traces.

Policy screen (décret 2-10-314, arts. 17–19, as commonly summarized):
- After 4.5 h continuous driving: uninterrupted pause ≥ 45 min (art. 18),
  or split pauses of ≥ 15 min each that together satisfy art. 18 (art. 19).
- Daily driving between mandatory daily rests ≤ 9 h (art. 17).
- Daily rest ≥ 12 h in each 24 h period (art. 16) — screened when journey
  duration approaches that horizon.

This module:
1. Extends verified CHARGE/WAIT stops that occur **before** the continuous-
   driving limit; and
2. If the energy-optimal itinerary skips charging, inserts an independent
   qualifying WAIT at a topology-verified rest node the route already
   traverses (ADM/service-area graph node), with aux + refrigeration energy
   charged during the break.

It does not invent inaccessible stops or redesign routing.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, dataclass
from typing import Any, Collection

from morocco_etruck.energy.refrigeration import refrigeration_energy_j
from morocco_etruck.optimization.operational_schedule import (
    MAX_CONTINUOUS_DRIVING_MIN,
    REQUIRED_BREAK_MIN,
    _action_type,
    validate_schedule_from_replay_trace,
)

DAILY_DRIVING_MAX_MIN = 9.0 * 60.0  # art. 17
MIN_SPLIT_BREAK_MIN = 15.0  # art. 19

# Path A single-duty scope labels (no Art.16 overnight daily-rest reset).
DUTY_SINGLE = "SINGLE_DUTY"
DUTY_MULTI_DAY_OUT_OF_SCOPE = "MULTI_DAY_OUT_OF_SCOPE"
DUTY_NOT_EVALUATED = "NOT_EVALUATED"


def classify_duty_scope(
    *,
    daily_driving_min: float | None,
    daily_driving_ok: bool | None = None,
    journey_min: float | None = None,
    daily_rest_horizon_min: float = 24.0 * 60.0,
) -> str:
    """Classify itinerary as single-duty vs multi-day out of scope.

    Art.17 daily driving > 9 h, or journey duration approaching a 24 h daily-rest
    horizon, means overnight Art.16 rest would be required. Path A does not
    implement that reset — such cases are excluded from ``served`` counts.

    ``daily_driving_ok is None`` means HOS was not audited (e.g. ops solver
    returned no actions). That is *not* evidence of a daily-driving violation.
    """
    if daily_driving_ok is None and daily_driving_min is None and journey_min is None:
        return DUTY_NOT_EVALUATED
    if daily_driving_ok is False:
        return DUTY_MULTI_DAY_OUT_OF_SCOPE
    if daily_driving_min is not None and float(daily_driving_min) > DAILY_DRIVING_MAX_MIN + 1e-9:
        return DUTY_MULTI_DAY_OUT_OF_SCOPE
    if journey_min is not None and float(journey_min) + 1e-9 >= daily_rest_horizon_min:
        return DUTY_MULTI_DAY_OUT_OF_SCOPE
    return DUTY_SINGLE


@dataclass
class HosPlanResult:
    needed: bool
    ok: bool
    adjusted_trace: list[dict[str, Any]]
    pad_location: str | None
    pad_duration_min: float
    pad_after_trace_index: int | None
    overlaps_charge: bool
    aux_energy_kwh: float
    refrig_energy_kwh: float
    total_stationary_energy_kwh: float
    continuous_driving_max_min: float
    daily_driving_min: float
    daily_driving_ok: bool
    notes: str = ""
    independent_rest: bool = False

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d.pop("adjusted_trace", None)
        return d


def _block_bounds(trace: list[dict[str, Any]], start: int) -> tuple[int, int, float, float]:
    """Return (start, end_exclusive, total_min, charge_min) for a stationary block."""
    j = start
    total = 0.0
    charge = 0.0
    while j < len(trace) and _action_type(trace[j]) in ("CHARGE", "WAIT"):
        dt = float(trace[j].get("dt_s") or 0.0) / 60.0
        total += dt
        if _action_type(trace[j]) == "CHARGE":
            charge += dt
        j += 1
    return start, j, total, charge


def _stationary_energy_kwh(
    *,
    pad_min: float,
    P_aux_w: float,
    T_amb_c: float,
    fridge_params: Any | None,
    refrigeration_on: bool,
) -> tuple[float, float]:
    dt_s = float(pad_min) * 60.0
    e_aux = (float(P_aux_w) * dt_s) / 3.6e6
    e_ref = 0.0
    if fridge_params is not None and refrigeration_on and dt_s > 0:
        e_ref = (
            refrigeration_energy_j(
                duration_s=dt_s,
                T_amb_c=float(T_amb_c),
                params=fridge_params,
                refrigeration_on=True,
            )
            / 3.6e6
        )
    return e_aux, e_ref


def _pass_through_rest_candidates(
    action_trace: list[dict[str, Any]],
    *,
    verified_rest_nodes: Collection[str],
    max_continuous_driving_min: float,
) -> list[tuple[int, float, str]]:
    """DRIVE arrivals at verified rest nodes before the continuous-driving limit.

    Returns list of (trace_index_of_arriving_DRIVE, cum_drive_min_at_arrival, node).
    """
    allowed = {str(x) for x in verified_rest_nodes}
    out: list[tuple[int, float, str]] = []
    cum = 0.0
    for i, act in enumerate(action_trace):
        if _action_type(act) != "DRIVE":
            continue
        cum += float(act.get("dt_s") or 0.0) / 60.0
        v = act.get("v") or act.get("to_node") or act.get("node")
        if v is None:
            continue
        node = str(v)
        if node in allowed and cum <= max_continuous_driving_min + 1e-9:
            out.append((i, cum, node))
    return out


def propose_chronological_hos_plan(
    action_trace: list[dict[str, Any]],
    *,
    P_aux_w: float = 2500.0,
    T_amb_c: float = 20.0,
    fridge_params: Any | None = None,
    refrigeration_on: bool = True,
    max_continuous_driving_min: float = MAX_CONTINUOUS_DRIVING_MIN,
    required_break_min: float = REQUIRED_BREAK_MIN,
    allow_art19_splits: bool = True,
    verified_rest_nodes: Collection[str] | None = None,
) -> HosPlanResult:
    """
    Walk the physical timeline. Before continuous driving would exceed the
    limit, extend the most recent verified stop (if any) to a qualifying break.
    If the itinerary has no charge/wait stop before the limit, insert an
    independent rest at a verified rest node the route already traverses.
    """
    base = validate_schedule_from_replay_trace(
        action_trace,
        max_continuous_driving_min=max_continuous_driving_min,
        required_break_min=required_break_min,
    )
    daily_drive = sum(
        float(a.get("dt_s") or 0.0) / 60.0
        for a in action_trace
        if _action_type(a) == "DRIVE"
    )
    daily_ok = daily_drive <= DAILY_DRIVING_MAX_MIN + 1e-9

    if base.ok and daily_ok:
        return HosPlanResult(
            needed=False,
            ok=True,
            adjusted_trace=list(action_trace),
            pad_location=None,
            pad_duration_min=0.0,
            pad_after_trace_index=None,
            overlaps_charge=False,
            aux_energy_kwh=0.0,
            refrig_energy_kwh=0.0,
            total_stationary_energy_kwh=0.0,
            continuous_driving_max_min=base.continuous_driving_max_min,
            daily_driving_min=daily_drive,
            daily_driving_ok=daily_ok,
            notes="already_schedule_valid",
        )

    # Collect stops: (trace_index_start, end_excl, cum_drive_at_arrival, block_min, charge_min, node)
    stops: list[tuple[int, int, float, float, float, str]] = []
    cum = 0.0
    i = 0
    n = len(action_trace)
    while i < n:
        typ = _action_type(action_trace[i])
        if typ == "DRIVE":
            cum += float(action_trace[i].get("dt_s") or 0.0) / 60.0
            i += 1
            continue
        if typ in ("CHARGE", "WAIT"):
            s0, s1, blk, ch = _block_bounds(action_trace, i)
            node = (
                action_trace[s0].get("node")
                or action_trace[s0].get("site")
                or f"stop_{s0}"
            )
            stops.append((s0, s1, cum, blk, ch, str(node)))
            i = s1
            continue
        i += 1

    # Prefer the latest stop with arrival cum_drive ≤ continuous limit.
    _ = allow_art19_splits  # reserved for explicit 15+30 split accounting
    candidates = [
        s for s in stops if s[2] <= max_continuous_driving_min + 1e-9
    ]
    independent = False
    if candidates:
        s0, s1, arr_cum, blk, ch, node = candidates[-1]
        pad_min = max(0.0, required_break_min - blk)
        insert_at = s1
        extends_existing = True
    else:
        # Independent rest at a verified on-path service-area / charger node.
        pass_cands = _pass_through_rest_candidates(
            action_trace,
            verified_rest_nodes=verified_rest_nodes or (),
            max_continuous_driving_min=max_continuous_driving_min,
        )
        if not pass_cands:
            return HosPlanResult(
                needed=True,
                ok=False,
                adjusted_trace=list(action_trace),
                pad_location=None,
                pad_duration_min=0.0,
                pad_after_trace_index=None,
                overlaps_charge=False,
                aux_energy_kwh=0.0,
                refrig_energy_kwh=0.0,
                total_stationary_energy_kwh=0.0,
                continuous_driving_max_min=base.continuous_driving_max_min,
                daily_driving_min=daily_drive,
                daily_driving_ok=daily_ok,
                notes=(
                    "no_verified_stop_before_continuous_limit;"
                    f"n_stops={len(stops)};"
                    f"n_pass_through={0 if not verified_rest_nodes else 'checked'};"
                    "need_earlier_site_or_route_change"
                ),
            )
        drive_idx, arr_cum, node = pass_cands[-1]
        pad_min = float(required_break_min)
        insert_at = drive_idx + 1
        blk = 0.0
        ch = 0.0
        extends_existing = False
        independent = True

    adj = deepcopy(action_trace)
    if pad_min > 1e-9:
        adj.insert(
            insert_at,
            {
                "action_type": "WAIT",
                "type": "WAIT",
                "dt_s": pad_min * 60.0,
                "steps": max(1, int(round(pad_min / 5.0))),
                "node": node,
                "hos_pad": True,
                "hos_extends_stop": extends_existing,
                "hos_independent_rest": independent,
            },
        )

    check = validate_schedule_from_replay_trace(
        adj,
        max_continuous_driving_min=max_continuous_driving_min,
        required_break_min=required_break_min,
    )
    e_aux, e_ref = _stationary_energy_kwh(
        pad_min=pad_min,
        P_aux_w=P_aux_w,
        T_amb_c=T_amb_c,
        fridge_params=fridge_params,
        refrigeration_on=refrigeration_on,
    )
    ok = bool(check.ok) and daily_ok
    mode = "independent_rest" if independent else "extend_stop"
    return HosPlanResult(
        needed=pad_min > 1e-9 or not base.ok,
        ok=ok,
        adjusted_trace=adj,
        pad_location=node,
        pad_duration_min=pad_min,
        pad_after_trace_index=insert_at - 1,
        overlaps_charge=ch > 1e-9,
        aux_energy_kwh=e_aux,
        refrig_energy_kwh=e_ref,
        total_stationary_energy_kwh=e_aux + e_ref,
        continuous_driving_max_min=check.continuous_driving_max_min,
        daily_driving_min=daily_drive,
        daily_driving_ok=daily_ok,
        independent_rest=independent,
        notes=(
            f"{mode}={node};arrival_cum_drive_min={arr_cum:.1f};"
            f"existing_block_min={blk:.1f};pad_min={pad_min:.1f};"
            f"schedule_ok_after={check.ok};violation={check.violation}"
        ),
    )


def inject_wait_into_solver_actions(
    actions: list[dict[str, Any]],
    *,
    station_node: str,
    pad_duration_min: float,
    time_step_min: int = 5,
) -> list[dict[str, Any]]:
    """Insert WAIT at station_node after CHARGE/WAIT, or after DRIVE arrival."""
    if pad_duration_min <= 1e-9:
        return list(actions)
    steps = max(1, int(round(pad_duration_min / float(time_step_min))))
    wait_act = {
        "type": "WAIT",
        "node": station_node,
        "steps": steps,
        "hos_pad": True,
    }
    out: list[dict[str, Any]] = []
    inserted = False
    i = 0
    while i < len(actions):
        a = dict(actions[i])
        out.append(a)
        typ = str(a.get("type") or "")
        node = str(a.get("node") or a.get("site") or "")
        if not inserted and typ in ("CHARGE", "WAIT") and node == str(station_node):
            # Consume following WAIT/CHARGE at same node then insert pad once.
            j = i + 1
            while j < len(actions) and str(actions[j].get("type") or "") in (
                "CHARGE",
                "WAIT",
            ):
                n2 = str(actions[j].get("node") or actions[j].get("site") or "")
                if n2 != str(station_node):
                    break
                out.append(dict(actions[j]))
                j += 1
            out.append(dict(wait_act))
            inserted = True
            i = j
            continue
        # Independent rest: insert after DRIVE that arrives at the station node.
        if not inserted and typ == "DRIVE" and str(a.get("v") or "") == str(station_node):
            out.append(dict(wait_act))
            out[-1]["hos_independent_rest"] = True
            inserted = True
            i += 1
            continue
        i += 1
    if not inserted:
        # Fallback: append at end (may not cure HOS — caller must revalidate).
        out.append(
            {
                "type": "WAIT",
                "node": station_node,
                "steps": steps,
                "hos_pad": True,
                "hos_fallback_end": True,
            }
        )
    return out
