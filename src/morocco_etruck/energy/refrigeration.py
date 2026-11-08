"""Approximate refrigeration (TRU) electrical load — engineering model, not Bank calibration."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import yaml

PowerSource = Literal["A", "B"]


@dataclass(frozen=True)
class RefrigerationParams:
    setpoint_c: float
    UA_w_per_k: float
    infiltration_w: float
    cop_at_delta_0: float
    cop_at_delta_40: float
    cop_min: float
    cop_max: float
    trailer_usable_kwh: float
    trailer_soc_initial: float
    trailer_soc_min: float
    raw: dict[str, Any]

    @property
    def trailer_usable_j(self) -> float:
        return self.trailer_usable_kwh * 3.6e6


def load_refrigeration(path: str | Path) -> RefrigerationParams:
    path = Path(path)
    with path.open(encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    cop = raw["cop"]
    b = raw["power_source"]["B"]
    return RefrigerationParams(
        setpoint_c=float(raw["setpoint_c"]),
        UA_w_per_k=float(raw["UA_w_per_k"]),
        infiltration_w=float(raw.get("infiltration_w", 0.0)),
        cop_at_delta_0=float(cop["cop_at_delta_0"]),
        cop_at_delta_40=float(cop["cop_at_delta_40"]),
        cop_min=float(cop["cop_min"]),
        cop_max=float(cop["cop_max"]),
        trailer_usable_kwh=float(b["trailer_usable_kwh"]),
        trailer_soc_initial=float(b.get("trailer_soc_initial", 1.0)),
        trailer_soc_min=float(b.get("trailer_soc_min", 0.10)),
        raw=raw,
    )


def cop_at_ambient(T_amb_c: float, params: RefrigerationParams) -> float:
    """Linear COP in ΔT = T_amb - T_set, clipped to [cop_min, cop_max]."""
    delta = T_amb_c - params.setpoint_c
    # Interpolate between delta=0 and delta=40
    if delta <= 0:
        cop = params.cop_at_delta_0
    else:
        t = min(delta, 40.0) / 40.0
        cop = params.cop_at_delta_0 + t * (params.cop_at_delta_40 - params.cop_at_delta_0)
    return max(params.cop_min, min(params.cop_max, cop))


def heat_gain_w(T_amb_c: float, params: RefrigerationParams) -> float:
    """Transmission heat gain plus optional infiltration; (T_amb - T_set)_+."""
    delta = T_amb_c - params.setpoint_c
    q_tx = params.UA_w_per_k * max(0.0, delta)
    return q_tx + max(0.0, params.infiltration_w)


def tru_electrical_power_w(T_amb_c: float, params: RefrigerationParams) -> float:
    q = heat_gain_w(T_amb_c, params)
    if q <= 0:
        return 0.0
    return q / cop_at_ambient(T_amb_c, params)


def refrigeration_energy_j(
    *,
    duration_s: float,
    T_amb_c: float,
    params: RefrigerationParams,
    refrigeration_on: bool,
) -> float:
    if not refrigeration_on:
        return 0.0
    if duration_s < 0:
        raise ValueError("duration_s must be non-negative")
    return tru_electrical_power_w(T_amb_c, params) * duration_s
