"""Transition-level battery quantization audit (DRIVE / CHARGE / WAIT).

Conservative flooring onto the energy quantum is preserved. This module only
measures continuous-vs-discrete discrepancy for scientific reporting.

``drive_path_floor_loss`` (node-path walk) is SUPERSEDED by
``audit_solved_actions_exact`` which uses the exact ordered action list.
"""

from __future__ import annotations

from dataclasses import dataclass, field
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
    arc_id: str | None = None
    node: str | None = None
    cap_truncation_kwh: float = 0.0
    zero_net_discrete_gain: bool = False


@dataclass
class ActionAuditResult:
    ok: bool
    steps: list[QuantizationStep] = field(default_factory=list)
    cumulative_floor_loss_kwh: float = 0.0
    cumulative_cap_truncation_kwh: float = 0.0
    n_drive: int = 0
    n_charge: int = 0
    n_wait: int = 0
    n_zero_net_charge: int = 0
    E_final_disc: int | None = None
    failure_reason: str | None = None
    n_actions_input: int = 0
    n_actions_audited: int = 0


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
    drain_tr, _drain_tl = stationary_drain_kwh(inst, steps)
    E_cont = float(E_truck) + float(delta_e) - drain_tr
    E_capped = min(E_cont, float(inst.E_truck_cap))
    cap_trunc = max(0.0, E_cont - E_capped)
    E_disc = _floor_to_quantum(E_capped, q)
    if E_disc > inst.E_truck_cap:
        E_disc = inst.E_truck_cap
    loss = max(0.0, E_capped - float(E_disc))
    zero = int(E_disc) == int(E_truck)
    return QuantizationStep(
        action="CHARGE",
        E_before_disc=int(E_truck),
        E_after_cont=E_cont,
        E_after_disc=int(E_disc),
        physical_delta_kwh=float(delta_e) - drain_tr,
        rounding_loss_kwh=loss,
        note=("zero_discrete_gain" if zero else f"discrete_gain={int(E_disc) - int(E_truck)}"),
        node=str(st_node),
        cap_truncation_kwh=cap_trunc,
        zero_net_discrete_gain=zero,
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


def audit_solved_actions_exact(
    inst: RoutingInstance,
    actions: list[dict[str, Any]],
    *,
    prep_ctx: Any,
    simulate_drive_fn: Any,
    E_truck_init: int | None = None,
    expected_final_E_disc: int | None = None,
) -> ActionAuditResult:
    """
    Authoritative complete-trip rounding audit on the exact ordered action list.

    - Every DRIVE uses its exact ``arc_id`` (never an arbitrary (u,v) match).
    - Discrete state is advanced via the drive table / CHARGE/WAIT floor rules.
    - Continuous energy for each DRIVE is re-simulated from the discrete SOC at
      the start of that action (matching table-build semantics).
    - Missing arc / missing table / action-count mismatch ⇒ ``ok=False``.
    """
    q = max(1, int(inst.energy_quantum_kwh))
    usable = float(prep_ctx.vehicle.usable_kwh)
    E_disc = int(inst.E_truck_init if E_truck_init is None else E_truck_init)
    arcs_by_id = {str(a.arc_id): a for a in inst.arcs}
    steps: list[QuantizationStep] = []
    n_drive = n_charge = n_wait = n_zero = 0
    floor_loss = 0.0
    cap_trunc = 0.0

    for idx, act in enumerate(actions):
        typ = str(act.get("type") or "")
        if typ == "DRIVE":
            aid = str(act.get("arc_id") or "")
            if not aid or aid not in arcs_by_id:
                return ActionAuditResult(
                    ok=False,
                    steps=steps,
                    cumulative_floor_loss_kwh=floor_loss,
                    cumulative_cap_truncation_kwh=cap_trunc,
                    n_drive=n_drive,
                    n_charge=n_charge,
                    n_wait=n_wait,
                    n_zero_net_charge=n_zero,
                    E_final_disc=E_disc,
                    failure_reason=f"missing_exact_arc_id_at_action_{idx}:{aid!r}",
                    n_actions_input=len(actions),
                    n_actions_audited=len(steps),
                )
            arc = arcs_by_id[aid]
            macro = prep_ctx.macros_by_arc_id.get(aid)
            if macro is None:
                return ActionAuditResult(
                    ok=False,
                    steps=steps,
                    cumulative_floor_loss_kwh=floor_loss,
                    cumulative_cap_truncation_kwh=cap_trunc,
                    n_drive=n_drive,
                    n_charge=n_charge,
                    n_wait=n_wait,
                    n_zero_net_charge=n_zero,
                    E_final_disc=E_disc,
                    failure_reason=f"missing_macro:{aid}",
                    n_actions_input=len(actions),
                    n_actions_audited=len(steps),
                )
            ent = arc.drive_table.get((E_disc, None))
            if ent is None or not ent.feasible:
                return ActionAuditResult(
                    ok=False,
                    steps=steps,
                    cumulative_floor_loss_kwh=floor_loss,
                    cumulative_cap_truncation_kwh=cap_trunc,
                    n_drive=n_drive,
                    n_charge=n_charge,
                    n_wait=n_wait,
                    n_zero_net_charge=n_zero,
                    E_final_disc=E_disc,
                    failure_reason=f"drive_table_infeasible:{aid}@E={E_disc}",
                    n_actions_input=len(actions),
                    n_actions_audited=len(steps),
                )
            soc0 = float(E_disc) / usable
            ok, _dt, soc_end, _, reason, _ecomp = simulate_drive_fn(
                macro.micro_edges,
                macro.terrain,
                soc0=soc0,
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
            E_cont = float(soc_end) * usable
            E_cap = min(E_cont, float(inst.E_truck_cap))
            this_cap = max(0.0, E_cont - E_cap)
            E_floor = _floor_to_quantum(E_cap, q)
            this_floor = max(0.0, E_cap - float(E_floor))
            E_after = int(ent.E_end_truck)
            # Table end should equal floored continuous under same physics
            note = "drive_ok"
            if not ok:
                note = f"cont_sim_violation:{reason}"
            if abs(E_after - E_floor) > max(1, q):
                note = f"table_vs_floor_gap:{E_after}-vs-{E_floor}"
            steps.append(
                QuantizationStep(
                    action="DRIVE",
                    E_before_disc=E_disc,
                    E_after_cont=E_cont,
                    E_after_disc=E_after,
                    physical_delta_kwh=E_cont - float(E_disc),
                    rounding_loss_kwh=this_floor,
                    note=note,
                    arc_id=aid,
                    cap_truncation_kwh=this_cap,
                )
            )
            floor_loss += this_floor
            cap_trunc += this_cap
            E_disc = E_after
            n_drive += 1
        elif typ == "CHARGE":
            de = int(act.get("delta_e_kwh") or 0)
            node = act.get("node")
            step = charge_continuous_vs_discrete(inst, E_truck=E_disc, delta_e=de, node=node)
            steps.append(step)
            floor_loss += step.rounding_loss_kwh
            cap_trunc += step.cap_truncation_kwh
            if step.zero_net_discrete_gain:
                n_zero += 1
            E_disc = int(step.E_after_disc)
            n_charge += 1
        elif typ == "WAIT":
            k = int(act.get("steps") or 0)
            step = wait_continuous_vs_discrete(inst, E_truck=E_disc, steps=k)
            steps.append(step)
            floor_loss += step.rounding_loss_kwh
            E_disc = int(step.E_after_disc)
            n_wait += 1
        elif typ in ("START",):
            continue
        else:
            return ActionAuditResult(
                ok=False,
                steps=steps,
                cumulative_floor_loss_kwh=floor_loss,
                cumulative_cap_truncation_kwh=cap_trunc,
                n_drive=n_drive,
                n_charge=n_charge,
                n_wait=n_wait,
                n_zero_net_charge=n_zero,
                E_final_disc=E_disc,
                failure_reason=f"unknown_action:{typ}",
                n_actions_input=len(actions),
                n_actions_audited=len(steps),
            )

    expected_n = sum(1 for a in actions if str(a.get("type") or "") in ("DRIVE", "CHARGE", "WAIT"))
    if len(steps) != expected_n:
        return ActionAuditResult(
            ok=False,
            steps=steps,
            cumulative_floor_loss_kwh=floor_loss,
            cumulative_cap_truncation_kwh=cap_trunc,
            n_drive=n_drive,
            n_charge=n_charge,
            n_wait=n_wait,
            n_zero_net_charge=n_zero,
            E_final_disc=E_disc,
            failure_reason=f"action_count_mismatch:audited={len(steps)} expected={expected_n}",
            n_actions_input=len(actions),
            n_actions_audited=len(steps),
        )
    if expected_final_E_disc is not None and int(E_disc) != int(expected_final_E_disc):
        return ActionAuditResult(
            ok=False,
            steps=steps,
            cumulative_floor_loss_kwh=floor_loss,
            cumulative_cap_truncation_kwh=cap_trunc,
            n_drive=n_drive,
            n_charge=n_charge,
            n_wait=n_wait,
            n_zero_net_charge=n_zero,
            E_final_disc=E_disc,
            failure_reason=(
                f"final_E_mismatch:audit={E_disc} label={expected_final_E_disc}"
            ),
            n_actions_input=len(actions),
            n_actions_audited=len(steps),
        )
    return ActionAuditResult(
        ok=True,
        steps=steps,
        cumulative_floor_loss_kwh=floor_loss,
        cumulative_cap_truncation_kwh=cap_trunc,
        n_drive=n_drive,
        n_charge=n_charge,
        n_wait=n_wait,
        n_zero_net_charge=n_zero,
        E_final_disc=E_disc,
        failure_reason=None,
        n_actions_input=len(actions),
        n_actions_audited=len(steps),
    )


def audit_action_rounding(
    inst: RoutingInstance,
    actions: list[dict[str, Any]],
    *,
    E_truck_init: int | None = None,
) -> dict[str, Any]:
    """Lightweight CHARGE/WAIT/DRIVE-table audit without continuous DRIVE physics."""
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
                return {
                    "ok": False,
                    "failure_reason": f"missing_arc:{aid}",
                    "steps": steps,
                    "cumulative_rounding_loss_kwh": cumulative_rounding_loss(steps),
                    "n_actions_audited": len(steps),
                    "energy_quantum_kwh": q,
                    "E_final_disc": E,
                }
            ent = arc.drive_table.get((E, None))
            if ent is None or not ent.feasible:
                return {
                    "ok": False,
                    "failure_reason": f"drive_infeasible:{aid}@E={E}",
                    "steps": steps,
                    "cumulative_rounding_loss_kwh": cumulative_rounding_loss(steps),
                    "n_actions_audited": len(steps),
                    "energy_quantum_kwh": q,
                    "E_final_disc": E,
                }
            e_end = int(ent.E_end_truck)
            steps.append(
                QuantizationStep(
                    action="DRIVE",
                    E_before_disc=E,
                    E_after_cont=float(e_end),
                    E_after_disc=e_end,
                    physical_delta_kwh=float(e_end) - float(E),
                    rounding_loss_kwh=0.0,
                    note="drive_table_only_no_cont_sim",
                    arc_id=aid,
                )
            )
            E = e_end
    return {
        "ok": True,
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
    SUPERSEDED — incomplete node-path walk that can skip CHARGE and wrong arcs.

    Retained only so historical callers fail loudly toward the exact audit.
    """
    return {
        "total_rounding_loss_kwh": None,
        "n_drive_steps": None,
        "macro_segmentation_n_arcs": len(arcs),
        "superseded": True,
        "use_instead": "audit_solved_actions_exact",
        "warning": (
            "drive_path_floor_loss walks path_nodes without CHARGE updates and may "
            "select the wrong arc; do not use for publication trip totals."
        ),
    }


def optimistic_no_floor_breaks_conservative_feasibility() -> dict[str, Any]:
    return {
        "adopted": False,
        "reason": (
            "Ceil/no-floor after CHARGE would admit discrete states above the "
            "conservatively floored lattice; label dominance and replay certificates "
            "would no longer match the finite model used by MRLS/B&B."
        ),
        "safe_within_scope": "finer_fixed_grids_only",
        "novel_algorithm_claim": False,
    }


def summarize_quantization_policy() -> dict[str, Any]:
    return {
        "policy": "conservative_floor_after_DRIVE_CHARGE_WAIT",
        "DRIVE": "ending kWh floored onto quantum in DRIVE table build",
        "CHARGE_WAIT": "continuous energy floored after stationary drain",
        "adopted_correction": None,
        "authoritative_audit": "audit_solved_actions_exact",
        "superseded_audit": "drive_path_floor_loss",
        "rationale": (
            "Removing flooring would risk optimistic discrete feasibility. "
            "Publication-facing infrastructure claims require fine-grid stability "
            "and action-exact rounding audits."
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
