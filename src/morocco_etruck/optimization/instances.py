"""Load synthetic routing instances from YAML."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from morocco_etruck.optimization.problem import ArcData, RoutingInstance, StationData


def _arc(d: dict[str, Any]) -> ArcData:
    return ArcData(
        u=str(d["u"]),
        v=str(d["v"]),
        dt_steps=int(d["dt_steps"]),
        dE_truck_kwh=int(d["dE_truck_kwh"]),
        dE_trailer_kwh=int(d.get("dE_trailer_kwh", 0)),
        road_cost=int(d["road_cost"]),
        power_ok=bool(d.get("power_ok", True)),
    )


def _station(d: dict[str, Any]) -> StationData:
    return StationData(
        node=str(d["node"]),
        power_kw=float(d["power_kw"]),
        eta=float(d.get("eta", 1.0)),
        price_cents_per_grid_kwh=int(d.get("price_cents_per_grid_kwh", 1)),
        compatible=bool(d.get("compatible", True)),
    )


def instance_from_dict(d: dict[str, Any]) -> RoutingInstance:
    stations = {_station(s).node: _station(s) for s in d.get("stations", [])}
    trailer = d.get("trailer")
    return RoutingInstance(
        name=str(d["name"]),
        nodes=[str(n) for n in d["nodes"]],
        arcs=[_arc(a) for a in d["arcs"]],
        origin=str(d["origin"]),
        destination=str(d["destination"]),
        deadline_steps=int(d["deadline_steps"]),
        E_truck_cap=int(d["E_truck_cap"]),
        E_truck_min=int(d["E_truck_min"]),
        E_truck_init=int(d["E_truck_init"]),
        E_trailer_cap=int(trailer["cap"]) if trailer else None,
        E_trailer_min=int(trailer["min"]) if trailer else None,
        E_trailer_init=int(trailer["init"]) if trailer else None,
        stations=stations,
        active_stations=set(str(x) for x in d.get("active_stations", [])),
        power_source=d.get("power_source", "A"),
        refrigeration_on=bool(d.get("refrigeration_on", False)),
        aux_kwh_per_step=int(d.get("aux_kwh_per_step", 0)),
        tru_kwh_per_step=int(d.get("tru_kwh_per_step", 0)),
        wait_max_steps=int(d.get("wait_max_steps", 0)),
        time_step_min=int(d.get("time_step_min", 5)),
        energy_quantum_kwh=int(d.get("energy_quantum_kwh", 1)),
        notes=str(d.get("notes", "")),
        expected=dict(d.get("expected", {})),
    )


def load_synthetic_instances(path: str | Path) -> list[RoutingInstance]:
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    return [instance_from_dict(item) for item in raw["instances"]]
