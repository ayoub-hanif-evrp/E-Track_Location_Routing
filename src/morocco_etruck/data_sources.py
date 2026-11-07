"""Source registry, download/caching, hashing, and geographic OSM extraction."""

from __future__ import annotations

import hashlib
import json
import logging
import shutil
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import pandas as pd
import requests
import yaml

logger = logging.getLogger(__name__)

ACCESS_DATE = datetime.now(timezone.utc).date().isoformat()


@dataclass(frozen=True)
class SourceRecord:
    name: str
    url: str
    access_date: str
    data_date_or_snapshot: str
    licence: str
    intended_use: str
    limitations: str


def load_config(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f)


def project_root_from_config_path(config_path: Path) -> Path:
    # configs/pilot_corridor.yaml → repo root
    return config_path.resolve().parent.parent


def resolve_path(root: Path, relative: str) -> Path:
    return (root / relative).resolve()


def sha256_file(path: Path, chunk_size: int = 8 * 1024 * 1024) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def md5_file(path: Path, chunk_size: int = 8 * 1024 * 1024) -> str:
    h = hashlib.md5()
    with path.open("rb") as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def download_file(url: str, dest: Path, timeout: int = 120) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".partial")
    logger.info("Downloading %s → %s", url, dest)
    with requests.get(url, stream=True, timeout=timeout) as r:
        r.raise_for_status()
        with tmp.open("wb") as f:
            for chunk in r.iter_content(chunk_size=8 * 1024 * 1024):
                if chunk:
                    f.write(chunk)
    tmp.replace(dest)


def relpath_posix(path: Path, root: Path) -> str:
    """Repository-relative POSIX path when possible."""
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def ensure_geofabrik_pbf(
    config: dict[str, Any],
    root: Path,
    *,
    skip_download: bool = False,
) -> tuple[Path, str, dict[str, Any]]:
    """Download or reuse cached Geofabrik PBF; return path, sha256, meta."""
    osm_cfg = config["osm"]
    raw_dir = resolve_path(root, config["paths"]["raw_dir"])
    dest = raw_dir / osm_cfg["filename"]
    meta: dict[str, Any] = {
        "url": osm_cfg["download_url"],
        "filename": osm_cfg["filename"],
        "snapshot_label": osm_cfg["snapshot_label"],
        "data_timestamp_hint": osm_cfg.get("data_timestamp_hint"),
        "downloaded": False,
        "md5_expected": None,
        "md5_actual": None,
        "md5_ok": None,
        "path": relpath_posix(dest, root),
    }

    hash_sidecar = dest.with_suffix(dest.suffix + ".sha256")
    if dest.exists() and hash_sidecar.exists():
        stored = hash_sidecar.read_text(encoding="utf-8").strip().split()[0]
        actual = sha256_file(dest)
        if stored == actual:
            logger.info("Using cached PBF %s (sha256=%s)", dest.name, actual)
            meta["sha256"] = actual
            return dest, actual, meta
        if skip_download:
            raise FileNotFoundError(
                f"Cached PBF hash mismatch for {dest} and --skip-download prevents re-download"
            )
        logger.warning("Cached PBF hash mismatch; re-downloading")
    elif dest.exists() and not hash_sidecar.exists():
        actual = sha256_file(dest)
        hash_sidecar.write_text(f"{actual}  {dest.name}\n", encoding="utf-8")
        meta["sha256"] = actual
        logger.info("Computed missing SHA-256 sidecar for cached %s", dest.name)
        return dest, actual, meta

    if skip_download:
        raise FileNotFoundError(
            f"--skip-download set but usable cached PBF not found at {dest}"
        )

    download_file(osm_cfg["download_url"], dest)
    meta["downloaded"] = True

    # Optional Geofabrik MD5 check
    md5_url = osm_cfg.get("md5_url")
    if md5_url:
        try:
            resp = requests.get(md5_url, timeout=60)
            resp.raise_for_status()
            expected_md5 = resp.text.strip().split()[0]
            actual_md5 = md5_file(dest)
            meta["md5_expected"] = expected_md5
            meta["md5_actual"] = actual_md5
            meta["md5_ok"] = expected_md5.lower() == actual_md5.lower()
            if not meta["md5_ok"]:
                raise RuntimeError(
                    f"MD5 mismatch for {dest.name}: expected {expected_md5}, got {actual_md5}"
                )
            logger.info("Geofabrik MD5 verified for %s", dest.name)
        except requests.RequestException as exc:
            logger.warning("Could not fetch/verify Geofabrik MD5: %s", exc)
            meta["md5_ok"] = None

    digest = sha256_file(dest)
    hash_sidecar.write_text(f"{digest}  {dest.name}\n", encoding="utf-8")
    meta["sha256"] = digest
    logger.info("SHA-256 for %s: %s", dest.name, digest)
    return dest, digest, meta


def osmium_available() -> str | None:
    return shutil.which("osmium")


def extract_bbox_pbf(
    input_pbf: Path,
    output_pbf: Path,
    bbox: dict[str, float],
    root: Path | None = None,
) -> dict[str, Any]:
    """Extract a geographic subset. Prefer osmium-tool; fall back to pyrosm filter."""
    west, south, east, north = bbox["west"], bbox["south"], bbox["east"], bbox["north"]
    output_pbf.parent.mkdir(parents=True, exist_ok=True)
    root = root or output_pbf.parent.parent.parent
    info: dict[str, Any] = {
        "bbox": [west, south, east, north],
        "output": relpath_posix(output_pbf, root),
        "tool": None,
    }

    osmium = osmium_available()
    if osmium:
        cmd = [
            osmium,
            "extract",
            "-b",
            f"{west},{south},{east},{north}",
            "-s",
            "complete_ways",
            str(input_pbf),
            "-o",
            str(output_pbf),
            "-O",
        ]
        logger.info("Running: %s", " ".join(cmd))
        subprocess.run(cmd, check=True)
        info["tool"] = "osmium-extract"
        info["command"] = cmd
        return info

    # Fallback: pyrosm bbox filter → write filtered PBF if supported, else keep
    # an in-memory marker file listing that Python filtering will be used downstream.
    logger.warning(
        "osmium-tool not found on PATH; attempting pyrosm-based corridor filter"
    )
    try:
        from pyrosm import OSM  # type: ignore
    except ImportError as exc:
        raise RuntimeError(
            "Neither osmium-tool nor pyrosm is available. "
            "Install osmium-tool (e.g. conda-forge) or `pip install pyrosm`."
        ) from exc

    # pyrosm can filter by bbox when reading; we materialize a lightweight sidecar
    # that downstream graph builders will honour, and also try to write OSM XML
    # via osmium if somehow available later. For reproducibility we copy the
    # full file reference and store bbox for Python-side filtering.
    marker = output_pbf.with_suffix(".bbox.json")
    marker.write_text(
        json.dumps(
            {
                "source_pbf": relpath_posix(input_pbf, root),
                "bbox": [west, south, east, north],
                "note": "No osmium-tool; road_network will filter in Python from source_pbf",
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    info["tool"] = "pyrosm-python-bbox-filter"
    info["marker"] = relpath_posix(marker, root)
    info["source_pbf_for_filter"] = relpath_posix(input_pbf, root)
    # Create empty placeholder note file path used by build script
    if output_pbf.exists():
        output_pbf.unlink()
    # Symlink/copy not used for 240MB; downstream uses marker
    return info


def build_source_registry(config: dict[str, Any], osm_meta: dict[str, Any]) -> list[SourceRecord]:
    osm_cfg = config["osm"]
    sa = config["service_areas"]
    return [
        SourceRecord(
            name="ADM_aires_de_services",
            url=sa["source_url"],
            access_date=ACCESS_DATE,
            data_date_or_snapshot="live_html",
            licence="ADM website content; cite ADM for official names/partners; do not treat as open geospatial DB",
            intended_use="Official service-area names, fuel partners, and travel-direction labels for candidate sites",
            limitations="Public HTML lists names/partners only; no latitude/longitude published on this page",
        ),
        SourceRecord(
            name="ADM_A3_Casablanca_Agadir",
            url=sa["a3_page_url"],
            access_date=ACCESS_DATE,
            data_date_or_snapshot="live_html",
            licence="ADM website content; cite ADM",
            intended_use="Corridor context, section openings, interchange PK values",
            limitations="No service-area coordinates; some section length fields appear inconsistent on the page",
        ),
        SourceRecord(
            name="Geofabrik_Morocco_OSM_PBF",
            url=osm_meta.get("url", osm_cfg["download_url"]),
            access_date=ACCESS_DATE,
            data_date_or_snapshot=osm_meta.get("snapshot_label", osm_cfg["snapshot_label"]),
            licence="ODbL 1.0 (OpenStreetMap contributors via Geofabrik)",
            intended_use="Directed motorway geometry, attributes, and OSM facility matching",
            limitations="HGV/access tags incomplete; public extracts strip user/changeset metadata; snapshot may lag ground truth",
        ),
        SourceRecord(
            name="OpenStreetMap_copyright",
            url="https://www.openstreetmap.org/copyright",
            access_date=ACCESS_DATE,
            data_date_or_snapshot="n/a",
            licence="ODbL 1.0",
            intended_use="Licence and attribution obligations for OSM-derived databases",
            limitations="Share-alike applies to derivative databases; attribution required",
        ),
        SourceRecord(
            name="Osmium_extract_documentation",
            url="https://docs.osmcode.org/osmium/latest/osmium-extract.html",
            access_date=ACCESS_DATE,
            data_date_or_snapshot="docs_live",
            licence="Documentation (Osmium project)",
            intended_use="Document reproducible geographic extraction procedure",
            limitations="Windows binary may require conda-forge or WSL; fallback Python filter differs from complete_ways",
        ),
        SourceRecord(
            name="Geofabrik_Morocco_download_page",
            url="https://download.geofabrik.de/africa/morocco.html",
            access_date=ACCESS_DATE,
            data_date_or_snapshot=osm_cfg.get("data_timestamp_hint", "see_filename"),
            licence="ODbL 1.0",
            intended_use="Locate dated Morocco PBF snapshots and file sizes",
            limitations="latest vs dated filenames differ; always pin a dated file for papers",
        ),
    ]


def write_sources_csv(records: list[SourceRecord], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame([r.__dict__ for r in records])
    df.to_csv(path, index=False)
    logger.info("Wrote source registry %s (%d rows)", path, len(df))


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
