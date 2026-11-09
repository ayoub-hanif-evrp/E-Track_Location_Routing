"""Adversarial placement config validation (Task 05A Stage 1)."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest
import yaml

from morocco_etruck.optimization.placement_problem import (
    PlacementConfigError,
    load_placement_config,
    validate_placement_config,
)

ROOT = Path(__file__).resolve().parents[2]
PILOT = ROOT / "configs/optimization/placement_pilot.yaml"


def _raw():
    return yaml.safe_load(PILOT.read_text(encoding="utf-8"))


def _write_tmp(tmp_path: Path, raw: dict) -> Path:
    p = tmp_path / "placement.yaml"
    p.write_text(yaml.safe_dump(raw), encoding="utf-8")
    return p


def test_valid_pilot_loads():
    cfg = load_placement_config(PILOT, root=ROOT)
    validate_placement_config(cfg)
    assert cfg.crf > 0
    assert cfg.cents_to_currency > 0


def test_rejects_negative_capex(tmp_path):
    raw = _raw()
    raw["capex_scenarios"]["equal"]["site_capex"]["y_settat_ca"] = -1.0
    with pytest.raises(PlacementConfigError, match="negative CAPEX"):
        load_placement_config(_write_tmp(tmp_path, raw), root=ROOT)


def test_rejects_nonpositive_weight(tmp_path):
    raw = _raw()
    raw["demand_scenarios"]["default"]["missions"][0]["weight"] = 0.0
    with pytest.raises(PlacementConfigError, match="weight must be > 0"):
        load_placement_config(_write_tmp(tmp_path, raw), root=ROOT)


def test_rejects_duplicate_site_ids(tmp_path):
    raw = _raw()
    raw["sites"].append(deepcopy(raw["sites"][0]))
    with pytest.raises(PlacementConfigError, match="duplicate site"):
        load_placement_config(_write_tmp(tmp_path, raw), root=ROOT)


def test_rejects_negative_budget(tmp_path):
    raw = _raw()
    raw["budgets"][0]["max_capex"] = -10.0
    with pytest.raises(PlacementConfigError, match="max_capex"):
        load_placement_config(_write_tmp(tmp_path, raw), root=ROOT)


def test_rejects_unknown_baseline_site(tmp_path):
    raw = _raw()
    raw["baselines"]["bogus"] = ["not_a_site"]
    with pytest.raises(PlacementConfigError, match="baseline"):
        load_placement_config(_write_tmp(tmp_path, raw), root=ROOT)


def test_rejects_bad_lifetime(tmp_path):
    raw = _raw()
    raw["annualization"]["lifetime_years"] = 0
    with pytest.raises(PlacementConfigError, match="lifetime_years"):
        load_placement_config(_write_tmp(tmp_path, raw), root=ROOT)
