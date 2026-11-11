"""Task 07A — demand portfolio integrity, alternate optima, certification."""

from __future__ import annotations

from pathlib import Path

from morocco_etruck.optimization.multiroute_placement import (
    load_multiroute_placement_config,
)
from morocco_etruck.optimization.placement_certification import (
    OptimalityStatus,
    portfolio_optimality_status,
)

ROOT = Path(__file__).resolve().parents[2]
CFG07 = ROOT / "configs/optimization/multiroute_placement_07a.yaml"


def test_primary_portfolio_no_ablation_or_mixed_weather():
    cfg = load_multiroute_placement_config(CFG07, root=ROOT)
    primary = cfg.demand_scenarios["cold_chain_baseline_07a"]
    assert all(m.refrigeration_on for m in primary)
    assert {m.weather_id for m in primary} == {"cool"}
    assert abs(sum(m.weight for m in primary) - 5.5) < 1e-9
    assert {m.id for m in primary} == {
        "M_casa_marrakech",
        "M_casa_agadir",
        "M_marrakech_agadir",
    }


def test_matched_scenarios_preserve_total_demand_and_ids():
    cfg = load_multiroute_placement_config(CFG07, root=ROOT)
    base = cfg.demand_scenarios["cold_chain_baseline_07a"]
    abl = cfg.demand_scenarios["cold_chain_no_refrigeration_ablation_07a"]
    hot = cfg.demand_scenarios["cold_chain_hot_07a"]
    cool = cfg.demand_scenarios["cold_chain_cool_07a"]
    for sc in (abl, hot, cool):
        assert abs(sum(m.weight for m in sc) - 5.5) < 1e-9
        assert {m.id for m in sc} == {m.id for m in base}
        assert {m.od_id for m in sc} == {m.od_id for m in base}
        assert {m.weight for m in sc} == {m.weight for m in base}
    assert all(not m.refrigeration_on for m in abl)
    assert all(m.refrigeration_on for m in hot)
    assert {m.weather_id for m in hot} == {"hot"}
    assert {m.weather_id for m in cool} == {"cool"}


def test_ablation_not_extra_row_inside_primary():
    cfg = load_multiroute_placement_config(CFG07, root=ROOT)
    primary = cfg.demand_scenarios["cold_chain_baseline_07a"]
    assert len(primary) == 3
    assert not any("ablation" in m.id.lower() for m in primary)


def test_fixed_payload_fields_present():
    cfg = load_multiroute_placement_config(CFG07, root=ROOT)
    for m in cfg.demand_scenarios["cold_chain_baseline_07a"]:
        assert m.cargo_payload_kg == 5300.0
        assert m.E_init_soc_frac == 0.5


def test_portfolio_cert_still_downgrades_replay_invalid():
    assert (
        portfolio_optimality_status(
            core_status=OptimalityStatus.CERTIFIED_OPTIMAL,
            serviceability={"M1": "replay_invalid"},
        )
        == OptimalityStatus.CONDITIONAL_RESTRICTED_PORTFOLIO
    )


def test_all_optimal_site_sets_helper():
    from morocco_etruck.optimization.multiroute_placement_evaluation import (
        all_optimal_site_sets,
    )

    rows = [
        {
            "sites": "y_settat_ca",
            "coverage_serviceable": 4.0,
            "secondary_cost": 10.0,
            "budget_ok": True,
            "certified": True,
        },
        {
            "sites": "y_benguerir_ca",
            "coverage_serviceable": 4.0,
            "secondary_cost": 10.0,
            "budget_ok": True,
            "certified": True,
        },
        {
            "sites": "y_amskroud_ca",
            "coverage_serviceable": 2.0,
            "secondary_cost": 1.0,
            "budget_ok": True,
            "certified": True,
        },
    ]
    opts = all_optimal_site_sets(rows)
    assert opts == ["y_benguerir_ca", "y_settat_ca"]
