"""Regression: explicit 100% SOC northbound demand must exist and stay consistent."""

from __future__ import annotations

from pathlib import Path

from morocco_etruck.optimization.multiroute_placement import load_multiroute_placement_config

ROOT = Path(__file__).resolve().parents[2]
CFG = ROOT / "configs/optimization/multiroute_placement_pass2a.yaml"
PAPER_CFG = ROOT / "configs/optimization/paper_scientific_portfolio.yaml"


def test_explicit_soc10_demand_exists_and_matches_payload():
    cfg = load_multiroute_placement_config(CFG, root=ROOT)
    assert "A_nb_tomato_p5300_soc10" in cfg.demand_scenarios
    m10 = cfg.demand_scenarios["A_nb_tomato_p5300_soc10"][0]
    m08 = cfg.demand_scenarios["A_nb_tomato_p5300_soc08"][0]
    assert float(m10.E_init_soc_frac) == 1.0
    assert float(m08.E_init_soc_frac) == 0.8
    assert float(m10.cargo_payload_kg) == float(m08.cargo_payload_kg)
    assert m10.od_id == m08.od_id == "agadir_casa"
    assert m10.refrigeration_on is True
    assert m10.terrain_mode == m08.terrain_mode
    assert m10.weather_id == m08.weather_id


def test_paper_portfolio_keeps_explicit_soc_fractions_not_force_soc():
    """Live config guard replacing retired run_final_moroccan_robustness.py source scan."""
    text = PAPER_CFG.read_text(encoding="utf-8")
    assert "force_soc" not in text
    cfg = load_multiroute_placement_config(PAPER_CFG, root=ROOT)
    assert cfg.demand_scenarios, "paper portfolio must declare demand scenarios"
    for missions in cfg.demand_scenarios.values():
        for m in missions:
            soc = float(m.E_init_soc_frac)
            assert 0.0 < soc <= 1.0
