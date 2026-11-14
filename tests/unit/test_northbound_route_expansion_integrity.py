"""Northbound 2-vs-4 alternative nesting / segmentation integrity."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from morocco_etruck.optimization.multiroute_adapter import (
    allowed_arc_ids_for_edge_union,
    edge_union_from_path_rows,
    load_multiroute_pilot_config,
    select_od_path_rows,
)

ROOT = Path(__file__).resolve().parents[2]
OD = "agadir_casa"


def test_two_alt_edges_contained_in_four_alt_union():
    cfg = load_multiroute_pilot_config(
        ROOT / "configs/optimization/multiroute_pilot.yaml", root=ROOT
    )
    rows = pd.read_csv(cfg.path_alternatives_csv).to_dict(orient="records")
    e2 = edge_union_from_path_rows(select_od_path_rows(rows, OD, 2))
    e4 = edge_union_from_path_rows(select_od_path_rows(rows, OD, 4))
    assert e2.issubset(e4)
    assert len(e4) >= len(e2)


def test_allowed_arc_mask_is_subset_of_full_arc_set_identity():
    """Mask helper returns a subset; physical arc ids are strings."""
    # Lightweight structural check using empty union → empty mask
    class _Ctx:
        macros_by_arc_id = {
            "a1": type("M", (), {"osm_edge_pairs": [(1, 2)], "path_nodes": [1, 2]})(),
            "a2": type("M", (), {"osm_edge_pairs": [(2, 3)], "path_nodes": [2, 3]})(),
        }

    full = {(1, 2), (2, 3)}
    sub = {(1, 2)}
    assert allowed_arc_ids_for_edge_union(_Ctx(), full) == frozenset({"a1", "a2"})
    assert allowed_arc_ids_for_edge_union(_Ctx(), sub) == frozenset({"a1"})
    assert allowed_arc_ids_for_edge_union(_Ctx(), set()) == frozenset()


def test_diagnostics_artifact_documents_q10_artifact_and_q5_nesting():
    path = ROOT / "results/northbound_route_expansion_diagnostics.csv"
    if not path.exists():
        pytest.skip("diagnostics CSV not generated")
    df = pd.read_csv(path)
    sub = df[df.experiment == "solve_compare"]
    assert not sub.empty
    r10 = sub[sub.q == 10].iloc[0]
    r5 = sub[sub.q == 5].iloc[0]
    # Containment already true in companion summary; rebuild vs mask incommensurable at q10
    assert str(r10.rebuild2_status) == "OPTIMAL"
    assert str(r10.mask2_status) == "INFEASIBLE"
    assert str(r10.full4_status) == "INFEASIBLE"
    assert "segmentation_artifact" in str(r10.nesting_class)
    # Same-graph nesting restored at q=5
    assert str(r5.mask2_status) == "OPTIMAL"
    assert str(r5.full4_status) == "OPTIMAL"
    assert float(r5.full4_obj) <= float(r5.mask2_obj) + 1e-9
    # Extra flooring on finer segmentation at q10
    assert float(r10.rounding_loss_same_nodes_on4_kwh) > float(
        r10.rounding_loss_rebuild2_kwh
    )


def test_charger_keys_stable_across_rebuild_sizes_in_artifact():
    path = ROOT / "results/northbound_route_expansion_diagnostics.csv"
    if not path.exists():
        pytest.skip("diagnostics CSV not generated")
    df = pd.read_csv(path)
    sub = df[df.experiment == "solve_compare"]
    for _, r in sub.iterrows():
        assert set(str(r.stations2).split(",")) == set(str(r.stations4).split(","))
        assert "benguerir_ac" in str(r.stations4)
        assert "settat_ac" in str(r.stations4)


def test_summary_acceptance_mentions_q5_nesting():
    path = ROOT / "results/northbound_route_expansion_summary.json"
    if not path.exists():
        pytest.skip("summary JSON missing")
    summary = json.loads(path.read_text(encoding="utf-8"))
    assert "A_at_q5" in summary["acceptance"] or summary["acceptance"].startswith("A_")
    assert "no_full_network_optimality_claim" in summary["acceptance"]


def test_placement_bb_enum_agree_on_canonical_q5_when_present():
    path = ROOT / "results/northbound_route_expansion_diagnostics.csv"
    if not path.exists():
        pytest.skip("diagnostics CSV not generated")
    df = pd.read_csv(path)
    place = df[df.experiment == "placement_canonical4"]
    if place.empty:
        pytest.skip("canonical placement not in artifact yet")
    assert (place.q == 5).all()
    assert place.bb_enum_agree.astype(str).str.lower().isin({"true", "1"}).all()
