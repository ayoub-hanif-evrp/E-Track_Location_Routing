"""Joint charger-placement problem definitions (Task 04A/05A)."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


class PlacementConfigError(ValueError):
    """Invalid placement configuration (B&B bound assumptions violated)."""


@dataclass(frozen=True)
class PlacementSite:
    id: str
    direction: str
    station_key: str
    label: str


@dataclass(frozen=True)
class PlacementMission:
    id: str
    direction: str
    gcm: str
    terrain: str
    weather: str
    refrigeration: str
    power_source: str
    weight: float
    structural_candidate: bool = False


@dataclass
class PlacementConfig:
    raw: dict[str, Any]
    sites: list[PlacementSite]
    morocco_pilot_path: Path
    cents_to_currency: float
    crf: float
    budgets: list[dict[str, Any]]
    capex_scenarios: dict[str, dict[str, float]]
    demand_scenarios: dict[str, list[PlacementMission]]
    price_modes: list[str]
    baselines: dict[str, list[str]]
    solver_max_seconds: float
    solver_max_expansions: int
    outputs: dict[str, str]
    disclaimer: str = ""


def capital_recovery_factor(interest_rate: float, lifetime_years: int) -> float:
    r = float(interest_rate)
    n = int(lifetime_years)
    if n <= 0:
        raise PlacementConfigError("lifetime_years must be > 0")
    if r < -1e-15:
        raise PlacementConfigError("interest_rate must be >= 0 for illustrative CRF")
    if abs(r) < 1e-15:
        return 1.0 / n
    return r * (1.0 + r) ** n / ((1.0 + r) ** n - 1.0)


def validate_placement_config(cfg: PlacementConfig) -> None:
    """
    Enforce assumptions required by B&B coverage/secondary bounds and lex objective.

    Nonnegative site costs, strictly positive mission weights, unique IDs, valid
    budgets, and consistent CAPEX/baseline site references. Annualized CAPEX
    (CRF × CAPEX) and weighted operating cost (Σ w · C_var) share the same
    illustrative currency units via cents_to_currency.
    """
    site_ids = [s.id for s in cfg.sites]
    if len(site_ids) != len(set(site_ids)):
        raise PlacementConfigError("duplicate site ids")
    site_set = set(site_ids)

    if cfg.cents_to_currency <= 0:
        raise PlacementConfigError("cents_to_currency must be > 0 (currency unit scale)")
    if cfg.crf < 0:
        raise PlacementConfigError("CRF must be nonnegative")

    for sc_name, capex in cfg.capex_scenarios.items():
        for sid, cost in capex.items():
            if sid not in site_set:
                raise PlacementConfigError(
                    f"capex scenario {sc_name!r}: unknown site id {sid!r}"
                )
            if float(cost) < 0:
                raise PlacementConfigError(
                    f"capex scenario {sc_name!r}: site {sid!r} has negative CAPEX"
                )
        missing = site_set - set(capex)
        if missing:
            raise PlacementConfigError(
                f"capex scenario {sc_name!r}: missing sites {sorted(missing)}"
            )

    for dname, missions in cfg.demand_scenarios.items():
        mids = [m.id for m in missions]
        if len(mids) != len(set(mids)):
            raise PlacementConfigError(f"demand scenario {dname!r}: duplicate mission ids")
        for m in missions:
            if float(m.weight) <= 0:
                raise PlacementConfigError(
                    f"demand scenario {dname!r}: mission {m.id!r} weight must be > 0"
                )

    for bud in cfg.budgets:
        if "name" not in bud:
            raise PlacementConfigError("budget missing name")
        max_c = bud.get("max_capex")
        if max_c is not None and float(max_c) < 0:
            raise PlacementConfigError(
                f"budget {bud['name']!r}: max_capex must be >= 0 or null"
            )

    for bname, bl_sites in cfg.baselines.items():
        for sid in bl_sites:
            if sid not in site_set:
                raise PlacementConfigError(
                    f"baseline {bname!r}: unknown site id {sid!r}"
                )


def load_placement_config(path: str | Path, *, root: Path | None = None) -> PlacementConfig:
    root = root or Path(__file__).resolve().parents[3]
    path = Path(path)
    if not path.is_absolute():
        path = root / path
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    sites = [
        PlacementSite(
            id=str(s["id"]),
            direction=str(s["direction"]),
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
    demand: dict[str, list[PlacementMission]] = {}
    for dname, dcfg in raw["demand_scenarios"].items():
        demand[dname] = [
            PlacementMission(
                id=str(m["id"]),
                direction=str(m["direction"]),
                gcm=str(m["gcm"]),
                terrain=str(m["terrain"]),
                weather=str(m["weather"]),
                refrigeration=str(m["refrigeration"]),
                power_source=str(m["power_source"]),
                weight=float(m["weight"]),
                structural_candidate=bool(m.get("structural_candidate", False)),
            )
            for m in dcfg["missions"]
        ]
    morocco = raw["morocco_pilot_config"]
    morocco_path = Path(morocco) if Path(morocco).is_absolute() else root / morocco
    cfg = PlacementConfig(
        raw=raw,
        sites=sites,
        morocco_pilot_path=morocco_path,
        cents_to_currency=float(raw.get("cents_to_currency", 0.01)),
        crf=crf,
        budgets=list(raw["budgets"]),
        capex_scenarios=capex_scenarios,
        demand_scenarios=demand,
        price_modes=[str(x) for x in raw.get("price_modes", ["uniform"])],
        baselines={k: list(v) for k, v in raw.get("baselines", {}).items()},
        solver_max_seconds=float(raw.get("solver", {}).get("max_seconds", 60.0)),
        solver_max_expansions=int(raw.get("solver", {}).get("max_expansions", 500_000)),
        outputs=dict(raw.get("outputs", {})),
        disclaimer=str(raw.get("disclaimer", "")),
    )
    validate_placement_config(cfg)
    return cfg


def subset_capex(site_ids: set[str], capex: dict[str, float]) -> float:
    return sum(float(capex[s]) for s in site_ids)


def annualized_infra_cost(site_ids: set[str], capex: dict[str, float], crf: float) -> float:
    return subset_capex(site_ids, capex) * float(crf)


def budget_ok(site_ids: set[str], capex: dict[str, float], max_capex: float | None) -> bool:
    if max_capex is None:
        return True
    return subset_capex(site_ids, capex) <= float(max_capex) + 1e-9


@dataclass(order=True)
class LexScore:
    """Maximize coverage, then minimize secondary cost (negate coverage for sort)."""

    neg_coverage: float
    secondary_cost: float
    certified: bool = field(compare=False, default=True)

    @staticmethod
    def from_parts(coverage: float, secondary_cost: float, certified: bool = True) -> "LexScore":
        return LexScore(-float(coverage), float(secondary_cost), certified=certified)
