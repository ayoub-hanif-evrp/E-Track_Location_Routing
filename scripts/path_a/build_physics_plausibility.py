"""Gate 1: physics plausibility reference table (not new physics / not field validation).

Writes:
  results/validation/path_a/physics_plausibility.csv
  results/validation/path_a/physics_plausibility_notes.md
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "results" / "validation" / "path_a"


def main() -> None:
    import sys

    sys.path.insert(0, str(ROOT / "src"))
    from morocco_etruck.energy.refrigeration import (
        load_refrigeration,
        tru_electrical_power_w,
    )
    from morocco_etruck.energy.vehicle import load_vehicle

    OUT.mkdir(parents=True, exist_ok=True)
    vehicle = load_vehicle(ROOT / "configs" / "vehicles" / "eactros_600.yaml")
    # Headline commodity fridge (firm-ripe tomato UNECE mid-band), not +2 °C approx.
    fridge = load_refrigeration(ROOT / "configs" / "energy" / "pass2_tomato_firm_ripe.yaml")
    approx = load_refrigeration(ROOT / "configs" / "energy" / "refrigeration_approx.yaml")

    # Steady cruise traction estimate at 80 km/h on flat road (order-of-magnitude).
    v_mps = 80.0 / 3.6
    rho = float(getattr(vehicle, "air_density_default_kg_m3", 1.225) or 1.225)
    g = float(getattr(vehicle, "gravity_m_s2", 9.80665) or 9.80665)
    # Representative refrigerated combo mass (tractor + trailer + mid payload).
    mass_kg = float(vehicle.unladen_tractor_kg) + float(vehicle.unladen_trailer_kg) + 15000.0
    F_aero = 0.5 * rho * float(vehicle.CdA_m2) * (v_mps**2)
    F_roll = float(vehicle.Crr) * mass_kg * g
    P_wheel_w = (F_aero + F_roll) * v_mps
    P_batt_w = P_wheel_w / max(1e-9, float(vehicle.eta_prop))
    kwh_per_km_traction = (P_batt_w / 1000.0) / 80.0  # kW / (km/h) = kWh/km

    # Published eActros long-haul refs (different duty cycles — caveat in notes).
    ref_lo, ref_hi = 1.11, 1.14

    ambients = [15.0, 25.0, 35.0]
    rows: list[dict] = []
    rows.append(
        {
            "check_id": "traction_flat_80kmh_15t",
            "quantity": "traction_kWh_per_km",
            "value": round(kwh_per_km_traction, 4),
            "unit": "kWh/km",
            "assumptions": (
                f"flat; v=80km/h; CdA={vehicle.CdA_m2}; Crr={vehicle.Crr}; "
                f"mass={mass_kg:.0f}kg; eta_prop={vehicle.eta_prop}"
            ),
            "reference": f"eActros long-haul literature band ~{ref_lo}–{ref_hi} kWh/km",
            "plausible": bool(0.7 <= kwh_per_km_traction <= 1.8),
            "caveat": "model cruise vs published mixed long-haul duty cycles; not field validation",
        }
    )
    rows.append(
        {
            "check_id": "aux_cabin",
            "quantity": "P_aux_w",
            "value": float(vehicle.P_aux_w),
            "unit": "W",
            "assumptions": "constant cabin/electronics draw from vehicle yaml",
            "reference": "literature cabin aux 1–4 kW",
            "plausible": bool(1000.0 <= float(vehicle.P_aux_w) <= 4000.0),
            "caveat": "assumed research parameter",
        }
    )
    for t_amb in ambients:
        p_w = tru_electrical_power_w(t_amb, fridge)
        wh_per_h = p_w  # W * 1 h = Wh
        rows.append(
            {
                "check_id": f"tru_amb_{int(t_amb)}C",
                "quantity": "tru_electrical_power",
                "value": round(p_w, 1),
                "unit": "W",
                "assumptions": (
                    f"tomato setpoint={fridge.setpoint_c}C (UNECE 8–10); "
                    f"UA={fridge.UA_w_per_k} W/K; "
                    f"infiltration={fridge.infiltration_w} W; ambient={t_amb}C; "
                    "applied on DRIVE/CHARGE/WAIT when refrigeration_on; "
                    f"legacy_approx_2C_tru_W={tru_electrical_power_w(t_amb, approx):.1f}"
                ),
                "reference": "UNECE ECE/TRADE/470 tomato guidance + refrigerated EVRP OOM",
                "plausible": bool(0.0 <= p_w <= 8000.0),
                "caveat": "engineering UA–COP model; not Bank-calibrated; Wh = P*dt on stationary+drive",
            }
        )
        rows.append(
            {
                "check_id": f"tru_wh_per_h_amb_{int(t_amb)}C",
                "quantity": "tru_Wh_per_hour",
                "value": round(wh_per_h, 1),
                "unit": "Wh/h",
                "assumptions": f"same as tru_amb_{int(t_amb)}C",
                "reference": "order-of-magnitude refrigerated trailer draw",
                "plausible": bool(0.0 <= wh_per_h <= 8000.0),
                "caveat": "continuous accounting; door openings not modeled",
            }
        )

    # Combined specific energy at 25 C ambient (traction + aux + TRU at cruise).
    p_tru_25 = tru_electrical_power_w(25.0, fridge)
    kwh_per_km_total = kwh_per_km_traction + (float(vehicle.P_aux_w) + p_tru_25) / 1000.0 / 80.0
    rows.append(
        {
            "check_id": "total_flat_80kmh_15t_25C",
            "quantity": "total_kWh_per_km",
            "value": round(kwh_per_km_total, 4),
            "unit": "kWh/km",
            "assumptions": "traction + aux + TRU at 25C ambient, flat 80 km/h",
            "reference": f"traction band {ref_lo}–{ref_hi}; refrigerated add-on expected",
            "plausible": bool(0.8 <= kwh_per_km_total <= 2.2),
            "caveat": "scenario estimate only; DEM/wind/grade change corridor macros",
        }
    )

    out_csv = OUT / "physics_plausibility.csv"
    pd.DataFrame(rows).to_csv(out_csv, index=False)

    notes = OUT / "physics_plausibility_notes.md"
    notes.write_text(
        "\n".join(
            [
                "# Physics plausibility (Path A Gate 1)",
                "",
                "Reference-check only — **not** field validation of the eActros pack or TRU.",
                "",
                f"- Flat-cruise traction estimate: **{kwh_per_km_traction:.3f} kWh/km** "
                f"(literature long-haul band ~{ref_lo}–{ref_hi} kWh/km; different duty cycles).",
                f"- Aux: **{vehicle.P_aux_w:.0f} W** (assumed).",
                f"- Refrigeration setpoint **{fridge.setpoint_c} °C**, UA **{fridge.UA_w_per_k} W/K**;",
                "  TRU electrical power from UA–COP model on DRIVE/CHARGE/WAIT when refrigeration is on.",
                "- Sensitivity variants that change CdA / aux / weather must **re-bake DRIVE tables**",
                "  (see `scripts/run_remaining_p6_extras.py`).",
                "",
                f"Table: `{out_csv.relative_to(ROOT).as_posix()}`",
                "",
            ]
        ),
        encoding="utf-8",
    )
    print(f"wrote {out_csv}")
    print(f"wrote {notes}")
    print(f"traction_kWh/km={kwh_per_km_traction:.4f} total@25C={kwh_per_km_total:.4f}")


if __name__ == "__main__":
    main()
