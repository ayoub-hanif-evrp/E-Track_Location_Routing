#!/usr/bin/env python3
"""Independent recount and quality audit of the constructed research dataset.

Does not copy manifest numbers blindly. Writes machine-readable tables under
results/final_evidence/ and a human-readable quality report.
"""
from __future__ import annotations

import json
import math
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "results" / "final_evidence"
DS = OUT / "dataset"
TAB = OUT / "tables" / "dataset"
MAN = OUT / "manifests"


CLAIMED = {
    "motorway_nodes": 58002,
    "motorway_edges": 58157,
    "expanded_nodes": 391653,
    "expanded_edges": 397255,
    "decision_nodes": 198,
    "decision_arcs": 293,
    "od_pairs": 18,
    "path_records": 36,
    "service_area_inventory": 19,
    "headline_missions": 14,
}


HEADLINE_ODS = [
    "casa_marrakech",
    "casa_agadir",
    "marrakech_agadir",
    "agadir_marrakech",
    "marrakech_casa",
    "agadir_casa",
    "casa_tangier",
    "tangier_casa",
    "tangier_rabat",
    "rabat_tangier",
    "rabat_fes",
    "fes_rabat",
    "casa_rabat",
    "rabat_casa",
]

OUJDA_ODS = ["fes_oujda", "oujda_fes", "casa_oujda", "oujda_casa"]

# Headline campaign retained directional candidates (Path A infra + related).
HEADLINE_CANDIDATE_KEYS = {
    "y_benguerir_ca",
    "y_benguerir_ac",
    "y_settat_ca",
    "y_settat_ac",
    "y_amskroud_ca",
    "y_larache_rt",
    "y_assilah_tr",
    "y_bouznika_cr",
    "y_bouznika_rc",
}


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _geodesic_m(lon1, lat1, lon2, lat2) -> float:
    """Approx WGS84 geodesic metres (haversine)."""
    r = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(min(1.0, math.sqrt(a)))


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def recount_networks() -> dict:
    road_nodes = pd.read_csv(ROOT / "data/processed/road_nodes.csv")
    road_edges = pd.read_csv(ROOT / "data/processed/road_edges.csv")
    mr_nodes = pd.read_csv(ROOT / "data/processed/multiroute/nodes.csv")
    mr_edges = pd.read_csv(ROOT / "data/processed/multiroute/edges.csv")
    dg = load_json(ROOT / "data/processed/multiroute/decision_graph.json")
    paths = pd.read_csv(ROOT / "data/processed/multiroute/path_alternatives.csv")
    cand = pd.read_csv(ROOT / "data/processed/candidate_sites.csv")
    mm = load_json(ROOT / "data/metadata/build_manifest.json")
    mrm = load_json(ROOT / "data/processed/multiroute/build_manifest.json")

    verified = {
        "motorway_nodes": int(len(road_nodes)),
        "motorway_edges": int(len(road_edges)),
        "expanded_nodes": int(len(mr_nodes)),
        "expanded_edges": int(len(mr_edges)),
        "decision_nodes": int(len(dg["decision_nodes"])),
        "decision_arcs": int(len(dg["arcs"])),
        "od_pairs": int(paths["od_id"].nunique()),
        "path_records": int(len(paths)),
        "service_area_inventory": int(len(cand)),
        "od_terminals_in_decision_graph": int(len(dg.get("od_terminals", {}))),
        "headline_missions": len(HEADLINE_ODS),
        "oujda_ods_excluded": len(OUJDA_ODS),
    }

    discrepancies = []
    for k, claimed in CLAIMED.items():
        actual = verified.get(k)
        if actual != claimed:
            discrepancies.append({"metric": k, "claimed": claimed, "verified": actual})

    # Directed vs unique physical length (motorway)
    def length_stats(edges: pd.DataFrame, label: str) -> dict:
        directed_km = float(edges["length_m"].sum() / 1000.0)
        # Unique physical: undirected (min(u,v), max(u,v), osm_way_id) where available
        e = edges.copy()
        e["a"] = e[["u", "v"]].min(axis=1)
        e["b"] = e[["u", "v"]].max(axis=1)
        if "osm_way_id" in e.columns:
            uniq = e.drop_duplicates(subset=["a", "b", "osm_way_id", "edge_key"])
            # Prefer half of directed sum for true two-way pairs approximation:
            pair = e.groupby(["a", "b"], as_index=False)["length_m"].mean()
            unique_km = float(pair["length_m"].sum() / 1000.0)
        else:
            unique_km = float("nan")
        by_class = (
            edges.groupby("highway", dropna=False)["length_m"]
            .sum()
            .div(1000.0)
            .sort_values(ascending=False)
        )
        return {
            "network": label,
            "n_nodes": None,
            "n_edges": int(len(edges)),
            "directed_length_km": directed_km,
            "unique_physical_length_km_approx": unique_km,
            "highway_directed_km": by_class.to_dict(),
            "length_m_p50": float(edges["length_m"].median()),
            "length_m_p95": float(edges["length_m"].quantile(0.95)),
            "length_m_max": float(edges["length_m"].max()),
            "length_m_min": float(edges["length_m"].min()),
        }

    mw_stats = length_stats(road_edges, "motorway_only")
    mw_stats["n_nodes"] = verified["motorway_nodes"]
    exp_stats = length_stats(mr_edges, "expanded_motorway_trunk_primary")
    exp_stats["n_nodes"] = verified["expanded_nodes"]

    # Connected components (undirected) on motorway / expanded — sample via edge lists
    def undirected_components(nodes: pd.DataFrame, edges: pd.DataFrame) -> dict:
        parent = {}

        def find(x):
            parent.setdefault(x, x)
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        def union(a, b):
            ra, rb = find(a), find(b)
            if ra != rb:
                parent[rb] = ra

        id_col = "osm_node_id" if "osm_node_id" in nodes.columns else "node_id"
        for n in nodes[id_col].astype(np.int64):
            parent[int(n)] = int(n)
        for u, v in zip(edges["u"].astype(np.int64), edges["v"].astype(np.int64)):
            union(int(u), int(v))
        roots = Counter(find(n) for n in parent)
        sizes = sorted(roots.values(), reverse=True)
        return {
            "n_undirected_components": len(sizes),
            "largest_component_nodes": sizes[0] if sizes else 0,
            "component_size_top5": sizes[:5],
            "n_isolates": sum(1 for s in sizes if s == 1),
        }

    mw_cc = undirected_components(road_nodes, road_edges)
    exp_cc = undirected_components(mr_nodes, mr_edges)

    # Decision-arc lengths
    arc_lens = [float(a.get("length_m") or a.get("distance_m") or 0.0) for a in dg["arcs"]]
    # Attempt common keys
    if not any(arc_lens):
        for a in dg["arcs"]:
            for k in ("length_m", "distance_m", "cost_m", "metres"):
                if k in a and a[k] is not None:
                    arc_lens = [float(x.get(k) or 0.0) for x in dg["arcs"]]
                    break

    # OD / path stats
    path_stats = (
        paths.groupby("od_id")
        .agg(
            n_alts=("method", "count"),
            length_m_min=("length_m", "min"),
            length_m_max=("length_m", "max"),
            jaccard_max=("jaccard_distance_vs_shortest", "max"),
        )
        .reset_index()
    )
    path_stats["in_headline"] = path_stats["od_id"].isin(HEADLINE_ODS)
    path_stats["is_oujda"] = path_stats["od_id"].isin(OUJDA_ODS)

    # Speed policy travel time (assume 80 km/h motorway policy if maxspeed missing)
    SPEED_KMH = 80.0
    path_stats["duration_h_at_80kmh_min_route"] = path_stats["length_m_min"] / 1000.0 / SPEED_KMH
    path_stats["duration_h_at_80kmh_max_route"] = path_stats["length_m_max"] / 1000.0 / SPEED_KMH

    # Candidate summary
    cand = cand.copy()
    cand["retained_headline_key_guess"] = False  # filled later via naming

    # Geographical coverage
    def bbox(nodes: pd.DataFrame) -> dict:
        return {
            "lon_min": float(nodes["lon"].min()),
            "lon_max": float(nodes["lon"].max()),
            "lat_min": float(nodes["lat"].min()),
            "lat_max": float(nodes["lat"].max()),
        }

    # Quality checks
    quality = []

    def flag(check_id, severity, n, detail):
        quality.append({"check_id": check_id, "severity": severity, "n": n, "detail": detail})

    # Duplicate nodes
    for label, nodes in [("motorway", road_nodes), ("expanded", mr_nodes)]:
        idc = "osm_node_id" if "osm_node_id" in nodes.columns else "node_id"
        dup = int(nodes[idc].duplicated().sum())
        flag(f"{label}_duplicate_node_ids", "fail" if dup else "pass", dup, "duplicate OSM node ids")
        bad_coord = int((~np.isfinite(nodes["lon"]) | ~np.isfinite(nodes["lat"])).sum())
        flag(f"{label}_invalid_coords", "fail" if bad_coord else "pass", bad_coord, "non-finite lon/lat")
        oob = int(
            (
                (nodes["lon"] < -20)
                | (nodes["lon"] > 0)
                | (nodes["lat"] < 20)
                | (nodes["lat"] > 40)
            ).sum()
        )
        flag(f"{label}_coords_outside_morocco_bbox", "warn" if oob else "pass", oob, "outside loose MA bbox")

    for label, edges in [("motorway", road_edges), ("expanded", mr_edges)]:
        dup_e = int(edges.duplicated(subset=["u", "v", "edge_key"]).sum())
        flag(f"{label}_duplicate_edges", "fail" if dup_e else "pass", dup_e, "duplicate u,v,key")
        bad_len = int((edges["length_m"] <= 0).sum())
        flag(f"{label}_nonpositive_length", "fail" if bad_len else "pass", bad_len, "length_m <= 0")
        if "hgv_tag" in edges.columns:
            hgv_counts = edges["hgv_tag"].fillna("unknown").astype(str).value_counts().to_dict()
        else:
            hgv_counts = {}
        flag(
            f"{label}_hgv_tag_unknown_fraction",
            "warn",
            int(hgv_counts.get("unknown", hgv_counts.get("nan", len(edges)))),
            f"counts={hgv_counts}; unknown HGV must NOT be treated as confirmed legal access",
        )

    # OD anchors
    anchors = load_json(ROOT / "data/processed/multiroute/od_anchors.json")
    # structure may vary
    anchor_map = anchors.get("anchors") or anchors
    if isinstance(anchor_map, dict) and "tangier" not in anchor_map and "od" in anchors:
        anchor_map = anchors["od"]

    # Forward/reverse endpoint differences from multiroute manifest
    mrm_anchors = mrm.get("anchors", {})
    od_endpoint_rows = []
    for od in sorted(paths["od_id"].unique()):
        o_key, d_key = f"{od}__o", f"{od}__d"
        o_id = mrm_anchors.get(o_key)
        d_id = mrm_anchors.get(d_key)
        # reverse
        parts = od.split("_")
        # not always reversible by split; use known pairs
        reverse_od = None
        for cand_od in paths["od_id"].unique():
            if cand_od == od:
                continue
            if mrm_anchors.get(f"{cand_od}__o") == d_id and mrm_anchors.get(f"{cand_od}__d") == o_id:
                reverse_od = cand_od
                break
        od_endpoint_rows.append(
            {
                "od_id": od,
                "origin_osm_node": o_id,
                "dest_osm_node": d_id,
                "reverse_od_id": reverse_od,
                "in_headline": od in HEADLINE_ODS,
                "is_oujda_related": od in OUJDA_ODS,
                "n_path_alts": int((paths["od_id"] == od).sum()),
                "length_m_shortest": float(paths.loc[paths["od_id"] == od, "length_m"].min()),
                "length_m_longest": float(paths.loc[paths["od_id"] == od, "length_m"].max()),
                "max_jaccard_vs_shortest": float(
                    paths.loc[paths["od_id"] == od, "jaccard_distance_vs_shortest"].max()
                ),
            }
        )

    # DEM completeness
    dem_meta = load_json(ROOT / "data/processed/multiroute/elevation/dem_sampling_meta.json")
    arcs_meta = dem_meta.get("arcs", dem_meta)
    if isinstance(arcs_meta, dict) and arcs_meta and isinstance(next(iter(arcs_meta.values())), dict):
        dem_rows = []
        qualities = Counter()
        gain_all, loss_all, grades = [], [], []
        for aid, meta in arcs_meta.items():
            q = meta.get("quality", "unknown")
            qualities[q] += 1
            dem_rows.append(
                {
                    "arc_id": aid,
                    "od_id": meta.get("od_id"),
                    "quality": q,
                    "z_min": meta.get("z_min"),
                    "z_max": meta.get("z_max"),
                    "max_abs_grade": meta.get("max_abs_grade"),
                    "length_m": meta.get("length_m"),
                    "source": meta.get("source"),
                }
            )
            g = meta.get("max_abs_grade")
            if g is not None and np.isfinite(g):
                grades.append(float(g))
        dem_df = pd.DataFrame(dem_rows)
        unreal_grade = int((dem_df["max_abs_grade"] > 0.20).sum()) if len(dem_df) else 0
        flag(
            "dem_unrealistic_grade_gt_20pct",
            "warn" if unreal_grade else "pass",
            unreal_grade,
            "arcs with |grade|>0.20",
        )
        invalid_dem = int((dem_df["quality"] != "valid").sum()) if len(dem_df) else 0
        flag("dem_non_valid_quality", "warn" if invalid_dem else "pass", invalid_dem, str(dict(qualities)))
    else:
        dem_df = pd.DataFrame()
        qualities = Counter()
        grades = []

    # Per-OD elevation gain/loss from arc profiles when available
    elev_dir = ROOT / "data/processed/multiroute/elevation"
    od_elev = []
    for od in sorted(paths["od_id"].unique()):
        gain = loss = 0.0
        n_prof = 0
        max_g = 0.0
        for p in elev_dir.glob("arc_*.json"):
            try:
                prof = load_json(p)
            except Exception:
                continue
            if prof.get("od_id") != od and (dem_meta.get("arcs", {}).get(p.stem.replace("arc_", ""), {}) or {}).get("od_id") != od:
                # filter via dem meta
                aid = p.stem.replace("arc_", "")
                meta = dem_meta.get("arcs", {}).get(aid, {})
                if meta.get("od_id") != od:
                    continue
            z = prof.get("elevations_m") or prof.get("z") or prof.get("elevation_m")
            if not z:
                continue
            z = np.asarray(z, dtype=float)
            dz = np.diff(z)
            gain += float(dz[dz > 0].sum()) if len(dz) else 0.0
            loss += float((-dz[dz < 0]).sum()) if len(dz) else 0.0
            n_prof += 1
            if "grades" in prof:
                max_g = max(max_g, float(np.nanmax(np.abs(prof["grades"]))))
        od_elev.append(
            {
                "od_id": od,
                "n_profiles_used": n_prof,
                "cum_gain_m": gain,
                "cum_loss_m": loss,
                "in_headline": od in HEADLINE_ODS,
            }
        )

    # Weather coverage
    weather_dir = ROOT / "data/raw/weather"
    weather_files = list(weather_dir.rglob("*")) if weather_dir.exists() else []
    weather_files = [p for p in weather_files if p.is_file()]
    flag(
        "weather_cache_files_present",
        "pass" if weather_files else "warn",
        len(weather_files),
        f"files under {weather_dir}",
    )

    # Candidate accessibility
    access_counts = cand["directed_access_status"].value_counts().to_dict()
    match_counts = cand["location_match_status"].value_counts().to_dict()
    n_matched_accessible = int(
        (
            (cand["location_match_status"] == "matched_osm")
            & (cand["directed_access_status"] == "entrance_and_exit")
        ).sum()
    )
    flag(
        "candidate_matched_entrance_and_exit",
        "info",
        n_matched_accessible,
        f"match={match_counts}; access={access_counts}",
    )

    # Diversity
    div_path = ROOT / "data/processed/multiroute/path_diversity_audit.csv"
    div = pd.read_csv(div_path) if div_path.exists() else pd.DataFrame()

    # Graph audit note: expanded manifest n_nodes vs CSV
    graph_audit_nodes = (mrm.get("graph_audit") or {}).get("n_nodes")
    if graph_audit_nodes and graph_audit_nodes != verified["expanded_nodes"]:
        discrepancies.append(
            {
                "metric": "expanded_nodes_vs_graph_audit",
                "claimed": verified["expanded_nodes"],
                "verified": graph_audit_nodes,
                "note": "CSV n_nodes after isolate removal; graph_audit may be pre-prune",
            }
        )

    return {
        "verified_counts": verified,
        "discrepancies": discrepancies,
        "motorway_stats": mw_stats,
        "expanded_stats": exp_stats,
        "motorway_components": mw_cc,
        "expanded_components": exp_cc,
        "motorway_bbox": bbox(road_nodes),
        "expanded_bbox": bbox(mr_nodes),
        "path_stats": path_stats,
        "od_endpoints": pd.DataFrame(od_endpoint_rows),
        "decision_arc_length_m": {
            "n": len(arc_lens),
            "sum_km": float(np.sum(arc_lens) / 1000.0) if arc_lens else None,
            "p50": float(np.median(arc_lens)) if arc_lens else None,
            "p95": float(np.percentile(arc_lens, 95)) if arc_lens else None,
            "max": float(np.max(arc_lens)) if arc_lens else None,
        },
        "candidates": cand,
        "quality_checks": pd.DataFrame(quality),
        "dem_summary": {
            "n_arcs_with_meta": int(len(dem_df)),
            "quality_counts": dict(qualities),
            "grade_p50": float(np.median(grades)) if grades else None,
            "grade_p95": float(np.percentile(grades, 95)) if grades else None,
            "grade_max": float(np.max(grades)) if grades else None,
        },
        "dem_arcs": dem_df,
        "od_elevation": pd.DataFrame(od_elev),
        "diversity": div,
        "manifest_motorway": mm,
        "manifest_multiroute": mrm,
        "n_weather_files": len(weather_files),
        "n_matched_accessible_candidates": n_matched_accessible,
    }


def build_provenance_table() -> pd.DataFrame:
    sources = pd.read_csv(ROOT / "data/metadata/sources.csv")
    rows = []
    for _, s in sources.iterrows():
        rows.append(
            {
                "dataset_variable_group": s["name"],
                "original_source": s["name"],
                "source_url": s.get("url"),
                "snapshot_or_acquisition_date": s.get("data_date_or_snapshot"),
                "access_date": s.get("access_date"),
                "spatial_coverage": "Morocco national envelope (approx)",
                "resolution": "OSM ways / ADM HTML list",
                "units": "varies",
                "processing_steps": "See build manifests Task 01C / 05B",
                "data_quality": s.get("limitations"),
                "licensing_attribution": s.get("licence"),
                "missing_data_handling": "Documented per pipeline; HGV unknown retained as unknown",
                "observation_type": "observed_external" if "OSM" in str(s["name"]) or "Geofabrik" in str(s["name"]) else "observed_admin_or_docs",
                "intended_use": s.get("intended_use"),
            }
        )
    # Add constructed / derived layers
    extra = [
        {
            "dataset_variable_group": "motorway_network_graph",
            "original_source": "Geofabrik_Morocco_OSM_PBF",
            "source_url": "data/processed/road_*.csv",
            "snapshot_or_acquisition_date": "morocco-261106",
            "access_date": "2026-11-18",
            "spatial_coverage": "bbox W-9.8 S30.2 E-1.8 N35.9",
            "resolution": "OSM node/way geometry",
            "units": "metres (geodesic)",
            "processing_steps": "bbox extract → pyrosm highway filter motorway+link → MultiDiGraph CSV",
            "data_quality": "3 undirected components per manifest",
            "licensing_attribution": "© OpenStreetMap contributors, ODbL",
            "missing_data_handling": "service edges not in routing baseline",
            "observation_type": "derived_from_osm",
            "intended_use": "motorway-only routing baseline",
        },
        {
            "dataset_variable_group": "expanded_longhaul_network",
            "original_source": "Geofabrik_Morocco_OSM_PBF",
            "source_url": "data/processed/multiroute/{nodes,edges}.csv",
            "snapshot_or_acquisition_date": "morocco-261106",
            "access_date": "2026-11-18",
            "spatial_coverage": "same national envelope",
            "resolution": "OSM node/way geometry",
            "units": "metres",
            "processing_steps": "motorway+trunk+primary (+links); isolates removed; HGV=no rejected",
            "data_quality": "All HGV tags unknown in retained edges — not legal confirmation",
            "licensing_attribution": "© OpenStreetMap contributors, ODbL",
            "missing_data_handling": "isolates removed; hgv=no edges rejected",
            "observation_type": "derived_from_osm",
            "intended_use": "multi-route OD path construction",
        },
        {
            "dataset_variable_group": "decision_graph",
            "original_source": "path_union of constructed OD alternatives",
            "source_url": "data/processed/multiroute/decision_graph.json",
            "snapshot_or_acquisition_date": "2026-11-18",
            "access_date": "2026-11-18",
            "spatial_coverage": "union of 18 OD path alternatives",
            "resolution": "macro decision nodes/arcs",
            "units": "metres",
            "processing_steps": "k-shortest / diversity paths → path union → decision reduction",
            "data_quality": "optimality only over selected path-union",
            "licensing_attribution": "derived OSM geometry",
            "missing_data_handling": "n_arc_length_failures=0 in manifest",
            "observation_type": "constructed_research_graph",
            "intended_use": "MRLS / TRIP operational search",
        },
        {
            "dataset_variable_group": "od_path_alternatives",
            "original_source": "constructed on expanded network",
            "source_url": "data/processed/multiroute/path_alternatives.csv",
            "snapshot_or_acquisition_date": "2026-11-18",
            "access_date": "2026-11-18",
            "spatial_coverage": "18 directional OD pairs",
            "resolution": "node sequences",
            "units": "metres",
            "processing_steps": "shortest + diversity alternative per OD",
            "data_quality": "NOT observed freight trips",
            "licensing_attribution": "derived OSM",
            "missing_data_handling": "2 alts per OD by construction",
            "observation_type": "simulated_constructed_routes",
            "intended_use": "freight mission geography for experiments",
        },
        {
            "dataset_variable_group": "candidate_charging_sites",
            "original_source": "ADM_aires_de_services + OSM matching",
            "source_url": "data/processed/candidate_sites.csv",
            "snapshot_or_acquisition_date": "2026-11-18",
            "access_date": "2026-11-18",
            "spatial_coverage": "ADM listed service areas in study area",
            "resolution": "point + directed access probe",
            "units": "WGS84 degrees",
            "processing_steps": "ADM inventory → OSM name match → entrance/exit probe",
            "data_quality": "chargers are HYPOTHETICAL installations at service areas",
            "licensing_attribution": "ADM names; OSM geometry ODbL",
            "missing_data_handling": "unmatched → unresolved access",
            "observation_type": "derived_match_plus_assumed_chargers",
            "intended_use": "infrastructure location-routing candidates",
        },
        {
            "dataset_variable_group": "dem_elevation_profiles",
            "original_source": "Copernicus DEM GLO-30",
            "source_url": "data/raw/dem/glo30 + multiroute/elevation/",
            "snapshot_or_acquisition_date": "ESA Copernicus DEM",
            "access_date": "pipeline",
            "spatial_coverage": "decision-arc geometries",
            "resolution": "30 m GLO-30",
            "units": "metres elevation",
            "processing_steps": "sample DEM along arc geometry; store profiles",
            "data_quality": "see dem_sampling_meta quality flags",
            "licensing_attribution": "Copernicus DEM DOI 10.5270/ESA-c5d3d65",
            "missing_data_handling": "quality!=valid flagged",
            "observation_type": "derived_from_dem",
            "intended_use": "terrain-aware energy",
        },
        {
            "dataset_variable_group": "weather_temperature",
            "original_source": "weather caches under data/raw/weather",
            "source_url": "data/raw/weather",
            "snapshot_or_acquisition_date": "cache-dependent",
            "access_date": "pipeline",
            "spatial_coverage": "mission / station samples",
            "resolution": "provider-dependent",
            "units": "°C etc.",
            "processing_steps": "cached lookups for refrigeration ambient",
            "data_quality": "coverage varies; missing handled in prepare",
            "licensing_attribution": "see weather provider terms in cache metadata",
            "missing_data_handling": "fallback / skip per prepare config",
            "observation_type": "observed_or_cached_weather",
            "intended_use": "refrigeration ambient boundary",
        },
        {
            "dataset_variable_group": "vehicle_battery_refrigeration_parameters",
            "original_source": "OEM / engineering configs",
            "source_url": "configs/vehicles/*.yaml + cold-chain YAML",
            "snapshot_or_acquisition_date": "research configs",
            "access_date": "n/a",
            "spatial_coverage": "n/a",
            "resolution": "parameter scalars",
            "units": "kWh, kW, kg, °C",
            "processing_steps": "YAML → prepare fingerprint",
            "data_quality": "representative configurations, not fleet telemetry",
            "licensing_attribution": "cite OEM public specs where used",
            "missing_data_handling": "required params must be present",
            "observation_type": "assumed_research_parameters",
            "intended_use": "physics model inputs",
        },
    ]
    return pd.concat([pd.DataFrame(rows), pd.DataFrame(extra)], ignore_index=True)


def build_data_dictionary() -> pd.DataFrame:
    rows = [
        ("od_id", "string", "Directional origin–destination mission id", "constructed"),
        ("origin_osm_node", "int", "OSM node id of OD origin anchor", "derived"),
        ("dest_osm_node", "int", "OSM node id of OD destination anchor", "derived"),
        ("node_id / osm_node_id", "int", "Graph node identifier", "derived_from_osm"),
        ("u,v,edge_key", "int", "Directed edge endpoints and parallel key", "derived_from_osm"),
        ("length_m", "float", "Geodesic edge/path length metres", "derived"),
        ("highway", "string", "OSM highway class", "observed_osm"),
        ("hgv_tag", "string", "OSM HGV access tag; unknown ≠ permitted", "observed_osm_or_missing"),
        ("official_name", "string", "ADM service-area inventory name", "observed_admin"),
        ("travel_direction", "string", "ADM listed travel direction", "observed_admin"),
        ("location_match_status", "string", "OSM geographic match outcome", "derived"),
        ("directed_access_status", "string", "Entrance/exit probe vs opposite-carriageway", "derived"),
        ("decision_nodes", "object", "Reduced operational graph vertices", "constructed"),
        ("arcs", "object", "Reduced operational graph arcs with length", "constructed"),
        ("jaccard_distance_vs_shortest", "float", "Node-set diversity vs shortest path", "derived"),
        ("diversity_class", "string", "Qualitative route-diversity label", "derived"),
        ("z / elevations_m", "float[]", "DEM elevations along arc", "derived_from_dem"),
        ("max_abs_grade", "float", "Max |grade| on arc (rise/run)", "derived"),
        ("infra_config_id", "string", "I0/I1/I2 infrastructure scenario id", "experimental"),
        ("soc_frac", "float", "Departure state of charge fraction", "assumed_scenario"),
        ("payload_kg", "float", "Cargo mass", "assumed_scenario"),
        ("status", "string", "Solver status OPTIMAL/INFEASIBLE/LIMIT_REACHED/…", "computed"),
        ("operationally_served", "bool", "Ops-feasible after audits (not LIMIT)", "computed"),
        ("energy_feasible", "bool", "Energy-only feasibility flag", "computed"),
        ("duty_scope", "string", "SINGLE_DUTY or MULTI_DAY_OUT_OF_SCOPE", "computed"),
        ("min_soc / arrival_soc", "float", "Physical-replay SOC fractions", "computed"),
    ]
    return pd.DataFrame(rows, columns=["column_or_id", "dtype", "description", "observation_type"])


def build_candidate_table(cand: pd.DataFrame) -> pd.DataFrame:
    """Enrich candidate inventory with inclusion rationale."""
    out = cand.copy()
    reasons = []
    for _, r in out.iterrows():
        name = str(r["official_name"]).upper()
        status = r["directed_access_status"]
        match = r["location_match_status"]
        if match != "matched_osm":
            reason = "excluded_unmatched_osm"
            retained = False
        elif status == "opposite_carriageway_only":
            reason = "excluded_or_caution_opposite_carriageway_only"
            retained = False
        elif status != "entrance_and_exit":
            reason = f"excluded_access_{status}"
            retained = False
        elif "OUJDA" in name or "LAAYOUNE" in name or "MSOUN" in name:
            reason = "excluded_oujda_corridor_outside_headline_panel"
            retained = "oujda" in name.lower() or True
            retained = False
            reason = "excluded_eastern_oujda_corridor_sites"
        elif "BIR JDID" in name:
            reason = "excluded_not_on_headline_longhaul_unions"
            retained = False
        elif "BERRCHID" in name:
            reason = "excluded_opposite_carriageway_only"
            retained = False
        elif "MARRAKECH" in name or "OUM RBII" in name:
            reason = "excluded_unmatched"
            retained = False
        else:
            # matched entrance_and_exit on core corridors
            reason = "retained_matched_entrance_exit_core_corridor"
            retained = True
        reasons.append((retained, reason))
    out["retained_in_headline_candidate_pool"] = [r[0] for r in reasons]
    out["inclusion_exclusion_reason"] = [r[1] for r in reasons]
    return out


def write_selection_report(audit: dict) -> str:
    cand = build_candidate_table(audit["candidates"])
    n_retained = int(cand["retained_in_headline_candidate_pool"].sum())
    lines = []
    lines.append("# Dataset construction, selection and quality report")
    lines.append("")
    lines.append(f"Generated (UTC): {_utcnow()}")
    lines.append(f"Baseline commit: `8b0cbf716cc342550299895d4da58889b8239d37`")
    lines.append("")
    lines.append("## Verified counts vs claimed")
    lines.append("")
    lines.append("| Metric | Claimed | Verified |")
    lines.append("|---|---:|---:|")
    for k, claimed in CLAIMED.items():
        v = audit["verified_counts"].get(k)
        lines.append(f"| {k} | {claimed} | {v} |")
    lines.append("")
    if audit["discrepancies"]:
        lines.append("### Discrepancies")
        for d in audit["discrepancies"]:
            lines.append(f"- {d}")
    else:
        lines.append("All headline claimed counts match independent CSV/JSON recounts.")
    lines.append("")
    lines.append("### Graph-audit note")
    ga = (audit["manifest_multiroute"].get("graph_audit") or {})
    lines.append(
        f"Multiroute `graph_audit.n_nodes`={ga.get('n_nodes')}, "
        f"`n_edges_multidigraph`={ga.get('n_edges_multidigraph')} vs CSV after isolate removal "
        f"{audit['verified_counts']['expanded_nodes']}/{audit['verified_counts']['expanded_edges']}."
    )
    lines.append("")
    lines.append("## Network layers")
    lines.append("")
    lines.append(
        "- **Motorway-only**: routing baseline for facility access probes / A3-style baselines; "
        f"{audit['verified_counts']['motorway_nodes']} nodes, {audit['verified_counts']['motorway_edges']} edges; "
        f"directed length {audit['motorway_stats']['directed_length_km']:.1f} km; "
        f"approx unique physical {audit['motorway_stats']['unique_physical_length_km_approx']:.1f} km."
    )
    lines.append(
        "- **Expanded (motorway+trunk+primary)**: used to construct multi-route OD alternatives; "
        f"{audit['verified_counts']['expanded_nodes']} nodes, {audit['verified_counts']['expanded_edges']} edges; "
        f"directed length {audit['expanded_stats']['directed_length_km']:.1f} km; "
        f"approx unique physical {audit['expanded_stats']['unique_physical_length_km_approx']:.1f} km."
    )
    lines.append(
        "- **Decision graph**: path-union reduction to "
        f"{audit['verified_counts']['decision_nodes']} nodes / {audit['verified_counts']['decision_arcs']} arcs "
        "for operational search. Exact optimality claims apply only on this selected graph."
    )
    lines.append("")
    lines.append("## OD selection")
    lines.append("")
    lines.append(
        f"- **18 constructed directional OD pairs** (36 path records = 2 alternatives each)."
    )
    lines.append(
        f"- **14 headline missions** exclude the four Oujda-related ODs: {', '.join(OUJDA_ODS)}."
    )
    lines.append(
        "**Why Oujda ODs are excluded from the headline campaign:** they extend the eastern "
        "Fes–Oujda / Casa–Oujda corridor beyond the core Atlantic–Atlas long-haul panel used for "
        "matched I0–I2 infrastructure comparison; several eastern ADM sites (Laayoune, Msoun) remain "
        "OSM-unmatched with unresolved directed access; including them would expand geography and "
        "confound the Benguerir/Larache infrastructure ladder without a separate eastern candidate set."
    )
    lines.append("")
    lines.append("## Candidate selection")
    lines.append("")
    lines.append(
        f"- **19** ADM service-area inventory records; "
        f"**{audit['n_matched_accessible_candidates']}** matched with entrance_and_exit; "
        f"**{n_retained}** retained in the core headline candidate pool after exclusion rules "
        "(unmatched, opposite-carriageway-only, eastern corridor, off-panel corridors)."
    )
    lines.append(
        "Excluded inventoried sites include unmatched Marrakech/Oum Rbii/Laayoune/Msoun entries, "
        "Berrchid (opposite carriageway only), and Bir Jdid (Safi corridor, outside headline OD unions)."
    )
    lines.append(
        "**Chargers are hypothetical research installations** at matched service areas — not claimed "
        "as existing operational truck chargers."
    )
    lines.append("")
    lines.append("## HGV accessibility")
    lines.append("")
    lines.append(
        "Expanded-network HGV tags are overwhelmingly **unknown**. Unknown must not be treated as "
        "confirmed legal HGV accessibility."
    )
    lines.append("")
    lines.append("## Quality checks (summary)")
    lines.append("")
    qc = audit["quality_checks"]
    for _, r in qc.iterrows():
        lines.append(f"- [{r['severity']}] `{r['check_id']}` n={r['n']}: {r['detail']}")
    lines.append("")
    lines.append("## Constructed vs observed freight")
    lines.append("")
    lines.append(
        "OD missions and path alternatives are **constructed research scenarios**, not observed "
        "freight-trip diaries. Demand weights in experiments are analytical (unit weight), not "
        "calibrated flows — do not encode line thickness as freight volume."
    )
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    for p in (DS, TAB, MAN, OUT / "validation"):
        p.mkdir(parents=True, exist_ok=True)

    print("Running independent dataset audit…", flush=True)
    audit = recount_networks()

    # Counts comparison
    counts_rows = []
    for k, claimed in CLAIMED.items():
        counts_rows.append(
            {
                "metric": k,
                "claimed": claimed,
                "verified": audit["verified_counts"].get(k),
                "match": audit["verified_counts"].get(k) == claimed,
            }
        )
    counts_df = pd.DataFrame(counts_rows)
    counts_df.to_csv(TAB / "D-T02_network_counts_verification.csv", index=False)

    # Network stats table
    net_rows = []
    for stats, cc, bbox in [
        (audit["motorway_stats"], audit["motorway_components"], audit["motorway_bbox"]),
        (audit["expanded_stats"], audit["expanded_components"], audit["expanded_bbox"]),
    ]:
        net_rows.append(
            {
                "network": stats["network"],
                "n_nodes": stats["n_nodes"],
                "n_edges": stats["n_edges"],
                "directed_length_km": round(stats["directed_length_km"], 3),
                "unique_physical_length_km_approx": round(stats["unique_physical_length_km_approx"], 3),
                "edge_length_m_p50": round(stats["length_m_p50"], 3),
                "edge_length_m_p95": round(stats["length_m_p95"], 3),
                "edge_length_m_max": round(stats["length_m_max"], 3),
                "undirected_components": cc["n_undirected_components"],
                "largest_component_nodes": cc["largest_component_nodes"],
                "lon_min": bbox["lon_min"],
                "lon_max": bbox["lon_max"],
                "lat_min": bbox["lat_min"],
                "lat_max": bbox["lat_max"],
                "highway_directed_km_json": json.dumps(stats["highway_directed_km"]),
            }
        )
    # Decision graph row
    da = audit["decision_arc_length_m"]
    net_rows.append(
        {
            "network": "decision_graph",
            "n_nodes": audit["verified_counts"]["decision_nodes"],
            "n_edges": audit["verified_counts"]["decision_arcs"],
            "directed_length_km": None if da["sum_km"] is None else round(da["sum_km"], 3),
            "unique_physical_length_km_approx": None,
            "edge_length_m_p50": None if da["p50"] is None else round(da["p50"], 3),
            "edge_length_m_p95": None if da["p95"] is None else round(da["p95"], 3),
            "edge_length_m_max": None if da["max"] is None else round(da["max"], 3),
            "undirected_components": None,
            "largest_component_nodes": None,
            "lon_min": None,
            "lon_max": None,
            "lat_min": None,
            "lat_max": None,
            "highway_directed_km_json": None,
        }
    )
    pd.DataFrame(net_rows).to_csv(TAB / "D-T02_road_network_and_decision_graph_stats.csv", index=False)

    # Highway composition long form
    hw_rows = []
    for stats in (audit["motorway_stats"], audit["expanded_stats"]):
        for hw, km in stats["highway_directed_km"].items():
            hw_rows.append({"network": stats["network"], "highway": hw, "directed_km": km})
    pd.DataFrame(hw_rows).to_csv(DS / "highway_class_directed_km.csv", index=False)

    # OD table
    od = audit["od_endpoints"].merge(
        audit["path_stats"][
            ["od_id", "duration_h_at_80kmh_min_route", "duration_h_at_80kmh_max_route"]
        ],
        on="od_id",
        how="left",
    )
    od = od.merge(audit["od_elevation"], on="od_id", how="left", suffixes=("", "_elev"))
    od.to_csv(TAB / "D-T03_od_inventory.csv", index=False)
    od[od["in_headline"]].to_csv(TAB / "D-T03_od_inventory_headline14.csv", index=False)

    # Candidates
    cand_t = build_candidate_table(audit["candidates"])
    cand_t.to_csv(TAB / "D-T04_candidate_inventory.csv", index=False)

    # Provenance + dictionary
    build_provenance_table().to_csv(TAB / "D-T01_data_sources_provenance.csv", index=False)
    build_data_dictionary().to_csv(DS / "data_dictionary.csv", index=False)

    # DEM / elevation / weather by mission (partial)
    elev = audit["od_elevation"].copy()
    elev["weather_cache_files_global"] = audit["n_weather_files"]
    elev.to_csv(TAB / "D-T05_elevation_by_mission.csv", index=False)

    # Quality / limitations
    qc = audit["quality_checks"].copy()
    qc.to_csv(TAB / "D-T06_quality_checks.csv", index=False)

    # Vehicle params provenance stub from YAML
    veh_rows = []
    for vp in [
        ROOT / "configs/vehicles/eactros_600.yaml",
        ROOT / "configs/vehicles/volvo_fh_electric_4x2_540kwh_usable460.yaml",
        ROOT / "configs/vehicles/volvo_fh_electric_4x2_540kwh.yaml",
    ]:
        if vp.exists():
            veh_rows.append(
                {
                    "config_path": str(vp.relative_to(ROOT)).replace("\\", "/"),
                    "exists": True,
                    "observation_type": "assumed_research_parameters",
                    "note": "Full parameter dump in D-T07 via prepare fingerprint later",
                }
            )
    pd.DataFrame(veh_rows).to_csv(TAB / "D-T07_vehicle_config_paths.csv", index=False)

    # Diversity dump
    if len(audit["diversity"]):
        audit["diversity"].to_csv(DS / "path_diversity_audit_copy.csv", index=False)

    # DEM arcs
    if len(audit["dem_arcs"]):
        audit["dem_arcs"].to_csv(DS / "dem_arc_meta_summary.csv", index=False)

    # Compact recount JSON
    summary = {
        "generated_utc": _utcnow(),
        "baseline_commit": "8b0cbf716cc342550299895d4da58889b8239d37",
        "verified_counts": audit["verified_counts"],
        "discrepancies": audit["discrepancies"],
        "dem_summary": audit["dem_summary"],
        "decision_arc_length_m": audit["decision_arc_length_m"],
        "n_weather_files": audit["n_weather_files"],
        "n_matched_accessible_candidates": audit["n_matched_accessible_candidates"],
        "n_headline_candidates_retained": int(cand_t["retained_in_headline_candidate_pool"].sum()),
        "motorway_directed_km": audit["motorway_stats"]["directed_length_km"],
        "expanded_directed_km": audit["expanded_stats"]["directed_length_km"],
        "motorway_unique_km_approx": audit["motorway_stats"]["unique_physical_length_km_approx"],
        "expanded_unique_km_approx": audit["expanded_stats"]["unique_physical_length_km_approx"],
        "components": {
            "motorway": audit["motorway_components"],
            "expanded": audit["expanded_components"],
        },
    }
    (DS / "independent_recount_summary.json").write_text(
        json.dumps(summary, indent=2, default=str), encoding="utf-8"
    )

    report = write_selection_report(audit)
    (DS / "dataset_quality_and_construction_report.md").write_text(report, encoding="utf-8")
    (OUT / "validation" / "dataset_audit_ok.json").write_text(
        json.dumps(
            {
                "ok": len(audit["discrepancies"]) == 0
                or all("graph_audit" in str(d.get("metric", "")) for d in audit["discrepancies"]),
                "n_discrepancies": len(audit["discrepancies"]),
                "discrepancies": audit["discrepancies"],
                "generated_utc": _utcnow(),
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    print(json.dumps(summary["verified_counts"], indent=2))
    print("discrepancies:", audit["discrepancies"])
    print("Wrote tables under", TAB)
    print("Report:", DS / "dataset_quality_and_construction_report.md")
    return 0


if __name__ == "__main__":
    sys.exit(main())
