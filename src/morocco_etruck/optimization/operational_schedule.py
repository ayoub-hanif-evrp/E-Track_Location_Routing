"""Independent operational schedule validator for solved action sequences.

Moroccan professional-driver working-time screen (policy / decree family):
a qualifying break of at least 45 minutes after 4.5 hours of continuous driving.

This module does **not** re-optimize routes. It audits an existing discrete
action plan and reports driving, charging, mandatory rest, and overlap.
Charging time counts toward a qualifying break only when the stop is at a
stationary location (CHARGE/WAIT) with uninterrupted duration ≥ required break.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
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

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _dt_min(act: dict[str, Any], *, time_step_min: int) -> float:
    typ = str(act.get("type") or "")
    if typ == "DRIVE":
        steps = int(act.get("dt_steps") or 0)
    elif typ in ("CHARGE", "WAIT"):
        steps = int(act.get("steps") or 0)
    else:
        steps = 0
    return float(steps) * float(time_step_min)


def validate_operational_schedule(
    actions: list[dict[str, Any]],
    *,
    time_step_min: int = 5,
    max_continuous_driving_min: float = MAX_CONTINUOUS_DRIVING_MIN,
    required_break_min: float = REQUIRED_BREAK_MIN,
) -> OperationalScheduleResult:
    """
    Walk solved actions and check continuous-driving / break policy.

    Qualifying break: uninterrupted CHARGE and/or WAIT block at a stop whose
    total stationary duration ≥ ``required_break_min``. Pure driving does not
    reset the continuous-driving clock.
    """
    driving = 0.0
    charging = 0.0
    waiting = 0.0
    cont = 0.0
    cont_max = 0.0
    n_drive = n_charge = n_wait = 0
    n_breaks = 0
    stationary_break = 0.0
    charge_rest_overlap = 0.0
    extra_rest = 0.0
    violation: str | None = None

    # Aggregate consecutive stationary actions into one stop block.
    i = 0
    n = len(actions)
    while i < n:
        act = actions[i]
        typ = str(act.get("type") or "")
        if typ in ("START",):
            i += 1
            continue
        if typ == "DRIVE":
            dt = _dt_min(act, time_step_min=time_step_min)
            driving += dt
            cont += dt
            cont_max = max(cont_max, cont)
            n_drive += 1
            if cont > max_continuous_driving_min + 1e-9 and violation is None:
                violation = (
                    f"continuous_driving_exceeded:{cont:.1f}min>"
                    f"{max_continuous_driving_min:.1f}min"
                )
                # Implied missing qualifying break at first exceedance.
                extra_rest += required_break_min
                n_breaks += 1
            i += 1
            continue
        if typ in ("CHARGE", "WAIT"):
            block_charge = 0.0
            block_wait = 0.0
            while i < n and str(actions[i].get("type") or "") in ("CHARGE", "WAIT"):
                a2 = actions[i]
                t2 = str(a2.get("type") or "")
                dt2 = _dt_min(a2, time_step_min=time_step_min)
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
                # Only uninterrupted stationary time at a suitable stop can overlap rest.
                charge_rest_overlap += min(block_charge, required_break_min)
                cont = 0.0
            elif hit_limit:
                # Stop too short to qualify — schedule needs an explicit rest pad.
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
            # else: short stop before continuous limit — does not reset the clock
            continue
        i += 1

    # How many mandatory breaks are implied by total driving (lower bound screen).
    implied_breaks = int(driving // max_continuous_driving_min)
    mandatory_rest = float(implied_breaks) * required_break_min

    total_journey = driving + charging + waiting
    realistic = total_journey + extra_rest

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
        notes=(
            f"policy=45min_after_4.5h_driving;"
            f"time_step_min={time_step_min};"
            f"implied_breaks_from_total_drive={implied_breaks}"
        ),
    )
