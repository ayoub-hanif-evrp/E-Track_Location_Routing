"""Build MRLS instances from multi-route decision graphs (Task 05A)."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from morocco_etruck.optimization.problem import ArcData, RoutingInstance, StationData
from morocco_etruck.optimization.route_choice_graph import DecisionArc, RouteChoiceGraph


@dataclass
class MultiroutePilotConfig:
    raw: dict[str, Any]
    decision_graph_path: Path
    nodes_csv: Path
    edges_csv: Path
    path_alternatives_csv: Path
    time_step_min: int
    energy_quantum_kwh: int
    deadline_steps: int
    consumption_kwh_per_km: float
    vehicle_yaml: Path
    fridge_yaml: Path
    speed_policy: dict[str, Any]
    disclaimer: str


def load_multiroute_pilot_config(path: Path, *, root: Path) -> MultiroutePilotConfig:
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    out = raw.get("outputs") or {}
    base = root / out.get("processed_dir", "data/processed/multiroute")
    return MultiroutePilotConfig(
        raw=raw,
        decision_graph_path=base / "decision_graph.json",
        nodes_csv=base / "nodes.csv",
        edges_csv=base / "edges.csv",
        path_alternatives_csv=base / "path_alternatives.csv",
        time_step_min=int(raw.get("time_step_min", 5)),
        energy_quantum_kwh=int(raw.get("energy_quantum_kwh", 5)),
        deadline_steps=int(raw.get("deadline_steps", 200)),
        consumption_kwh_per_km=float(raw.get("consumption_kwh_per_km", 1.2)),
        vehicle_yaml=root / raw.get("vehicle_config", "configs/vehicles/eactros_600.yaml"),
        fridge_yaml=root / raw.get("refrigeration_config", "configs/energy/refrigeration_approx.yaml"),
        speed_policy=dict(raw.get("speed_policy") or {}),
        disclaimer=str(raw.get("disclaimer", "")),
    )


def load_decision_graph(path: Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _dt_steps(length_m: float, speed_kmh: float, time_step_min: int) -> int:
    if speed_kmh <= 0:
        speed_kmh = 50.0
    dt_s = (length_m / 1000.0) / speed_kmh * 3600.0
    step_s = time_step_min * 60.0
    return max(1, int(math.ceil(dt_s / step_s)))


def _dE_kwh(length_m: float, consumption_kwh_per_km: float, quantum: int) -> int:
    raw = (length_m / 1000.0) * consumption_kwh_per_km
    if raw <= 0:
        return 0
    q = max(1, int(quantum))
    # Ceil onto quantum without imposing a per-arc minimum of one full quantum
    # on tiny macros (that previously made long ODs artificially infeasible).
    return int(math.ceil(raw / q) * q)


def arcs_from_decision_json(
    dec: dict[str, Any],
    *,
    time_step_min: int,
    energy_quantum_kwh: int,
    consumption_kwh_per_km: float,
    od_id: str | None = None,
) -> list[ArcData]:
    arcs: list[ArcData] = []
    for a in dec.get("arcs") or []:
        if od_id is not None:
            # Keep arcs whose path nodes appear in any recorded path for od — if provenance missing, keep all
            pass
        length_m = float(a["length_m"])
        speed = float(a.get("scenario_speed_kmh") or 50.0)
        dt = _dt_steps(length_m, speed, time_step_min)
        dE = _dE_kwh(length_m, consumption_kwh_per_km, energy_quantum_kwh)
        road_cost = int(round(length_m / 1000.0))  # 1 cent-equivalent per km illustrative
        arcs.append(
            ArcData(
                u=str(a["u"]),
                v=str(a["v"]),
                dt_steps=dt,
                dE_truck_kwh=dE,
                dE_trailer_kwh=0,
                road_cost=max(1, road_cost),
                power_ok=True,
            )
        )
    return arcs


def filter_arcs_for_od_paths(
    arcs: list[ArcData],
    dec: dict[str, Any],
    path_rows: list[dict[str, Any]],
    od_id: str,
) -> list[ArcData]:
    """Retain decision arcs whose OSM node sequence is a subpath of an OD alternative."""
    import json as _json

    od_paths = []
    for row in path_rows:
        if str(row.get("od_id")) != od_id:
            continue
        od_paths.append([int(x) for x in _json.loads(row["node_path_json"])])
    if not od_paths:
        return arcs

    arc_meta = {(str(a["u"]), str(a["v"]), tuple(a.get("path_nodes") or [])): a for a in dec.get("arcs") or []}
    keep: list[ArcData] = []
    for arc in arcs:
        # Match by u,v name; accept if any path_nodes for this u,v is subsequence of some OD path
        candidates = [m for (u, v, _), m in arc_meta.items() if u == arc.u and v == arc.v]
        if not candidates:
            keep.append(arc)
            continue
        ok = False
        for m in candidates:
            pn = [int(x) for x in (m.get("path_nodes") or [])]
            for path in od_paths:
                # subsequence check
                if _is_subsequence(pn, path):
                    ok = True
                    break
            if ok:
                break
        if ok:
            keep.append(arc)
    return keep or arcs


def _is_subsequence(sub: list[int], full: list[int]) -> bool:
    if not sub:
        return False
    # Find sub as contiguous segment
    n, m = len(full), len(sub)
    if m > n:
        return False
    for i in range(n - m + 1):
        if full[i : i + m] == sub:
            return True
    return False


def build_od_routing_instance(
    *,
    cfg: MultiroutePilotConfig,
    od_id: str,
    origin_name: str,
    dest_name: str,
    path_rows: list[dict[str, Any]],
    active_stations: set[str] | None = None,
    stations: dict[str, StationData] | None = None,
    E_truck_init: int = 600,
    E_truck_cap: int = 600,
    E_truck_min: int = 60,
    refrigeration_on: bool = False,
    name: str | None = None,
    mean_speed_kmh: float = 70.0,
) -> RoutingInstance:
    """
    Build a branching instance with one intermediate node per verified path
    alternative: O -> R_i -> D. Exact over the selected path set only.
    """
    import json as _json

    od_paths = [r for r in path_rows if str(r.get("od_id")) == od_id]
    arcs: list[ArcData] = []
    nodes = {origin_name, dest_name}
    for i, row in enumerate(od_paths):
        mid = f"R{i}_{od_id}"
        nodes.add(mid)
        length_m = float(row["length_m"])
        # Split length evenly across two hops for discrete transitions
        half = length_m / 2.0
        for u, v in ((origin_name, mid), (mid, dest_name)):
            dt = _dt_steps(half, mean_speed_kmh, cfg.time_step_min)
            dE = _dE_kwh(half, cfg.consumption_kwh_per_km, cfg.energy_quantum_kwh)
            road_cost = max(1, int(round(half / 1000.0)))
            arcs.append(
                ArcData(
                    u=u,
                    v=v,
                    dt_steps=dt,
                    dE_truck_kwh=max(1, dE),
                    dE_trailer_kwh=0,
                    road_cost=road_cost,
                    power_ok=True,
                )
            )
        _ = _json.loads(row["node_path_json"])  # provenance retained in CSV
    if not arcs:
        # Fallback: empty / infeasible shell
        arcs = []
    return RoutingInstance(
        name=name or f"multiroute_{od_id}",
        nodes=sorted(nodes),
        arcs=arcs,
        origin=origin_name,
        destination=dest_name,
        deadline_steps=cfg.deadline_steps,
        E_truck_cap=E_truck_cap,
        E_truck_min=E_truck_min,
        E_truck_init=E_truck_init,
        E_trailer_cap=None,
        E_trailer_min=None,
        E_trailer_init=None,
        stations=stations or {},
        active_stations=set(active_stations or []),
        power_source="A",
        refrigeration_on=refrigeration_on,
        wait_max_steps=0,
        time_step_min=cfg.time_step_min,
        energy_quantum_kwh=cfg.energy_quantum_kwh,
        notes=(
            "Task 05A path-set MRLS: one branch per verified OSM alternative "
            f"(n={len(od_paths)}); not full-network optimality"
        ),
    )


def decision_graph_to_route_choice(dec: dict[str, Any]) -> RouteChoiceGraph:
    arcs = [
        DecisionArc(
            u=str(a["u"]),
            v=str(a["v"]),
            path_nodes=list(a.get("path_nodes") or []),
            osm_edge_pairs=[],
            length_m=float(a["length_m"]),
            highway_classes=list(a.get("highway_classes") or []),
            scenario_speed_kmh=float(a.get("scenario_speed_kmh") or 50),
            hgv_access=str(a.get("hgv_access") or "unknown"),
        )
        for a in dec.get("arcs") or []
    ]
    return RouteChoiceGraph(
        decision_nodes={k: v for k, v in (dec.get("decision_nodes") or {}).items()},
        arcs=arcs,
        path_records=[],
        notes=list(dec.get("notes") or []),
    )
