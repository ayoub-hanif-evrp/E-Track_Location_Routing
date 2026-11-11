"""One-shot helper: write Task 07B thermal YAML ladder (documented ranges only)."""
from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
base = yaml.safe_load(
    (ROOT / "configs/energy/refrigeration_approx.yaml").read_text(encoding="utf-8")
)
variants = {
    "task07b_thermal_low.yaml": {
        "UA_w_per_k": 50.0,
        "infiltration_w": 0.0,
        "scenario_id": "thermal_low",
        "note": "YAML UA_sensitivity low",
    },
    "task07b_thermal_nominal.yaml": {
        "UA_w_per_k": 80.0,
        "infiltration_w": 0.0,
        "scenario_id": "thermal_nominal",
        "note": "current research default",
    },
    "task07b_thermal_high.yaml": {
        "UA_w_per_k": 120.0,
        "infiltration_w": 0.0,
        "scenario_id": "thermal_high",
        "note": "YAML UA_sensitivity high",
    },
    "task07b_thermal_summer.yaml": {
        "UA_w_per_k": 120.0,
        "infiltration_w": 0.0,
        "scenario_id": "thermal_summer",
        "note": "high UA; pair with hot weather",
    },
    "task07b_thermal_infiltration_assumed.yaml": {
        "UA_w_per_k": 80.0,
        "infiltration_w": 500.0,
        "scenario_id": "thermal_infiltration_assumed",
        "note": "explicit assumed duty, not observed",
    },
}
for name, ov in variants.items():
    d = dict(base)
    d["UA_w_per_k"] = ov["UA_w_per_k"]
    d["infiltration_w"] = ov["infiltration_w"]
    d["task07b_scenario_id"] = ov["scenario_id"]
    d["task07b_note"] = ov["note"]
    d["disclaimer"] = (
        str(d.get("disclaimer") or "")
        + f" Task 07B scenario {ov['scenario_id']}: {ov['note']}."
    )
    out = ROOT / "configs/energy" / name
    out.write_text(yaml.safe_dump(d, sort_keys=False), encoding="utf-8")
    print("wrote", out)
