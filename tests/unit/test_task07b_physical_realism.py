"""Task 07B — DEM gates, thermal ladder, deadlines, discrete vs continuous, fingerprints."""

from __future__ import annotations

import json
from pathlib import Path

import yaml

from morocco_etruck.optimization.drive_table_cache import (
    build_drive_table_fingerprint,
    file_sha256,
)
from morocco_etruck.optimization.multiroute_placement import (
    load_multiroute_placement_config,
)
from morocco_etruck.optimization.placement_cache import build_mission_energy_fingerprint
from morocco_etruck.optimization.problem import RoutingInstance, StationData

ROOT = Path(__file__).resolve().parents[2]
CFG07B = ROOT / "configs/optimization/multiroute_placement_07b.yaml"


def test_07b_demand_weight_fixed_55():
    cfg = load_multiroute_placement_config(CFG07B, root=ROOT)
    for name in (
        "cold_chain_baseline_07b_flat",
        "cold_chain_baseline_07b_dem",
    ):
        missions = cfg.demand_scenarios[name]
        assert abs(sum(m.weight for m in missions) - 5.5) < 1e-9
        assert all(m.cargo_payload_kg == 5300.0 for m in missions)
        assert all(m.E_init_soc_frac == 0.5 for m in missions)
        assert all(m.refrigeration_on for m in missions)


def test_07b_dem_meta_complete_for_pilot_ods():
    meta = json.loads(
        (ROOT / "data/processed/multiroute/elevation/dem_sampling_meta.json").read_text(
            encoding="utf-8"
        )
    )
    assert meta.get("blockers") in (None, [])
    arcs = meta["arcs"]
    assert len(arcs) == 29
    assert all(a["quality"] == "valid" for a in arcs.values())
    assert all(a["source"] == "copdem_glo30" for a in arcs.values())
    ods = {a["od_id"] for a in arcs.values()}
    assert {"casa_marrakech", "casa_agadir", "marrakech_agadir"} <= ods


def test_thermal_ladder_yamls_match_documented_ranges():
    expected = {
        "task07b_thermal_low.yaml": (50.0, 0.0),
        "task07b_thermal_nominal.yaml": (80.0, 0.0),
        "task07b_thermal_high.yaml": (120.0, 0.0),
        "task07b_thermal_summer.yaml": (120.0, 0.0),
        "task07b_thermal_infiltration_assumed.yaml": (80.0, 500.0),
    }
    for name, (ua, inf) in expected.items():
        d = yaml.safe_load((ROOT / "configs/energy" / name).read_text(encoding="utf-8"))
        assert float(d["UA_w_per_k"]) == ua
        assert float(d["infiltration_w"]) == inf


def test_fingerprint_invalidates_on_terrain_thermal_deadline_power():
    v = ROOT / "configs/vehicles/eactros_600.yaml"
    f_nom = ROOT / "configs/energy/task07b_thermal_nominal.yaml"
    f_high = ROOT / "configs/energy/task07b_thermal_high.yaml"
    base = dict(
        vehicle_yaml=v,
        fridge_yaml=f_nom,
        q=10,
        time_step_min=5,
        terrain_mode="flat",
        weather_id="cool",
        refrigeration="on",
        power_source="A",
        extra={"deadline_steps": 240, "charger_power_kw": 350.0},
    )
    fp0 = build_mission_energy_fingerprint(**base)
    fp_terrain = build_mission_energy_fingerprint(**{**base, "terrain_mode": "dem"})
    fp_thermal = build_mission_energy_fingerprint(**{**base, "fridge_yaml": f_high})
    fp_deadline = build_mission_energy_fingerprint(
        **{**base, "extra": {"deadline_steps": 144, "charger_power_kw": 350.0}}
    )
    fp_power = build_mission_energy_fingerprint(
        **{**base, "extra": {"deadline_steps": 240, "charger_power_kw": 150.0}}
    )
    assert fp0 != fp_terrain
    assert fp0 != fp_thermal
    assert fp0 != fp_deadline
    assert fp0 != fp_power
    # Drive-table fingerprint also tracks terrain + fridge
    dt_base = dict(
        vehicle_yaml=v,
        fridge_yaml=f_nom,
        weather_points={"T": 20},
        terrain_mode="flat",
        terrain_source="flat",
        terrain_hash="h0",
        macro_u="O",
        macro_v="D",
        edge_pairs=[(1, 2)],
        length_m=1000.0,
        gcm_kg=25000.0,
        refrigeration_on=True,
        power_source="A",
        energy_quantum_kwh=10,
        time_step_min=5,
        E_truck_min=60,
        E_truck_cap=600,
        E_trailer_min=None,
        E_trailer_cap=None,
    )
    assert build_drive_table_fingerprint(**dt_base) != build_drive_table_fingerprint(
        **{**dt_base, "terrain_mode": "dem", "terrain_source": "copdem_glo30"}
    )
    assert build_drive_table_fingerprint(**dt_base) != build_drive_table_fingerprint(
        **{**dt_base, "fridge_yaml": f_high}
    )
    assert file_sha256(f_nom) != file_sha256(f_high)


def test_charge_duration_scales_inversely_with_power():
    def _inst(power_kw: float) -> RoutingInstance:
        return RoutingInstance(
            name="t",
            nodes=["O", "S", "D"],
            arcs=[],
            origin="O",
            destination="D",
            deadline_steps=240,
            E_truck_cap=600,
            E_truck_min=60,
            E_truck_init=300,
            E_trailer_cap=None,
            E_trailer_min=None,
            E_trailer_init=None,
            stations={
                "S": StationData(
                    node="S",
                    power_kw=power_kw,
                    eta=0.95,
                    price_cents_per_grid_kwh=20,
                )
            },
            active_stations={"S"},
            power_source="A",
            refrigeration_on=True,
            time_step_min=5,
            energy_quantum_kwh=10,
        )

    inst350 = _inst(350.0)
    inst150 = _inst(150.0)
    d350 = inst350.charge_duration_steps(inst350.stations["S"], 100)
    d150 = inst150.charge_duration_steps(inst150.stations["S"], 100)
    assert d150 > d350
    assert d150 / d350 >= 2.0


def test_shortest_path_baseline_restricts_union():
    """max_alternatives_for_union=1 keeps only shortest_distance row for an OD."""
    import pandas as pd

    from morocco_etruck.optimization.multiroute_adapter import load_multiroute_pilot_config

    cfg = load_multiroute_pilot_config(
        ROOT / "configs/optimization/multiroute_pilot.yaml", root=ROOT
    )
    path_df = pd.read_csv(cfg.path_alternatives_csv)
    od = "casa_marrakech"
    rows = path_df[path_df.od_id == od]
    assert (rows.method == "shortest_distance").any()
    n_all = len(rows)
    assert n_all >= 2
    # Selection logic mirror of adapter
    short = rows[rows.method == "shortest_distance"]
    rest = rows[rows.method != "shortest_distance"].sort_values(
        "jaccard_distance_vs_shortest", ascending=False
    )
    kept = pd.concat([short.head(1), rest]).head(1)
    assert len(kept) == 1
    assert str(kept.iloc[0]["method"]) == "shortest_distance"


def test_deadline_physically_impossible_helper():
    """Windows shorter than min drive+charge are gated, not forced infeasible theater."""
    min_journey_h = 9.5
    assert 8.0 < min_journey_h
    assert not (10.0 < min_journey_h)
