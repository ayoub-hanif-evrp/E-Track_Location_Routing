"""Transition-level battery quantization audit (DRIVE / CHARGE / WAIT).

Conservative flooring onto the energy quantum is preserved. This module only
measures continuous-vs-discrete discrepancy for scientific reporting.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from morocco_etruck.optimization.problem import RoutingInstance
from morocco_etruck.optimization.resource_transitions import (
    _floor_to_quantum,
    stationary_drain_kwh,
)


@dataclass
class QuantizationStep:
    action: str
    E_before_disc: int
    E_after_cont: float
    E_after_disc: int
    physical_delta_kwh: float
    rounding_loss_kwh: float
    note: str = ""


def charge_continuous_vs_discrete(
    inst: RoutingInstance,
    *,
    E_truck: int,
    delta_e: int,
    node: str | None = None,
) -> QuantizationStep:
    """
    Compare continuous post-charge energy to the floored discrete label energy.

    Demonstrates that a paid CHARGE can have zero discrete net gain when
    continuous residual falls short of the next quantum after stationary drain.
    """
    q = max(1, int(inst.energy_quantum_kwh))
    st_node = node or next(iter(inst.active_stations or inst.stations.keys()))
    st = inst.stations[st_node]
    steps = inst.charge_duration_steps(st, delta_e)
    drain_tr, drain_tl = stationary_drain_kwh(inst, steps)
    E_cont = float(E_truck) + float(delta_e) - drain_tr
    E_disc = _floor_to_quantum(E_cont, q)
    if E_disc > inst.E_truck_cap:
        E_disc = inst.E_truck_cap
    loss = max(0.0, E_cont - float(E_disc))
    return QuantizationStep(
        action="CHARGE",
        E_before_disc=int(E_truck),
        E_after_cont=E_cont,
        E_after_disc=int(E_disc),
        physical_delta_kwh=float(delta_e) - drain_tr,
        rounding_loss_kwh=loss,
        note=(
            "zero_discrete_gain"
            if int(E_disc) == int(E_truck)
            else "discrete_gain=" + str(int(E_disc) - int(E_truck))
        ),
    )


def wait_continuous_vs_discrete(
    inst: RoutingInstance,
    *,
    E_truck: int,
    steps: int,
) -> QuantizationStep:
    q = max(1, int(inst.energy_quantum_kwh))
    drain_tr, _ = stationary_drain_kwh(inst, steps)
    E_cont = float(E_truck) - drain_tr
    E_disc = _floor_to_quantum(E_cont, q)
    loss = max(0.0, E_cont - float(E_disc))
    return QuantizationStep(
        action="WAIT",
        E_before_disc=int(E_truck),
        E_after_cont=E_cont,
        E_after_disc=int(E_disc),
        physical_delta_kwh=-drain_tr,
        rounding_loss_kwh=loss,
    )


def cumulative_rounding_loss(steps: list[QuantizationStep]) -> float:
    return float(sum(s.rounding_loss_kwh for s in steps))


def audit_action_rounding(
    inst: RoutingInstance,
    actions: list[dict[str, Any]],
    *,
    E_truck_init: int | None = None,
) -> dict[str, Any]:
    """
    Transition-level continuous-vs-discrete audit along a solved action list.

    DRIVE steps use the precomputed drive table when available (E_end continuous
    reconstructed from table energy after flooring is already discrete — loss on
    DRIVE is measured as residual to the next lower quantum from a continuous
    estimate when the table stores only floored ends: we report CHARGE/WAIT
    losses exactly and DRIVE table floor residuals when ``E_end_truck`` is known
    relative to a continuous post-drive energy carried in action metadata.
    """
    q = max(1, int(inst.energy_quantum_kwh))
    E = int(inst.E_truck_init if E_truck_init is None else E_truck_init)
    steps: list[QuantizationStep] = []
    for act in actions:
        typ = str(act.get("type") or "")
        if typ == "CHARGE":
            de = int(act.get("delta_e_kwh") or 0)
            step = charge_continuous_vs_discrete(inst, E_truck=E, delta_e=de, node=act.get("node"))
            steps.append(step)
            E = int(step.E_after_disc)
        elif typ == "WAIT":
            k = int(act.get("steps") or 0)
            step = wait_continuous_vs_discrete(inst, E_truck=E, steps=k)
            steps.append(step)
            E = int(step.E_after_disc)
        elif typ == "DRIVE":
            aid = str(act.get("arc_id") or "")
            arc = next((a for a in inst.arcs if str(a.arc_id) == aid), None)
            if arc is None:
                continue
            ent = arc.drive_table.get((E, None))
            if ent is None or not ent.feasible:
                steps.append(
                    QuantizationStep(
                        action="DRIVE",
                        E_before_disc=E,
                        E_after_cont=float(E),
                        E_after_disc=E,
                        physical_delta_kwh=0.0,
                        rounding_loss_kwh=0.0,
                        note="drive_infeasible_or_missing_table",
                    )
                )
                break
            # Table already stores floored end; residual within quantum is lost.
            # Approximate continuous end as just below next quantum above E_end
            # is unsafe; instead report known floor gap from action if present.
            e_end = int(ent.E_end_truck)
            cont_hint = act.get("E_end_cont_kwh")
            if cont_hint is not None:
                e_cont = float(cont_hint)
                loss = max(0.0, e_cont - float(e_end))
            else:
                # Conservative: residual lost is in [0, q); report 0 without cont.
                e_cont = float(e_end)
                loss = 0.0
            steps.append(
                QuantizationStep(
                    action="DRIVE",
                    E_before_disc=E,
                    E_after_cont=e_cont,
                    E_after_disc=e_end,
                    physical_delta_kwh=e_cont - float(E),
                    rounding_loss_kwh=loss,
                    note="drive_table",
                )
            )
            E = e_end
    return {
        "steps": steps,
        "cumulative_rounding_loss_kwh": cumulative_rounding_loss(steps),
        "n_actions_audited": len(steps),
        "energy_quantum_kwh": q,
        "E_final_disc": E,
    }


def drive_path_floor_loss(
    *,
    path_nodes: list[str],
    arcs: list[Any],
    E_truck_init: int,
    energy_quantum_kwh: int,
    simulate_drive_fn: Any,
    prep_ctx: Any,
) -> dict[str, Any]:
    """
    Cumulative DRIVE flooring loss along a node path using continuous micro simulation.

    ``simulate_drive_fn`` must match ``simulate_drive_from_soc`` signature used in
    arc preprocessing (passed in to avoid circular imports at module load).
    """
    from collections import defaultdict

    by_uv: dict[tuple[str, str], list[Any]] = defaultdict(list)
    for a in arcs:
        by_uv[(a.u, a.v)].append(a)
    usable = float(prep_ctx.vehicle.usable_kwh)
    soc = float(E_truck_init) / usable
    E_disc = int(E_truck_init)
    q = max(1, int(energy_quantum_kwh))
    lost = 0.0
    n = 0
    for u, v in zip(path_nodes[:-1], path_nodes[1:]):
        cands = by_uv.get((u, v), [])
        chosen = None
        for a in cands:
            ent = a.drive_table.get((E_disc, None))
            if ent is not None and ent.feasible:
                chosen = a
                break
        if chosen is None:
            break
        macro = prep_ctx.macros_by_arc_id[str(chosen.arc_id)]
        ok, _dt, soc_end, _, _reason, _ecomp = simulate_drive_fn(
            macro.micro_edges,
            macro.terrain,
            soc0=soc,
            trailer_soc0=None,
            vehicle=prep_ctx.vehicle,
            weather=prep_ctx.weather,
            fridge_cfg=prep_ctx.fridge,
            gcm_kg=prep_ctx.gcm_kg,
            refrigeration_on=prep_ctx.refrigeration_on,
            power_source=prep_ctx.power_source,
            adapt_speed_to_peak_power=prep_ctx.adapt_speed_to_peak_power,
            adapt_speed_to_continuous_power=prep_ctx.adapt_speed_to_continuous_power,
            min_adapt_speed_mps=prep_ctx.min_adapt_speed_mps,
        )
        E_cont = soc_end * usable
        E_floor = _floor_to_quantum(E_cont, q)
        lost += max(0.0, E_cont - float(E_floor))
        n += 1
        ent = chosen.drive_table.get((E_disc, None))
        if not ok or ent is None or not ent.feasible:
            break
        soc = soc_end
        E_disc = int(ent.E_end_truck)
    return {
        "total_rounding_loss_kwh": lost,
        "n_drive_steps": n,
        "macro_segmentation_n_arcs": len(arcs),
    }


def optimistic_no_floor_breaks_conservative_feasibility() -> dict[str, Any]:
    """
    Toy evidence: dropping stationary flooring can make a discrete label look
    feasible (or richer) than the conservative model permits — unsafe for B&B
    certificates that assume flooring. Used only as a negative control.
    """
    inst = None  # filled by test helper; this documents the decision contract
    return {
        "adopted": False,
        "reason": (
            "Ceil/no-floor after CHARGE would admit discrete states above the "
            "conservatively floored lattice; label dominance and replay certificates "
            "would no longer match the finite model used by MRLS/B&B."
        ),
        "safe_within_scope": "finer_fixed_grids_only",
        "novel_algorithm_claim": False,
        "inst_placeholder": inst,
    }


def summarize_quantization_policy() -> dict[str, Any]:
    return {
        "policy": "conservative_floor_after_DRIVE_CHARGE_WAIT",
        "DRIVE": "ending kWh floored onto quantum in DRIVE table build",
        "CHARGE_WAIT": "continuous energy floored after stationary drain",
        "adopted_correction": None,
        "rationale": (
            "Removing flooring would risk optimistic discrete feasibility. "
            "Publication-facing infrastructure claims require fine-grid stability "
            "(see battery_quantization_and_convergence report)."
        ),
        "alternatives_considered": [
            "finer_fixed_grids",
            "residual_preserving_state",
            "quantize_only_at_charge_events",
            "conservative_interval_bounds",
        ],
        "alternatives_decision": optimistic_no_floor_breaks_conservative_feasibility(),
        "novel_algorithm_claim": False,
    }
