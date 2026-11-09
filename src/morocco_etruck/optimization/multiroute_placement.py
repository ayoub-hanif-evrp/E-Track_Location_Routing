"""Joint multi-route charger placement (Task 05C) — B&B over fixed path-union MRLS."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from morocco_etruck.optimization.placement_problem import (
    PlacementConfigError,
    PlacementSite,
    capital_recovery_factor,
    validate_placement_config,
)


@dataclass(frozen=True)
class MultiroutePlacementMission:
    id: str
    od_id: str
    weight: float
    E_truck_init: int
    refrigeration_on: bool = False
    terrain_mode: str = "flat"
    weather_id: str = "cool"
    gcm: str = "light"
    structural_candidate: bool = False


@dataclass
class MultiroutePlacementConfig:
    raw: dict[str, Any]
    sites: list[PlacementSite]
    multiroute_pilot_path: Path
    cents_to_currency: float
    crf: float
    budgets: list[dict[str, Any]]
    capex_scenarios: dict[str, dict[str, float]]
    demand_scenarios: dict[str, list[MultiroutePlacementMission]]
    price_modes: list[str]
    baselines: dict[str, list[str]]
    solver_max_seconds: float
    solver_max_expansions: int
    outputs: dict[str, str]
    disclaimer: str = ""
    node_limit: int | None = None
    time_limit_sec: float | None = None


def _as_placement_config_shim(cfg: MultiroutePlacementConfig):
    """Reuse validate_placement_config by projecting onto PlacementConfig shape."""
    from morocco_etruck.optimization.placement_problem import PlacementConfig, PlacementMission

    missions_map = {
        name: [
            PlacementMission(
                id=m.id,
                direction=m.od_id,
                gcm=m.gcm,
                terrain=m.terrain_mode,
                weather=m.weather_id,
                refrigeration="on" if m.refrigeration_on else "off",
                power_source="A",
                weight=m.weight,
                structural_candidate=m.structural_candidate,
            )
            for m in missions
        ]
        for name, missions in cfg.demand_scenarios.items()
    }
    return PlacementConfig(
        raw=cfg.raw,
        sites=cfg.sites,
        morocco_pilot_path=cfg.multiroute_pilot_path,
        cents_to_currency=cfg.cents_to_currency,
        crf=cfg.crf,
        budgets=cfg.budgets,
        capex_scenarios=cfg.capex_scenarios,
        demand_scenarios=missions_map,
        price_modes=cfg.price_modes,
        baselines=cfg.baselines,
        solver_max_seconds=cfg.solver_max_seconds,
        solver_max_expansions=cfg.solver_max_expansions,
        outputs=cfg.outputs,
        disclaimer=cfg.disclaimer,
    )


def load_multiroute_placement_config(
    path: str | Path, *, root: Path | None = None
) -> MultiroutePlacementConfig:
    root = root or Path(__file__).resolve().parents[3]
    path = Path(path)
    if not path.is_absolute():
        path = root / path
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    sites = [
        PlacementSite(
            id=str(s["id"]),
            direction=str(s.get("direction", "shared")),
            station_key=str(s["station_key"]),
            label=str(s.get("label", s["id"])),
        )
        for s in raw["sites"]
    ]
    ann = raw["annualization"]
    crf = capital_recovery_factor(ann["interest_rate"], ann["lifetime_years"])
    capex_scenarios = {
        name: {str(k): float(v) for k, v in sc["site_capex"].items()}
        for name, sc in raw["capex_scenarios"].items()
    }
    demand: dict[str, list[MultiroutePlacementMission]] = {}
    for dname, dcfg in raw["demand_scenarios"].items():
        demand[dname] = [
            MultiroutePlacementMission(
                id=str(m["id"]),
                od_id=str(m["od_id"]),
                weight=float(m["weight"]),
                E_truck_init=int(m.get("E_truck_init", 200)),
                refrigeration_on=bool(m.get("refrigeration_on", False)),
                terrain_mode=str(m.get("terrain_mode", "flat")),
                weather_id=str(m.get("weather_id", "cool")),
                gcm=str(m.get("gcm", "light")),
                structural_candidate=bool(m.get("structural_candidate", False)),
            )
            for m in dcfg["missions"]
        ]
    pilot = raw.get("multiroute_pilot_config", "configs/optimization/multiroute_pilot.yaml")
    pilot_path = Path(pilot) if Path(pilot).is_absolute() else root / pilot
    solver = raw.get("solver") or {}
    cfg = MultiroutePlacementConfig(
        raw=raw,
        sites=sites,
        multiroute_pilot_path=pilot_path,
        cents_to_currency=float(raw.get("cents_to_currency", 0.01)),
        crf=crf,
        budgets=list(raw["budgets"]),
        capex_scenarios=capex_scenarios,
        demand_scenarios=demand,
        price_modes=[str(x) for x in raw.get("price_modes", ["uniform"])],
        baselines={k: list(v) for k, v in (raw.get("baselines") or {}).items()},
        solver_max_seconds=float(solver.get("max_seconds", 90.0)),
        solver_max_expansions=int(solver.get("max_expansions", 800_000)),
        outputs=dict(raw.get("outputs") or {}),
        disclaimer=str(raw.get("disclaimer", "")),
        node_limit=solver.get("node_limit"),
        time_limit_sec=solver.get("time_limit_sec"),
    )
    validate_placement_config(_as_placement_config_shim(cfg))
    # Extra: station keys unique
    keys = [s.station_key for s in cfg.sites]
    if len(keys) != len(set(keys)):
        raise PlacementConfigError("duplicate station_key in multiroute placement sites")
    return cfg
