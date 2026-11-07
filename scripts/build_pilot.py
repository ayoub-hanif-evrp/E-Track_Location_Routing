#!/usr/bin/env python3
"""Build the Casablanca–Agadir pilot network dataset (Task 01)."""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

# Allow running without install
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from morocco_etruck import __version__
from morocco_etruck.baseline_routing import run_baseline_routes, write_baseline_results
from morocco_etruck.data_sources import (
    build_source_registry,
    ensure_geofabrik_pbf,
    extract_bbox_pbf,
    load_config,
    project_root_from_config_path,
    resolve_path,
    write_json,
    write_sources_csv,
)
from morocco_etruck.report import generate_report
from morocco_etruck.road_network import build_pilot_graph, export_graph_artifacts, resolve_extract_input
from morocco_etruck.service_areas import build_candidate_sites, write_candidate_sites
from morocco_etruck.validation import network_summary

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("build_pilot")


def main() -> int:
    parser = argparse.ArgumentParser(description="Build Moroccan A3 pilot dataset")
    parser.add_argument(
        "--config",
        type=Path,
        default=ROOT / "configs" / "pilot_corridor.yaml",
    )
    parser.add_argument("--skip-download", action="store_true", help="Require cached PBF")
    args = parser.parse_args()

    config_path = args.config.resolve()
    config = load_config(config_path)
    root = project_root_from_config_path(config_path)

    raw_dir = resolve_path(root, config["paths"]["raw_dir"])
    processed_dir = resolve_path(root, config["paths"]["processed_dir"])
    metadata_dir = resolve_path(root, config["paths"]["metadata_dir"])
    reports_dir = resolve_path(root, config["paths"]["reports_dir"])
    results_dir = resolve_path(root, config["paths"]["results_dir"])
    for d in (raw_dir, processed_dir, metadata_dir, reports_dir, results_dir):
        d.mkdir(parents=True, exist_ok=True)

    # 1) Download / cache Geofabrik PBF
    national_pbf, sha256, osm_meta = ensure_geofabrik_pbf(config, root)
    if args.skip_download and osm_meta.get("downloaded"):
        logger.error("--skip-download set but file was downloaded")
        return 2

    # 2) Geographic extract
    extract_path = raw_dir / "a3_casa_agadir.osm.pbf"
    extract_info = extract_bbox_pbf(national_pbf, extract_path, config["bbox"])
    pbf_for_graph, bbox = resolve_extract_input(raw_dir, extract_info, national_pbf)

    # 3) Directed road graph
    G = build_pilot_graph(national_pbf, extract_info, config)
    export_graph_artifacts(G, processed_dir)
    net_stats = network_summary(G)

    # 4) Candidate service areas
    adm_cache = raw_dir / "adm_aires_de_services.html"
    sites, sa_meta = build_candidate_sites(config, G, pbf_for_graph, bbox, adm_html_cache=adm_cache)
    write_candidate_sites(sites, processed_dir / "candidate_sites.csv")

    # 5) Baseline routing
    baseline = run_baseline_routes(G, config)
    write_baseline_results(baseline, results_dir)

    # 6) Sources + manifest
    records = build_source_registry(config, osm_meta)
    write_sources_csv(records, metadata_dir / "sources.csv")

    status_counts = sites["match_status"].value_counts().to_dict() if len(sites) else {}
    manifest = {
        "built_at_utc": datetime.now(timezone.utc).isoformat(),
        "package_version": __version__,
        "config": str(config_path),
        "osm": osm_meta,
        "extract": extract_info,
        "crs": config["crs"],
        "bbox": config["bbox"],
        "highway_classes": config["osm"]["highway_classes"],
        "network": net_stats,
        "candidates": {
            "n_total": int(len(sites)),
            "status_counts": {str(k): int(v) for k, v in status_counts.items()},
        },
        "baseline_routes": {
            k: {
                "ok": v.get("ok"),
                "distance_km": v.get("distance_km"),
                "error": v.get("error"),
            }
            for k, v in baseline.get("routes", {}).items()
        },
        "direction_asymmetry_km": baseline.get("direction_asymmetry_km"),
        "adm_trafic_probe": sa_meta.get("adm_trafic"),
        "sha256_national_pbf": sha256,
        "notes": [
            "Service areas are potential future truck-charger locations, not verified e-truck chargers.",
            "Unresolved candidates never receive invented coordinates.",
            "Baseline routes are connectivity validation only.",
        ],
    }
    write_json(metadata_dir / "build_manifest.json", manifest)

    # 7) Report
    generate_report(G, sites, baseline, processed_dir, reports_dir)

    logger.info("Build complete. Nodes=%s Edges=%s Candidates=%s",
                net_stats["n_nodes"], net_stats["n_edges"], len(sites))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
