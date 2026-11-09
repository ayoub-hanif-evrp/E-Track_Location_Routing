#!/usr/bin/env python
"""Task 05B — Regenerate decision_graph.json from existing multiroute paths (no A3 overwrite)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from morocco_etruck.optimization.route_choice_graph import (  # noqa: E402
    PathRecord,
    classify_path_diversity,
    contract_to_decision_graph,
    union_path_digraph,
    verify_arc_length,
)
from morocco_etruck.road_network import load_graph_from_csv  # noqa: E402


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--corridor-config",
        type=Path,
        default=ROOT / "configs/multiroute_corridor.yaml",
    )
    args = p.parse_args()
    cfg = yaml.safe_load(args.corridor_config.read_text(encoding="utf-8"))
    out_dir = ROOT / cfg["paths"]["processed_dir"]
    nodes = out_dir / "nodes.csv"
    edges = out_dir / "edges.csv"
    if not nodes.exists():
        nodes = out_dir / "road_nodes.csv"
        edges = out_dir / "road_edges.csv"
    G = load_graph_from_csv(nodes, edges)
    anchors_raw = json.loads((out_dir / "od_anchors.json").read_text(encoding="utf-8"))
    city = {k: int(v) for k, v in (anchors_raw.get("city_anchors") or {}).items()}
    od_snaps = anchors_raw.get("od_snaps") or {}

    path_df = pd.read_csv(out_dir / "path_alternatives.csv")
    records: list[PathRecord] = []
    for _, row in path_df.iterrows():
        path = json.loads(row["node_path_json"])
        records.append(
            PathRecord(
                od_id=str(row["od_id"]),
                node_path=path,
                length_m=float(row["length_m"]),
                edge_keys=[],
                method=str(row["method"]),
                jaccard_distance_vs_shortest=float(row["jaccard_distance_vs_shortest"]),
            )
        )

    terminals = dict(city)
    od_pairs = []
    for od in cfg.get("od_pairs") or []:
        od_id = str(od["id"])
        if od_id in od_snaps:
            ok, dk = f"{od_id}__o", f"{od_id}__d"
            terminals[ok] = int(od_snaps[od_id]["origin"])
            terminals[dk] = int(od_snaps[od_id]["destination"])
            od_pairs.append({"id": od_id, "origin": ok, "destination": dk})
        else:
            od_pairs.append(
                {"id": od_id, "origin": str(od["origin"]), "destination": str(od["destination"])}
            )

    union = union_path_digraph(G, [r.node_path for r in records])
    rcg = contract_to_decision_graph(
        union,
        terminals=terminals,
        path_records=records,
        speed_policy=dict(cfg.get("speed_policy") or {}),
        od_pairs=od_pairs,
    )

    length_failures = []
    for a in rcg.arcs:
        ok, summed, declared = verify_arc_length(union, a)
        if not ok:
            length_failures.append(
                {
                    "arc_id": a.arc_id,
                    "u": a.u,
                    "v": a.v,
                    "declared_length_m": declared,
                    "summed_osm_length_m": summed,
                }
            )

    diversity = classify_path_diversity(rcg.path_records)
    pd.DataFrame(diversity).to_csv(out_dir / "path_diversity_audit.csv", index=False)
    if length_failures:
        pd.DataFrame(length_failures).to_csv(out_dir / "arc_length_failures.csv", index=False)
    elif (out_dir / "arc_length_failures.csv").exists():
        (out_dir / "arc_length_failures.csv").unlink()

    dec = {
        "decision_nodes": {k: int(v) for k, v in rcg.decision_nodes.items()},
        "alias_to_canonical": dict(rcg.alias_to_canonical),
        "od_terminals": dict(rcg.od_terminals),
        "arcs": [
            {
                "arc_id": a.arc_id,
                "u": a.u,
                "v": a.v,
                "length_m": a.length_m,
                "scenario_speed_kmh": a.scenario_speed_kmh,
                "highway_classes": a.highway_classes,
                "hgv_access": a.hgv_access,
                "n_osm_edges": len(a.osm_edge_pairs),
                "osm_edge_pairs": [[int(u), int(v)] for u, v in a.osm_edge_pairs],
                "path_nodes": [int(x) for x in a.path_nodes],
            }
            for a in rcg.arcs
        ],
        "notes": rcg.notes,
        "claim_scope": "path_union_of_verified_alternatives_only",
        "n_arc_length_failures": len(length_failures),
    }
    (out_dir / "decision_graph.json").write_text(json.dumps(dec, indent=2), encoding="utf-8")

    # Patch manifest lightly
    man_path = out_dir / "build_manifest.json"
    if man_path.exists():
        man = json.loads(man_path.read_text(encoding="utf-8"))
        man["task"] = "05B"
        man["n_decision_nodes"] = len(rcg.decision_nodes)
        man["n_decision_arcs"] = len(rcg.arcs)
        man["n_arc_length_failures"] = len(length_failures)
        man["od_notes"] = rcg.notes
        man_path.write_text(json.dumps(man, indent=2), encoding="utf-8")

    print(
        f"Regenerated decision graph: nodes={len(rcg.decision_nodes)} arcs={len(rcg.arcs)} "
        f"length_failures={len(length_failures)}",
        flush=True,
    )
    return 0 if not length_failures else 2


if __name__ == "__main__":
    raise SystemExit(main())
