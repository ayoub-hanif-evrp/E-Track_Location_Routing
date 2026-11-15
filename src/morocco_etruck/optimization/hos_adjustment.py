"""Chronological Moroccan HOS rest adjustment on physical action traces.

Policy screen (décret 2-10-314, arts. 17–19, as commonly summarized):
- After 4.5 h continuous driving: uninterrupted pause ≥ 45 min (art. 18),
  or split pauses of ≥ 15 min each that together satisfy art. 18 (art. 19).
- Daily driving between mandatory daily rests ≤ 9 h (art. 17).
- Daily rest ≥ 12 h in each 24 h period (art. 16) — screened when journey
  duration approaches that horizon.

This module extends verified CHARGE/WAIT stops that occur **before** the
continuous-driving limit. It does not invent inaccessible stops.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, dataclass
from typing import Any

from morocco_etruck.energy.refrigeration import refrigeration_energy_j
from morocco_etruck.optimization.operational_schedule import (
    MAX_CONTINUOUS_DRIVING_MIN,
    REQUIRED_BREAK_MIN,
    _action_type,
    validate_schedule_from_replay_trace,
)

DAILY_DRIVING_MAX_MIN = 9.0 * 60.0  # art. 17
MIN_SPLIT_BREAK_MIN = 15.0  # art. 19


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
) -> HosPlanResult:
    """
    Walk the physical timeline. Before continuous driving would exceed the
    limit, extend the most recent verified stop (if any) to a qualifying break.
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
    if not candidates:
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
                f"n_stops={len(stops)};need_earlier_site_or_route_change"
            ),
        )

    s0, s1, arr_cum, blk, ch, node = candidates[-1]
    pad_min = max(0.0, required_break_min - blk)
    adj = deepcopy(action_trace)
    insert_at = s1
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
                "hos_extends_stop": True,
            },
        )

    check = validate_schedule_from_replay_trace(
        adj,
        max_continuous_driving_min=max_continuous_driving_min,
        required_break_min=required_break_min,
    )
    dt_s = pad_min * 60.0
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
    ok = bool(check.ok) and daily_ok
    return HosPlanResult(
        needed=pad_min > 1e-9 or not base.ok,
        ok=ok,
        adjusted_trace=adj,
        pad_location=node,
        pad_duration_min=pad_min,
        pad_after_trace_index=s1 - 1,
        overlaps_charge=ch > 1e-9,
        aux_energy_kwh=e_aux,
        refrig_energy_kwh=e_ref,
        total_stationary_energy_kwh=e_aux + e_ref,
        continuous_driving_max_min=check.continuous_driving_max_min,
        daily_driving_min=daily_drive,
        daily_driving_ok=daily_ok,
        notes=(
            f"extend_stop={node};arrival_cum_drive_min={arr_cum:.1f};"
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
    """Insert WAIT steps after the CHARGE (or existing WAIT) at station_node."""
    if pad_duration_min <= 1e-9:
        return list(actions)
    steps = max(1, int(round(pad_duration_min / float(time_step_min))))
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
            out.append(
                {
                    "type": "WAIT",
                    "node": station_node,
                    "steps": steps,
                    "hos_pad": True,
                }
            )
            inserted = True
            i = j
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
