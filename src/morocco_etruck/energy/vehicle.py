"""Vehicle parameter loading (SI units)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True)
class VehicleParams:
    """eActros-class tractor parameters in SI units."""

    vehicle_id: str
    installed_kwh: float
    usable_kwh: float
    continuous_power_w: float
    peak_power_w: float
    peak_regen_power_w: float
    unladen_tractor_kg: float
    unladen_trailer_kg: float
    gcm_limit_kg: float
    CdA_m2: float
    Crr: float
    eta_prop: float
    eta_regen: float
    P_aux_w: float
    soc_initial: float
    soc_min: float
    soc_max: float
    cruise_mps: float
    gravity_m_s2: float
    air_density_default_kg_m3: float
    raw: dict[str, Any]

    @property
    def usable_j(self) -> float:
        return self.usable_kwh * 3.6e6


def load_vehicle(path: str | Path) -> VehicleParams:
    path = Path(path)
    with path.open(encoding="utf-8") as f:
        raw = yaml.safe_load(f)

    drive = raw["drive"]
    mass = raw["mass"]
    aero = raw["aero"]
    eff = raw["efficiency"]
    aux = raw["auxiliaries"]
    soc = raw["soc"]
    speed = raw["speed_policy"]
    batt = raw["battery"]

    cruise_mps = float(speed.get("cruise_mps", float(speed["cruise_kmh"]) / 3.6))

    return VehicleParams(
        vehicle_id=str(raw.get("vehicle_id", path.stem)),
        installed_kwh=float(batt["installed_kwh"]),
        usable_kwh=float(batt["usable_kwh"]),
        continuous_power_w=float(drive["continuous_power_kw"]) * 1000.0,
        peak_power_w=float(drive["peak_power_kw"]) * 1000.0,
        peak_regen_power_w=float(drive["peak_regen_power_kw"]) * 1000.0,
        unladen_tractor_kg=float(mass["unladen_tractor_kg"]),
        unladen_trailer_kg=float(mass["unladen_trailer_kg"]),
        gcm_limit_kg=float(mass["technically_permissible_combination_kg"]),
        CdA_m2=float(aero["CdA_m2"]),
        Crr=float(aero["Crr"]),
        eta_prop=float(eff["eta_prop"]),
        eta_regen=float(eff["eta_regen"]),
        P_aux_w=float(aux["P_aux_w"]),
        soc_initial=float(soc["soc_initial"]),
        soc_min=float(soc["soc_min"]),
        soc_max=float(soc["soc_max"]),
        cruise_mps=cruise_mps,
        gravity_m_s2=float(raw.get("gravity_m_s2", 9.80665)),
        air_density_default_kg_m3=float(raw.get("air_density_default_kg_m3", 1.225)),
        raw=raw,
    )


def mass_from_gcm(gcm_kg: float) -> float:
    """Total combination mass for longitudinal dynamics (kg)."""
    if gcm_kg <= 0:
        raise ValueError(f"gcm_kg must be positive, got {gcm_kg}")
    return float(gcm_kg)


def empty_combination_kg(vehicle: VehicleParams) -> float:
    """Assumed empty tractor + trailer curb mass (research assumption for trailer curb)."""
    return vehicle.unladen_tractor_kg + vehicle.unladen_trailer_kg


def cargo_payload_kg(gcm_kg: float, vehicle: VehicleParams) -> float:
    """Cargo payload = GCM − empty combination (may be validated via validate_gcm)."""
    return float(gcm_kg) - empty_combination_kg(vehicle)


def validate_gcm(gcm_kg: float, vehicle: VehicleParams) -> None:
    """
    Ensure gross combination mass is within physical research bounds.

    GCM must be ≥ assumed empty tractor+trailer and ≤ manufacturer GCM limit.
    """
    gcm = mass_from_gcm(gcm_kg)
    empty = empty_combination_kg(vehicle)
    if gcm + 1e-6 < empty:
        raise ValueError(
            f"GCM {gcm} kg is below assumed empty combination {empty} kg "
            f"(tractor {vehicle.unladen_tractor_kg} + trailer {vehicle.unladen_trailer_kg})"
        )
    if gcm > vehicle.gcm_limit_kg + 1e-6:
        raise ValueError(
            f"GCM {gcm} kg exceeds technically permissible combination "
            f"{vehicle.gcm_limit_kg} kg"
        )
