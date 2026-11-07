"""Pilot dataset build orchestration."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from morocco_etruck import __version__
from morocco_etruck.baseline_routing import run_baseline_routes, write_baseline_results
from morocco_etruck.data_sources import (
    build_source_registry,
    ensure_geofabrik_pbf,
    extract_bbox_pbf,
    load_config,
    project_root_from_config_path,
    relpath_posix,
    resolve_path,
    write_json,
    write_sources_csv,
)
from morocco_etruck.report import generate_report, write_static_corridor_figure
from morocco_etruck.road_network import build_pilot_graph, export_graph_artifacts, resolve_extract_input
from morocco_etruck.service_areas import build_candidate_sites, write_candidate_sites
from morocco_etruck.validation import network_summary

logger = logging.getLogger(__name__)


def run_build(config_path: Path, *, skip_download: bool = False) -> dict[str, Any]:
    config_path = config_path.resolve()
    config = load_config(config_path)
    root = project_root_from_config_path(config_path)

    raw_dir = resolve_path(root, config["paths"]["raw_dir"])
    processed_dir = resolve_path(root, config["paths"]["processed_dir"])
    metadata_dir = resolve_path(root, config["paths"]["metadata_dir"])
    reports_dir = resolve_path(root, config["paths"]["reports_dir"])
    results_dir = resolve_path(root, config["paths"]["results_dir"])
    for d in (raw_dir, processed_dir, metadata_dir, reports_dir, results_dir):
        d.mkdir(parents=True, exist_ok=True)

    national_pbf, sha256, osm_meta = ensure_geofabrik_pbf(
        config, root, skip_download=skip_download
    )

    extract_path = raw_dir / "a3_casa_agadir.osm.pbf"
    extract_info = extract_bbox_pbf(national_pbf, extract_path, config["bbox"], root=root)
    pbf_for_graph, bbox = resolve_extract_input(
        raw_dir, extract_info, national_pbf, root=root
    )

    G, graph_audit = build_pilot_graph(national_pbf, extract_info, config, root=root)
    export_graph_artifacts(G, processed_dir)
    net_stats = network_summary(G)

    adm_cache = raw_dir / "adm_aires_de_services.html"
    sites, sa_meta = build_candidate_sites(
        config,
        G,
        pbf_for_graph,
        bbox,
        adm_html_cache=adm_cache,
        allow_network=not skip_download,
    )
    write_candidate_sites(sites, processed_dir / "candidate_sites.csv")

    baseline = run_baseline_routes(G, config)
    write_baseline_results(baseline, results_dir)

    records = build_source_registry(config, osm_meta)
    write_sources_csv(records, metadata_dir / "sources.csv")

    access_counts = (
        sites["directed_access_status"].value_counts().to_dict() if len(sites) else {}
    )
    loc_counts = (
        sites["location_match_status"].value_counts().to_dict() if len(sites) else {}
    )
    hgv_counts = sites["hgv_access_status"].value_counts().to_dict() if len(sites) else {}

    manifest = {
        "built_at_utc": datetime.now(timezone.utc).isoformat(),
        "package_version": __version__,
        "task": "01B",
        "config": relpath_posix(config_path, root),
        "osm": osm_meta,
        "extract": extract_info,
        "graph_audit": graph_audit,
        "crs": config["crs"],
        "bbox": config["bbox"],
        "highway_classes": config["osm"]["highway_classes"],
        "network": net_stats,
        "candidates": {
            "n_total": int(len(sites)),
            "location_match_status_counts": {str(k): int(v) for k, v in loc_counts.items()},
            "directed_access_status_counts": {str(k): int(v) for k, v in access_counts.items()},
            "hgv_access_status_counts": {str(k): int(v) for k, v in hgv_counts.items()},
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
        "skip_download": skip_download,
        "notes": [
            "Service areas are potential future truck-charger locations, not verified e-truck chargers.",
            "Proximity/bearing alone never yields verified truck accessibility.",
            "OSM topological entrance/exit ≠ confirmed legal HGV access.",
            "Python research code licence is separate from ODbL obligations for OSM-derived data.",
        ],
        "licensing": {
            "python_code": "Research/academic use as documented in README; not an OSM licence grant",
            "osm_derived_data": "ODbL 1.0 — © OpenStreetMap contributors; attribution + share-alike required",
        },
    }
    write_json(metadata_dir / "build_manifest.json", manifest)

    generate_report(G, sites, baseline, processed_dir, reports_dir)
    write_static_corridor_figure(sites, baseline, reports_dir)

    logger.info(
        "Build complete. Nodes=%s Edges=%s Candidates=%s parallel_collisions=%s",
        net_stats["n_nodes"],
        net_stats["n_edges"],
        len(sites),
        graph_audit.get("parallel_uv_collisions_if_digraph"),
    )
    return manifest
