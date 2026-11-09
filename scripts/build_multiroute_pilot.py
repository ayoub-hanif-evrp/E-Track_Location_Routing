#!/usr/bin/env python
"""Task 05A — Build separate multi-route Moroccan road dataset (does not overwrite A3 CSVs)."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from morocco_etruck.data_sources import (  # noqa: E402
    ensure_geofabrik_pbf,
    extract_bbox_pbf,
    load_config,
    project_root_from_config_path,
    resolve_path,
)
from morocco_etruck.optimization.route_choice_graph import (  # noqa: E402
    build_route_choice_for_ods,
    snap_anchors,
    snap_od_pair,
)
from morocco_etruck.road_network import (  # noqa: E402
    build_multidigraph_from_directed_edges,
    export_graph_artifacts,
    load_network_tables_pyrosm,
    resolve_extract_input,
)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--config",
        type=Path,
        default=ROOT / "configs/multiroute_corridor.yaml",
    )
    p.add_argument("--skip-download", action="store_true")
    args = p.parse_args()

    config_path = args.config.resolve()
    config = load_config(config_path)
    root = project_root_from_config_path(config_path)
    raw_dir = resolve_path(root, config["paths"]["raw_dir"])
    out_dir = resolve_path(root, config["paths"]["processed_dir"])
    out_dir.mkdir(parents=True, exist_ok=True)

    print("Ensuring Geofabrik PBF…", flush=True)
    national_pbf, sha256, osm_meta = ensure_geofabrik_pbf(
        config, root, skip_download=args.skip_download
    )

    extract_path = raw_dir / "multiroute_casa_marrakech_agadir.osm.pbf"
    print(f"Extracting bbox -> {extract_path}", flush=True)
    extract_info = extract_bbox_pbf(national_pbf, extract_path, config["bbox"], root=root)
    pbf_for_graph, bbox = resolve_extract_input(
        raw_dir, extract_info, national_pbf, root=root
    )

    highway_classes = list(config["osm"]["highway_classes"])
    if config["osm"].get("include_secondary"):
        highway_classes.extend(["secondary", "secondary_link"])
        highway_classes = list(dict.fromkeys(highway_classes))

    print(f"Loading driving tables (classes={highway_classes})…", flush=True)
    nodes, edges = load_network_tables_pyrosm(pbf_for_graph, bbox, highway_classes)
    G, graph_audit = build_multidigraph_from_directed_edges(nodes, edges)

    # HGV filter for multiroute routing graph
    rejected = []
    if config["osm"].get("filter_hgv_no", True):
        to_remove = []
        for u, v, k, data in list(G.edges(keys=True, data=True)):
            if str(data.get("hgv_access") or "") == "no":
                to_remove.append((u, v, k))
                rejected.append(
                    {
                        "u": u,
                        "v": v,
                        "key": k,
                        "osm_way_id": data.get("osm_way_id", data.get("osmid", "")),
                        "highway": data.get("highway"),
                        "hgv_access": data.get("hgv_access"),
                    }
                )
        G.remove_edges_from(to_remove)

    # Drop isolates
    iso = list(nx_isolates(G))
    G.remove_nodes_from(iso)

    export_graph_artifacts(G, out_dir)
    # export writes road_nodes.csv / road_edges.csv into out_dir — rename clarity
    (out_dir / "nodes.csv").write_bytes((out_dir / "road_nodes.csv").read_bytes())
    (out_dir / "edges.csv").write_bytes((out_dir / "road_edges.csv").read_bytes())

    search_r = float(config["anchors"].get("search_radius_m", 25000))
    print("Snapping OD anchors...", flush=True)
    anchors = snap_anchors(G, config["anchors"], search_radius_m=search_r)

    # Connectivity-aware snaps per OD (fixes one-way carriageway dead-ends)
    od_snaps: dict[str, dict[str, int]] = {}
    for od in config["od_pairs"]:
        od_id = str(od["id"])
        o_name, d_name = str(od["origin"]), str(od["destination"])
        oa = config["anchors"][o_name]
        da = config["anchors"][d_name]
        pair = snap_od_pair(
            G,
            origin_lon=float(oa["lon"]),
            origin_lat=float(oa["lat"]),
            dest_lon=float(da["lon"]),
            dest_lat=float(da["lat"]),
            search_radius_m=search_r,
        )
        if pair is not None:
            od_snaps[od_id] = {"origin": int(pair[0]), "destination": int(pair[1])}
            # Prefer connectivity-aware nodes as city anchors when available
            anchors[o_name] = int(pair[0])
            anchors[d_name] = int(pair[1])
    (out_dir / "od_anchors.json").write_text(
        json.dumps(
            {
                "city_anchors": {k: int(v) for k, v in anchors.items()},
                "od_snaps": od_snaps,
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    print("Discovering route alternatives...", flush=True)
    # Per-OD anchors: use od_snaps when present
    od_pairs = []
    for od in config["od_pairs"]:
        od_id = str(od["id"])
        o_name, d_name = str(od["origin"]), str(od["destination"])
        if od_id in od_snaps:
            # Temporary unique anchor keys for this OD
            ok, dk = f"{od_id}__o", f"{od_id}__d"
            anchors[ok] = od_snaps[od_id]["origin"]
            anchors[dk] = od_snaps[od_id]["destination"]
            od_pairs.append({"id": od_id, "origin": ok, "destination": dk})
        else:
            od_pairs.append({"id": od_id, "origin": o_name, "destination": d_name})

    rcg = build_route_choice_for_ods(
        G,
        anchors=anchors,
        od_pairs=od_pairs,
        path_cfg=dict(config.get("path_discovery") or {}),
        speed_policy=dict(config.get("speed_policy") or {}),
    )
    path_rows = []
    for r in rcg.path_records:
        path_rows.append(
            {
                "od_id": r.od_id,
                "method": r.method,
                "n_nodes": len(r.node_path),
                "length_m": r.length_m,
                "jaccard_distance_vs_shortest": r.jaccard_distance_vs_shortest,
                "node_path_json": json.dumps([int(x) for x in r.node_path]),
            }
        )
    pd.DataFrame(path_rows).to_csv(out_dir / "path_alternatives.csv", index=False)

    hgv_counts = {}
    for _, _, _, d in G.edges(keys=True, data=True):
        h = str(d.get("hgv_access") or "unknown")
        hgv_counts[h] = hgv_counts.get(h, 0) + 1
    class_counts = {}
    for _, _, _, d in G.edges(keys=True, data=True):
        h = str(d.get("highway") or "")
        class_counts[h] = class_counts.get(h, 0) + 1

    audit = {
        "built_at_utc": datetime.now(timezone.utc).isoformat(),
        "task": "05A",
        "config": str(config_path.relative_to(root)).replace("\\", "/"),
        "osm": osm_meta,
        "extract": extract_info,
        "bbox": config["bbox"],
        "highway_classes": highway_classes,
        "n_nodes": G.number_of_nodes(),
        "n_edges": G.number_of_edges(),
        "n_isolates_removed": len(iso),
        "hgv_access_counts": hgv_counts,
        "highway_class_counts": class_counts,
        "n_hgv_no_rejected": len(rejected),
        "anchors": {k: int(v) for k, v in anchors.items()},
        "od_notes": rcg.notes,
        "n_path_records": len(rcg.path_records),
        "n_decision_nodes": len(rcg.decision_nodes),
        "n_decision_arcs": len(rcg.arcs),
        "attribution": {
            "osm": "© OpenStreetMap contributors",
            "license": "ODbL",
            "geofabrik_snapshot": config["osm"].get("snapshot_label"),
        },
        "graph_audit": graph_audit,
        "sha256_national_pbf": sha256,
    }
    (out_dir / "build_manifest.json").write_text(json.dumps(audit, indent=2), encoding="utf-8")
    pd.DataFrame(rejected).to_csv(out_dir / "hgv_audit.csv", index=False)

    # Persist decision graph summary
    dec = {
        "decision_nodes": {k: int(v) for k, v in rcg.decision_nodes.items()},
        "arcs": [
            {
                "u": a.u,
                "v": a.v,
                "length_m": a.length_m,
                "scenario_speed_kmh": a.scenario_speed_kmh,
                "highway_classes": a.highway_classes,
                "hgv_access": a.hgv_access,
                "n_osm_edges": len(a.osm_edge_pairs),
                "path_nodes": [int(x) for x in a.path_nodes],
            }
            for a in rcg.arcs
        ],
        "notes": rcg.notes,
    }
    (out_dir / "decision_graph.json").write_text(json.dumps(dec, indent=2), encoding="utf-8")

    print(
        f"Wrote {out_dir}: nodes={audit['n_nodes']} edges={audit['n_edges']} "
        f"paths={audit['n_path_records']} decision_arcs={audit['n_decision_arcs']}",
        flush=True,
    )
    for n in rcg.notes:
        print(f"  {n}", flush=True)
    return 0


def nx_isolates(G):
    import networkx as nx

    return list(nx.isolates(G))


if __name__ == "__main__":
    raise SystemExit(main())
