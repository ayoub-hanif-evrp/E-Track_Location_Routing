#!/usr/bin/env python3
"""P2–P4 finite journal campaign: provenance + refrigeration + heavier payload.

Reuses `run_remaining_p2_p3._eval_row` / `_prepare` for eActros; Volvo uses the same
prepare path with the Volvo vehicle YAML. Does not re-run the 224-cell panel.
"""
from __future__ import annotations

import copy
import json
import subprocess
import sys
import tempfile
from pathlib import Path

import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "scripts/final_evidence"))

import run_remaining_p2_p3 as p2  # noqa: E402
import run_stage_c_hos_national as stage_c  # noqa: E402
from run_final_operational_correction import evaluate_mission_operational  # noqa: E402
from morocco_etruck.energy.vehicle import load_vehicle  # noqa: E402
from morocco_etruck.energy.refrigeration import load_refrigeration  # noqa: E402

FE = ROOT / "results/final_evidence"
OUT = FE / "experiments/journal_p2_p4"
PHYS = FE / "experiments/physical_model"
TAB = FE / "tables/results"
TOMATO = ROOT / "configs/energy/pass2_tomato_firm_ripe.yaml"

REFRIG = [
    # (od, vehicle_key, payload, soc, installed, variant, opts)
    ("casa_marrakech", "eactros_600", 5300.0, 0.5, {"y_benguerir_ca"}, "refrig_off", {"refrigeration_on": False}),
    ("casa_marrakech", "eactros_600", 5300.0, 0.5, {"y_benguerir_ca"}, "tomato_9C_cool", {"refrigeration_on": True, "weather": "cool"}),
    ("casa_marrakech", "eactros_600", 5300.0, 0.5, {"y_benguerir_ca"}, "tomato_9C_hot", {"refrigeration_on": True, "weather": "hot"}),
    ("casa_marrakech", "eactros_600", 5300.0, 0.5, {"y_benguerir_ca"}, "tomato_UA_x1p5_hot", {"refrigeration_on": True, "weather": "hot", "ua_mult": 1.5}),
    ("casa_agadir", "eactros_600", 5300.0, 0.5, {"y_benguerir_ca"}, "refrig_off", {"refrigeration_on": False}),
    ("casa_agadir", "eactros_600", 5300.0, 0.5, {"y_benguerir_ca"}, "tomato_9C_cool", {"refrigeration_on": True, "weather": "cool"}),
    ("casa_agadir", "eactros_600", 5300.0, 0.5, {"y_benguerir_ca"}, "tomato_9C_hot", {"refrigeration_on": True, "weather": "hot"}),
    ("casa_agadir", "eactros_600", 5300.0, 0.5, {"y_benguerir_ca"}, "tomato_UA_x1p5_hot", {"refrigeration_on": True, "weather": "hot", "ua_mult": 1.5}),
    ("casa_marrakech", "volvo_475", 5300.0, 0.5, {"y_benguerir_ca"}, "refrig_off", {"refrigeration_on": False}),
    ("casa_marrakech", "volvo_475", 5300.0, 0.5, {"y_benguerir_ca"}, "tomato_9C_cool", {"refrigeration_on": True, "weather": "cool"}),
    ("casa_marrakech", "volvo_475", 5300.0, 0.5, {"y_benguerir_ca"}, "tomato_UA_x1p5_hot", {"refrigeration_on": True, "weather": "hot", "ua_mult": 1.5}),
]

PAYLOAD = [
    ("casa_marrakech", "eactros_600", 5300.0, 0.5, set(), "I0"),
    ("casa_marrakech", "eactros_600", 10000.0, 0.5, set(), "I0"),
    ("casa_marrakech", "eactros_600", 15000.0, 0.5, set(), "I0"),
    ("casa_marrakech", "eactros_600", 5300.0, 0.5, {"y_benguerir_ca"}, "I1"),
    ("casa_marrakech", "eactros_600", 10000.0, 0.5, {"y_benguerir_ca"}, "I1"),
    ("casa_marrakech", "eactros_600", 15000.0, 0.5, {"y_benguerir_ca"}, "I1"),
    ("casa_agadir", "eactros_600", 5300.0, 0.5, {"y_benguerir_ca"}, "I1"),
    ("casa_agadir", "eactros_600", 10000.0, 0.5, {"y_benguerir_ca"}, "I1"),
    ("casa_agadir", "eactros_600", 15000.0, 0.5, {"y_benguerir_ca"}, "I1"),
    ("casa_tangier", "eactros_600", 5300.0, 0.8, {"y_benguerir_ca", "y_larache_rt"}, "I2"),
    ("casa_tangier", "eactros_600", 10000.0, 0.8, {"y_benguerir_ca", "y_larache_rt"}, "I2"),
    ("marrakech_agadir", "volvo_475", 5300.0, 0.8, {"y_benguerir_ca", "y_larache_rt"}, "I2"),
    ("marrakech_agadir", "volvo_475", 10000.0, 0.8, {"y_benguerir_ca", "y_larache_rt"}, "I2"),
    ("casa_marrakech", "volvo_475", 5300.0, 0.5, {"y_benguerir_ca"}, "I1"),
    ("casa_marrakech", "volvo_475", 10000.0, 0.5, {"y_benguerir_ca"}, "I1"),
    ("agadir_casa", "eactros_600", 5300.0, 0.5, {"y_benguerir_ac"}, "I1_ac"),
    ("agadir_casa", "eactros_600", 10000.0, 0.5, {"y_benguerir_ac"}, "I1_ac"),
]


def _sha() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT).decode().strip()
    except Exception:
        return "unknown"


def _write_provenance() -> None:
    PHYS.mkdir(parents=True, exist_ok=True)
    TAB.mkdir(parents=True, exist_ok=True)
    rows = []
    packs = {
        "eactros_600": ROOT / "configs/vehicles/eactros_600.yaml",
        "volvo_475": ROOT / "configs/vehicles/volvo_fh_electric_4x2_540kwh.yaml",
        "volvo_460_sensitivity": ROOT
        / "configs/vehicles/volvo_fh_electric_4x2_540kwh_usable460.yaml",
    }
    class_map = {
        "manufacturer": "Manufacturer-reported",
        "manufacturer_public_web": "Manufacturer-reported",
        "manufacturer_conflict_ma": "Manufacturer-reported",
        "manufacturer_advertised": "Manufacturer-reported",
        "assumed": "Engineering assumption",
        "assumed_variant_pick": "Engineering assumption",
        "literature": "Literature-derived",
        "published": "Literature-derived",
    }
    for vk, path in packs.items():
        if not path.exists():
            continue
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        bat, drive, mass = raw.get("battery") or {}, raw.get("drive") or {}, raw.get("mass") or {}
        aero, eff, aux = raw.get("aero") or {}, raw.get("efficiency") or {}, raw.get("auxiliaries") or {}
        soc, chg, spd = raw.get("soc") or {}, raw.get("charging") or {}, raw.get("speed_policy") or {}
        entries = [
            ("battery_installed_kwh", bat.get("installed_kwh"), "kWh", bat.get("provenance"), bat.get("source")),
            ("battery_usable_kwh", bat.get("usable_kwh"), "kWh", bat.get("provenance"), bat.get("source")),
            ("soc_min", soc.get("soc_min"), "frac", "assumed", soc.get("soc_min_note")),
            ("unladen_tractor_kg", mass.get("unladen_tractor_kg"), "kg", mass.get("provenance_tractor"), mass.get("note_tractor")),
            ("unladen_trailer_kg", mass.get("unladen_trailer_kg"), "kg", mass.get("provenance_trailer"), None),
            ("gcm_limit_kg", mass.get("technically_permissible_combination_kg"), "kg", mass.get("provenance_gcm_limit"), mass.get("note_gcm")),
            ("CdA_m2", aero.get("CdA_m2"), "m2", aero.get("CdA_provenance"), aero.get("note")),
            ("Crr", aero.get("Crr"), "-", aero.get("Crr_provenance"), aero.get("note")),
            ("eta_prop", eff.get("eta_prop"), "-", eff.get("eta_prop_provenance"), None),
            ("eta_regen", eff.get("eta_regen"), "-", eff.get("eta_regen_provenance"), None),
            ("peak_regen_power_kw", drive.get("peak_regen_power_kw"), "kW", drive.get("peak_regen_provenance"), None),
            ("continuous_power_kw", drive.get("continuous_power_kw"), "kW", drive.get("continuous_power_provenance"), drive.get("note")),
            ("peak_power_kw", drive.get("peak_power_kw"), "kW", drive.get("peak_power_provenance"), None),
            ("P_aux_w", aux.get("P_aux_w"), "W", aux.get("provenance"), aux.get("note")),
            (
                "ccs_max_charge_kw",
                chg.get("ccs_max_charge_kw"),
                "kW",
                chg.get("provenance") or chg.get("ccs_max_charge_provenance"),
                chg.get("note") or chg.get("ccs_max_charge_source"),
            ),
            ("cruise_kmh", spd.get("cruise_kmh"), "km/h", "assumed", spd.get("note")),
        ]
        for name, val, unit, prov, src in entries:
            rows.append(
                {
                    "vehicle_key": vk,
                    "config_path": str(path.relative_to(ROOT)).replace("\\", "/"),
                    "parameter": name,
                    "value": val,
                    "unit": unit,
                    "source": src or "",
                    "source_date": (raw.get("sources") or {}).get("access_date") or "",
                    "model_or_variant": raw.get("model_reference") or raw.get("name") or raw.get("vehicle_id"),
                    "evidence_classification": class_map.get(str(prov or "assumed"), "Unverified assumption"),
                    "raw_provenance_token": prov,
                }
            )
    tomato = yaml.safe_load(TOMATO.read_text(encoding="utf-8"))
    rows.append(
        {
            "vehicle_key": "scenario",
            "config_path": "configs/optimization/paper_scientific_portfolio.yaml",
            "parameter": "headline_cargo_payload_kg",
            "value": 5300.0,
            "unit": "kg",
            "source": "Constructed light refrigerated research scenario; not measured Moroccan freight",
            "source_date": "",
            "model_or_variant": "Path A headline",
            "evidence_classification": "Engineering assumption",
            "raw_provenance_token": "assumed",
        }
    )
    for k, unit, src, klass in [
        ("setpoint_c", "C", tomato.get("setpoint_source"), "Literature-derived"),
        ("UA_w_per_k", "W/K", tomato.get("UA_note"), "Engineering assumption"),
        ("cargo_precooled", "-", tomato.get("cargo_precooled_note"), "Engineering assumption"),
    ]:
        rows.append(
            {
                "vehicle_key": "refrigeration",
                "config_path": "configs/energy/pass2_tomato_firm_ripe.yaml",
                "parameter": k,
                "value": tomato.get(k),
                "unit": unit,
                "source": src or "",
                "source_date": "",
                "model_or_variant": tomato.get("pass2_scenario_id"),
                "evidence_classification": klass,
                "raw_provenance_token": tomato.get("UA_provenance") if "UA" in k else "literature",
            }
        )
    pd.DataFrame(rows).to_csv(PHYS / "parameter_provenance_matrix.csv", index=False)
    pd.DataFrame(rows).to_csv(TAB / "R-T15_parameter_provenance.csv", index=False)
    bench = [
        {
            "benchmark_id": "eactros600_europe_testing_tour_2024",
            "source": "Daimler Truck eActros 600 European Testing Tour 2024",
            "url": "https://www.daimlertruck.com/en/newsroom/events/2024/eactros-600-european-testing-tour-2024",
            "metric": "average_driving_consumption",
            "value_kwh_per_km": 1.03,
            "gcm_t": 40.0,
            "distance_km": 15269.0,
            "daily_range_note": "0.85–1.40 kWh/km",
            "comparison_class": "order_of_magnitude_plausibility",
            "notes": "Near-series prototype; not matched to 5.3 t refrigerated Moroccan DEM missions.",
        }
    ]
    pd.DataFrame(bench).to_csv(PHYS / "external_consumption_benchmarks.csv", index=False)
    pd.DataFrame(bench).to_csv(TAB / "R-T16_external_benchmarks.csv", index=False)
    (PHYS / "P2_physical_model_credibility.md").write_text(
        """# P2 — Physical-model provenance and credibility

See `parameter_provenance_matrix.csv` and `R-T15_parameter_provenance.csv`.

- Assumed aero, Crr, efficiencies, trailer curb, aux and regen limits are **engineering assumptions**, not experimentally validated for these packs.
- Primary Volvo pack remains **475 kWh usable** (MA page); `*_usable460.yaml` is sensitivity-only.
- External eActros 600 tour (~1.03 kWh/km at 40 t) is **order-of-magnitude plausibility**, not calibration.
- Refrigeration: firm-ripe tomato 9 °C (UNECE mid-band; UC Davis 7–10 °C consistent). Bank et al. (2025) is methodological inspiration only. Electrical demand without cargo-temperature evolution ⇒ no temperature-compliance claim.
""",
        encoding="utf-8",
    )


def _eval_volvo(od, payload, soc, installed, variant, opts, sha, block):
    """Volvo path mirroring p2._eval_row with vehicle YAML override."""
    v_yaml = Path(stage_c.VEHICLES["volvo_475"])
    fridge = TOMATO
    if opts.get("ua_mult"):
        fridge = p2._write_fridge(ua_mult=opts["ua_mult"], tag=variant)
    weather = str(opts.get("weather") or "cool")
    chg = float(opts.get("charger_kw") or 350.0)
    ref_on = bool(opts.get("refrigeration_on", True))
    print(f"[{block}/volvo] {od} p={payload} soc={soc} {variant}", flush=True)
    cfg, vehicle, context, masks = p2._prepare(
        od_id=od,
        payload=payload,
        soc=soc,
        vehicle_yaml=v_yaml,
        fridge_yaml=fridge,
        weather_id=weather,
        charger_kw=chg,
        refrigeration_on=ref_on,
        cache_tag=f"{block}_{variant}_volvo",
    )
    mid = context["missions"][0].id
    mr = evaluate_mission_operational(
        prep=context["prepared"][mid],
        cfg=cfg,
        installed=set(installed),
        mask=frozenset(masks[mid]["all"]),
        vehicle=vehicle,
        fridge_path=fridge,
        max_seconds=stage_c.UNIFORM_MAX_SECONDS,
        max_expansions=stage_c.ABLATION_MAX_EXPANSIONS,
        include_energy_only=True,
    )
    row = dict(mr)
    tr = row.get("action_trace_json")
    et = ea = er = eg = None
    if tr and not isinstance(tr, float):
        actions = json.loads(tr) if isinstance(tr, str) else tr
        et = sum(float(a.get("E_traction_kwh") or 0) for a in actions)
        ea = sum(float(a.get("E_aux_kwh") or 0) for a in actions)
        er = sum(float(a.get("E_refrig_kwh") or 0) for a in actions)
        eg = sum(float(a.get("E_regen_credit_kwh") or 0) for a in actions)
    row.update(
        {
            "variant": variant,
            "block": block,
            "od_id": od,
            "vehicle_key": "volvo_475",
            "payload_kg": payload,
            "soc_frac": soc,
            "installed": ",".join(sorted(installed)),
            "charger_power_kw": chg,
            "vehicle_CdA_m2": float(vehicle.CdA_m2),
            "vehicle_Crr": float(vehicle.Crr),
            "vehicle_P_aux_w": float(vehicle.P_aux_w),
            "weather_id": weather,
            "refrigeration_on": ref_on,
            "setpoint_c": float(load_refrigeration(fridge).setpoint_c),
            "E_traction_kwh": et,
            "E_aux_kwh": ea,
            "E_refrig_kwh": er,
            "E_regen_credit_kwh": eg,
            "git_sha": sha,
            "pipeline": f"journal_{block}",
            "drive_tables_rebaked": True,
        }
    )
    print(
        f"  status={row.get('status')} ops={row.get('operationally_served')} "
        f"min_soc={row.get('min_soc')} refrig_kwh={er}",
        flush=True,
    )
    return row


def _eval_any(od, vk, payload, soc, installed, variant, opts, sha, block):
    if vk == "volvo_475":
        return _eval_volvo(od, payload, soc, installed, variant, opts, sha, block)
    row = p2._eval_row(od, payload, soc, installed, variant, opts, sha, block)
    row["vehicle_key"] = "eactros_600"
    return row


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    _write_provenance()
    (OUT / "P4_payload_justification.md").write_text(
        """# P4.1 — Headline payload justification (5.3 t)

**Value:** 5300 kg (`cargo_payload_kg` in `paper_scientific_portfolio.yaml`).

**Classification:** deliberately light **engineering / research scenario assumption**.
Not a measured Moroccan freight load; not claimed as typical national refrigerated tonnage.
Historical task reports already label 5300 / 15000 kg as engineering assumptions.

Preserve the 5.3 t historical baseline; use matched 10 t / 15 t cells for persistence checks.
""",
        encoding="utf-8",
    )
    weather_rows = []
    for p in (ROOT / "tests/fixtures/weather").glob("*.json"):
        if p.name == "selection.json":
            continue
        raw = json.loads(p.read_text(encoding="utf-8"))
        weather_rows.append(
            {
                "fixture": p.name,
                "keys": ",".join(sorted(raw.keys())[:20]),
                "temp_c": raw.get("temp_c_mean")
                or raw.get("temperature_c")
                or raw.get("T_air_c")
                or raw.get("t_air_c"),
            }
        )
    pd.DataFrame(weather_rows).to_csv(OUT / "weather_fixture_inventory.csv", index=False)
    (OUT / "P4_weather_notes.md").write_text(
        """# P4.3 — Weather representativeness

Headline Path A uses the controlled **cool** ambient. Hot/warm sensitivity uses the model
`weather_id` (`hot` / fixtures under `tests/fixtures/weather/`). Scenario frequencies are
**not** observed climate probabilities.
""",
        encoding="utf-8",
    )

    sha = _sha()
    refrig_path = OUT / "refrigeration_controlled_missions.csv"
    payload_path = OUT / "heavier_payload_infra_missions.csv"
    refrig_rows = []
    if refrig_path.exists():
        refrig_rows = pd.read_csv(refrig_path).to_dict(orient="records")
    done_r = {(r.get("od_id"), r.get("vehicle_key"), r.get("variant")) for r in refrig_rows}
    for od, vk, payload, soc, installed, variant, opts in REFRIG:
        key = (od, vk, variant)
        if key in done_r:
            continue
        try:
            refrig_rows.append(_eval_any(od, vk, payload, soc, installed, variant, opts, sha, "refrigeration_journal"))
        except Exception as e:  # noqa: BLE001
            refrig_rows.append(
                {
                    "od_id": od,
                    "vehicle_key": vk,
                    "payload_kg": payload,
                    "soc_frac": soc,
                    "variant": variant,
                    "error": str(e),
                }
            )
        pd.DataFrame(refrig_rows).to_csv(refrig_path, index=False)

    payload_rows = []
    if payload_path.exists():
        payload_rows = pd.read_csv(payload_path).to_dict(orient="records")
    done_p = {
        (r.get("od_id"), r.get("vehicle_key"), float(r.get("payload_kg") or 0), r.get("infra_label"))
        for r in payload_rows
    }
    for od, vk, payload, soc, installed, infra in PAYLOAD:
        key = (od, vk, float(payload), infra)
        if key in done_p:
            continue
        try:
            row = _eval_any(
                od,
                vk,
                payload,
                soc,
                installed,
                f"payload_{int(payload)}_{infra}",
                {"refrigeration_on": True, "weather": "cool"},
                sha,
                "payload_infra",
            )
            row["infra_label"] = infra
            payload_rows.append(row)
        except Exception as e:  # noqa: BLE001
            payload_rows.append(
                {
                    "od_id": od,
                    "vehicle_key": vk,
                    "payload_kg": payload,
                    "soc_frac": soc,
                    "infra_label": infra,
                    "error": str(e),
                }
            )
        pd.DataFrame(payload_rows).to_csv(payload_path, index=False)

    if refrig_rows:
        pd.DataFrame(refrig_rows).to_csv(TAB / "R-T17_refrigeration_controlled.csv", index=False)
    if payload_rows:
        pd.DataFrame(payload_rows).to_csv(TAB / "R-T18_heavier_payload_infra.csv", index=False)

    # Steep-grade note (P1.3)
    steep = FE / "experiments/executed_route_geometry/P1_steep_gradient_343a5225681579e5.md"
    steep.write_text(
        """# P1.3 — Arc `343a5225681579e5` max gradient ~23%

- **Location:** Casablanca origin connector `casablanca` → `J13208408666` (~5.55 km).
- **Profile:** 39 DEM samples; net elevation change small (~−3.6 m).
- **Max |grade|:** ~0.230 over a **2.61 m** segment near the arc end (s≈5549–5552 m).
- **Segments >10% / >15%:** one segment, length 2.61 m.
- **Interpretation:** short DEM/junction sampling artifact, not a sustained ~23% motorway grade.
- **Action:** do **not** auto-clip; report raw max with length context. Solver used valid DEM (not flat fallback).
""",
        encoding="utf-8",
    )

    print(f"Done refrig={len(refrig_rows)} payload={len(payload_rows)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
