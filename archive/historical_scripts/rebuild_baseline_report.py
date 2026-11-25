#!/usr/bin/env python3
"""Recompute baseline routes and reports from existing processed graph CSVs."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import pandas as pd

from morocco_etruck.baseline_routing import run_baseline_routes, write_baseline_results
from morocco_etruck.data_sources import load_config, write_json
from morocco_etruck.report import generate_report, write_static_corridor_figure
from morocco_etruck.road_network import load_graph_from_csv
from morocco_etruck.validation import network_summary

config = load_config(ROOT / "configs" / "pilot_corridor.yaml")
processed = ROOT / "data" / "processed"
G = load_graph_from_csv(processed / "road_nodes.csv", processed / "road_edges.csv")
sites = pd.read_csv(processed / "candidate_sites.csv")
baseline = run_baseline_routes(G, config)
write_baseline_results(baseline, ROOT / "results")
generate_report(G, sites, baseline, processed, ROOT / "reports")
write_static_corridor_figure(sites, baseline, ROOT / "reports")

manifest_path = ROOT / "data" / "metadata" / "build_manifest.json"
manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
manifest["network"] = network_summary(G)
manifest["baseline_routes"] = {
    k: {"ok": v.get("ok"), "distance_km": v.get("distance_km"), "error": v.get("error")}
    for k, v in baseline.get("routes", {}).items()
}
manifest["direction_asymmetry_km"] = baseline.get("direction_asymmetry_km")
write_json(manifest_path, manifest)
print(json.dumps(manifest["baseline_routes"], indent=2))
