"""Independent operational schedule validator for solved action sequences.

Moroccan professional-driver working-time screen (policy / decree family):
a qualifying break of at least 45 minutes after 4.5 hours of continuous driving.

This module does **not** re-optimize routes. Prefer physical continuous-replay
``dt_s`` times over rounded discrete routing steps when a replay trace is available.
Charging time counts toward a qualifying break only when the driver can take an
uninterrupted break at a suitable stop.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

# Policy screen — not a manufacturer requirement.
MAX_CONTINUOUS_DRIVING_MIN = 4.5 * 60.0  # 270 min
REQUIRED_BREAK_MIN = 45.0


@dataclass
class OperationalScheduleResult:
    ok: bool
    driving_min: float
    charging_min: float
    wait_min: float
    continuous_driving_max_min: float
    mandatory_rest_required_min: float
    stationary_break_min: float
    charging_rest_overlap_min: float
    extra_rest_beyond_charge_min: float
    total_journey_min: float
    total_realistic_journey_min: float
    n_drive_actions: int
    n_charge_actions: int
    n_wait_actions: int
    n_required_breaks: int
    violation: str | None = None
    notes: str = ""
    time_basis: str = "discrete_steps"
    discrete_driving_min: float | None = None
    physical_vs_discrete_drive_delta_min: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _action_type(act: dict[str, Any]) -> str:
    """Accept solver actions (``type``) or continuous-replay traces (``action_type``)."""
    return str(act.get("type") or act.get("action_type") or "")


def _dt_min_discrete(act: dict[str, Any], *, time_step_min: int) -> float:
    typ = _action_type(act)
    if typ == "DRIVE":
        steps = int(act.get("dt_steps") or 0)
    elif typ in ("CHARGE", "WAIT"):
        steps = int(act.get("steps") or 0)
    else:
        steps = 0
    return float(steps) * float(time_step_min)


def _dt_min_physical(act: dict[str, Any], *, time_step_min: int) -> float:
    """Prefer continuous-replay ``dt_s``; fall back to discrete steps."""
    if act.get("dt_s") is not None:
        return float(act["dt_s"]) / 60.0
    return _dt_min_discrete(act, time_step_min=time_step_min)


def validate_operational_schedule(
    actions: list[dict[str, Any]],
    *,
    time_step_min: int = 5,
    max_continuous_driving_min: float = MAX_CONTINUOUS_DRIVING_MIN,
    required_break_min: float = REQUIRED_BREAK_MIN,
    use_physical_times: bool = False,
) -> OperationalScheduleResult:
    """
    Walk solved actions and check continuous-driving / break policy.

    When ``use_physical_times=True``, each action should carry ``dt_s`` from
    continuous physics replay (authoritative). Discrete step times are still
    computed for comparison diagnostics.
    """
    dt_fn = _dt_min_physical if use_physical_times else _dt_min_discrete
    driving = 0.0
    charging = 0.0
    waiting = 0.0
    driving_disc = 0.0
    cont = 0.0
    cont_max = 0.0
    n_drive = n_charge = n_wait = 0
    n_breaks = 0
    stationary_break = 0.0
    charge_rest_overlap = 0.0
    extra_rest = 0.0
    violation: str | None = None
    n_physical = sum(1 for a in actions if a.get("dt_s") is not None)

    i = 0
    n = len(actions)
    while i < n:
        act = actions[i]
        typ = _action_type(act)
        if typ in ("START",):
            i += 1
            continue
        if typ == "DRIVE":
            dt = dt_fn(act, time_step_min=time_step_min)
            driving += dt
            driving_disc += _dt_min_discrete(act, time_step_min=time_step_min)
            cont += dt
            cont_max = max(cont_max, cont)
            n_drive += 1
            if cont > max_continuous_driving_min + 1e-9 and violation is None:
                violation = (
                    f"continuous_driving_exceeded:{cont:.1f}min>"
                    f"{max_continuous_driving_min:.1f}min"
                )
                extra_rest += required_break_min
                n_breaks += 1
            i += 1
            continue
        if typ in ("CHARGE", "WAIT"):
            block_charge = 0.0
            block_wait = 0.0
            while i < n and _action_type(actions[i]) in ("CHARGE", "WAIT"):
                a2 = actions[i]
                t2 = _action_type(a2)
                dt2 = dt_fn(a2, time_step_min=time_step_min)
                if t2 == "CHARGE":
                    block_charge += dt2
                    n_charge += 1
                else:
                    block_wait += dt2
                    n_wait += 1
                i += 1
            charging += block_charge
            waiting += block_wait
            block_total = block_charge + block_wait
            hit_limit = cont + 1e-9 >= max_continuous_driving_min
            qualifying = block_total + 1e-9 >= required_break_min
            if qualifying:
                n_breaks += 1
                stationary_break += block_total
                charge_rest_overlap += min(block_charge, required_break_min)
                cont = 0.0
            elif hit_limit:
                pad = max(0.0, required_break_min - block_total)
                extra_rest += pad
                charge_rest_overlap += min(block_charge, required_break_min)
                stationary_break += block_total
                n_breaks += 1
                cont = 0.0
                if violation is None and pad > 1e-9:
                    violation = (
                        f"break_too_short_needs_pad:{block_total:.1f}min"
                        f"<{required_break_min:.1f}min"
                    )
            continue
        i += 1

    implied_breaks = int(driving // max_continuous_driving_min)
    mandatory_rest = float(implied_breaks) * required_break_min
    total_journey = driving + charging + waiting
    realistic = total_journey + extra_rest
    basis = "physical_dt_s" if use_physical_times else "discrete_steps"
    if use_physical_times and n_physical == 0:
        basis = "discrete_steps_fallback_no_dt_s"

    return OperationalScheduleResult(
        ok=violation is None,
        driving_min=driving,
        charging_min=charging,
        wait_min=waiting,
        continuous_driving_max_min=cont_max,
        mandatory_rest_required_min=mandatory_rest,
        stationary_break_min=stationary_break,
        charging_rest_overlap_min=charge_rest_overlap,
        extra_rest_beyond_charge_min=extra_rest,
        total_journey_min=total_journey,
        total_realistic_journey_min=realistic,
        n_drive_actions=n_drive,
        n_charge_actions=n_charge,
        n_wait_actions=n_wait,
        n_required_breaks=max(n_breaks, implied_breaks),
        violation=violation,
        time_basis=basis,
        discrete_driving_min=driving_disc if use_physical_times else None,
        physical_vs_discrete_drive_delta_min=(
            (driving - driving_disc) if use_physical_times else None
        ),
        notes=(
            f"policy=45min_after_4.5h_driving;time_basis={basis};"
            f"time_step_min={time_step_min};"
            f"implied_breaks_from_total_drive={implied_breaks};"
            f"n_actions_with_dt_s={n_physical}"
        ),
    )


def validate_schedule_from_replay_trace(
    action_trace: list[dict[str, Any]],
    *,
    max_continuous_driving_min: float = MAX_CONTINUOUS_DRIVING_MIN,
    required_break_min: float = REQUIRED_BREAK_MIN,
) -> OperationalScheduleResult:
    """Authoritative schedule check using continuous-replay action_trace ``dt_s``."""
    return validate_operational_schedule(
        action_trace,
        time_step_min=5,
        max_continuous_driving_min=max_continuous_driving_min,
        required_break_min=required_break_min,
        use_physical_times=True,
    )


@dataclass
class HosRestAdjustment:
    """Post-hoc executable rest pad proposal (does not re-optimize the route)."""

    needed: bool
    ok_after_pad: bool
    pad_location: str | None
    pad_after_action_index: int | None
    pad_duration_min: float
    pad_overlaps_existing_charge: bool
    charge_rest_overlap_min: float
    aux_energy_kwh: float
    refrig_energy_kwh: float
    total_stationary_energy_kwh: float
    arrival_soc_before: float | None
    arrival_soc_after_pad: float | None
    soc_still_feasible: bool | None
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def propose_hos_rest_adjustment(
    action_trace: list[dict[str, Any]],
    *,
    arrival_soc: float | None = None,
    soc_min: float = 0.10,
    P_aux_w: float = 1500.0,
    T_amb_c: float = 20.0,
    fridge_params: Any | None = None,
    refrigeration_on: bool = True,
    max_continuous_driving_min: float = MAX_CONTINUOUS_DRIVING_MIN,
    required_break_min: float = REQUIRED_BREAK_MIN,
) -> HosRestAdjustment:
    """
    If continuous driving exceeds the HOS screen, propose a WAIT pad at the first
    suitable stop (CHARGE/WAIT block) that can complete a qualifying break, or at
    the end of the trip if no earlier stop exists.

    Energy during the pad uses aux + refrigeration (source A, tractor battery).
    This is an executable schedule adjustment, not a route re-optimization.
    """
    from morocco_etruck.energy.refrigeration import refrigeration_energy_j

    base = validate_schedule_from_replay_trace(
        action_trace,
        max_continuous_driving_min=max_continuous_driving_min,
        required_break_min=required_break_min,
    )
    if base.ok:
        return HosRestAdjustment(
            needed=False,
            ok_after_pad=True,
            pad_location=None,
            pad_after_action_index=None,
            pad_duration_min=0.0,
            pad_overlaps_existing_charge=False,
            charge_rest_overlap_min=base.charging_rest_overlap_min,
            aux_energy_kwh=0.0,
            refrig_energy_kwh=0.0,
            total_stationary_energy_kwh=0.0,
            arrival_soc_before=arrival_soc,
            arrival_soc_after_pad=arrival_soc,
            soc_still_feasible=(
                None if arrival_soc is None else arrival_soc + 1e-9 >= soc_min
            ),
            notes="no_pad_needed;schedule_already_ok",
        )

    cont = 0.0
    pad_idx: int | None = None
    pad_loc: str | None = None
    pad_min = 0.0
    overlaps_charge = False
    charge_overlap = 0.0
    i = 0
    n = len(action_trace)
    while i < n:
        act = action_trace[i]
        typ = _action_type(act)
        if typ == "DRIVE":
            dt = float(act.get("dt_s") or 0.0) / 60.0
            cont += dt
            if cont > max_continuous_driving_min + 1e-9 and pad_idx is None:
                # Need a break ASAP — prefer next stationary block.
                j = i + 1
                while j < n and _action_type(action_trace[j]) == "DRIVE":
                    j += 1
                if j < n and _action_type(action_trace[j]) in ("CHARGE", "WAIT"):
                    block = 0.0
                    block_charge = 0.0
                    k = j
                    while k < n and _action_type(action_trace[k]) in ("CHARGE", "WAIT"):
                        dt2 = float(action_trace[k].get("dt_s") or 0.0) / 60.0
                        block += dt2
                        if _action_type(action_trace[k]) == "CHARGE":
                            block_charge += dt2
                        k += 1
                    pad_min = max(0.0, required_break_min - block)
                    pad_idx = k - 1
                    node = action_trace[j].get("node") or action_trace[j].get("site")
                    pad_loc = str(node) if node is not None else f"stop_after_drive_{i}"
                    overlaps_charge = block_charge > 1e-9
                    charge_overlap = min(block_charge, required_break_min)
                else:
                    # No stop ahead — pad after this drive (end-of-leg / destination).
                    pad_min = required_break_min
                    pad_idx = i
                    pad_loc = str(act.get("v") or act.get("arc_id") or f"after_drive_{i}")
                    overlaps_charge = False
                    charge_overlap = 0.0
            i += 1
            continue
        if typ in ("CHARGE", "WAIT"):
            block = 0.0
            while i < n and _action_type(action_trace[i]) in ("CHARGE", "WAIT"):
                block += float(action_trace[i].get("dt_s") or 0.0) / 60.0
                i += 1
            if block + 1e-9 >= required_break_min:
                cont = 0.0
            continue
        i += 1

    if pad_idx is None:
        pad_min = float(base.extra_rest_beyond_charge_min or required_break_min)
        pad_idx = max(0, n - 1)
        pad_loc = "trip_end_fallback"

    # If the first available stop occurs only after continuous driving already
    # exceeded the limit, a post-hoc WAIT there cannot cure the past violation
    # without an earlier site or route change.
    drive_before_first_stop = 0.0
    for act in action_trace:
        typ = _action_type(act)
        if typ == "DRIVE":
            drive_before_first_stop += float(act.get("dt_s") or 0.0) / 60.0
        elif typ in ("CHARGE", "WAIT"):
            break
    stop_too_late = drive_before_first_stop > max_continuous_driving_min + 1e-9

    dt_s = pad_min * 60.0
    e_aux = (float(P_aux_w) * dt_s) / 3.6e6
    e_ref = 0.0
    if fridge_params is not None and refrigeration_on and dt_s > 0:
        e_ref = refrigeration_energy_j(
            duration_s=dt_s,
            T_amb_c=float(T_amb_c),
            params=fridge_params,
            refrigeration_on=True,
        ) / 3.6e6
    e_tot = e_aux + e_ref

    adj = list(action_trace)
    insert_at = (pad_idx + 1) if pad_idx is not None else len(adj)
    if pad_min > 1e-9 and not stop_too_late:
        adj.insert(
            insert_at,
            {
                "action_type": "WAIT",
                "dt_s": dt_s,
                "node": pad_loc,
                "hos_pad": True,
            },
        )
    check = validate_schedule_from_replay_trace(
        adj,
        max_continuous_driving_min=max_continuous_driving_min,
        required_break_min=required_break_min,
    )
    ok_after = bool(check.ok) and not stop_too_late
    return HosRestAdjustment(
        needed=True,
        ok_after_pad=ok_after,
        pad_location=pad_loc,
        pad_after_action_index=pad_idx,
        pad_duration_min=pad_min,
        pad_overlaps_existing_charge=overlaps_charge,
        charge_rest_overlap_min=charge_overlap,
        aux_energy_kwh=e_aux,
        refrig_energy_kwh=e_ref,
        total_stationary_energy_kwh=e_tot,
        arrival_soc_before=arrival_soc,
        arrival_soc_after_pad=None,
        soc_still_feasible=None,
        notes=(
            f"pad_at={pad_loc};pad_min={pad_min:.1f};"
            f"stop_too_late={stop_too_late};"
            f"drive_before_first_stop_min={drive_before_first_stop:.1f};"
            f"schedule_ok_after={check.ok};violation_after={check.violation}"
        ),
    )


def propose_hos_rest_adjustment_with_usable(
    action_trace: list[dict[str, Any]],
    *,
    arrival_soc: float,
    usable_kwh: float,
    soc_min: float = 0.10,
    P_aux_w: float = 1500.0,
    T_amb_c: float = 20.0,
    fridge_params: Any | None = None,
    refrigeration_on: bool = True,
) -> HosRestAdjustment:
    """HOS pad proposal with tractor SOC impact using usable pack energy."""
    adj = propose_hos_rest_adjustment(
        action_trace,
        arrival_soc=arrival_soc,
        soc_min=soc_min,
        P_aux_w=P_aux_w,
        T_amb_c=T_amb_c,
        fridge_params=fridge_params,
        refrigeration_on=refrigeration_on,
    )
    if not adj.needed or adj.total_stationary_energy_kwh <= 0:
        soc_after = arrival_soc
    else:
        soc_after = float(arrival_soc) - float(adj.total_stationary_energy_kwh) / float(
            usable_kwh
        )
    return HosRestAdjustment(
        needed=adj.needed,
        ok_after_pad=adj.ok_after_pad,
        pad_location=adj.pad_location,
        pad_after_action_index=adj.pad_after_action_index,
        pad_duration_min=adj.pad_duration_min,
        pad_overlaps_existing_charge=adj.pad_overlaps_existing_charge,
        charge_rest_overlap_min=adj.charge_rest_overlap_min,
        aux_energy_kwh=adj.aux_energy_kwh,
        refrig_energy_kwh=adj.refrig_energy_kwh,
        total_stationary_energy_kwh=adj.total_stationary_energy_kwh,
        arrival_soc_before=arrival_soc,
        arrival_soc_after_pad=soc_after,
        soc_still_feasible=soc_after + 1e-9 >= float(soc_min),
        notes=adj.notes + f";usable_kwh={usable_kwh}",
    )
