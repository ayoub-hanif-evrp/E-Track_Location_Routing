"""P0.2 — charge/wait quantization can erase discrete battery gain."""

from __future__ import annotations

from morocco_etruck.optimization.problem import RoutingInstance, StationData
from morocco_etruck.optimization.quantization_audit import (
    charge_continuous_vs_discrete,
    summarize_quantization_policy,
    wait_continuous_vs_discrete,
)
from morocco_etruck.optimization.resource_transitions import (
    Label,
    apply_charge,
    _floor_to_quantum,
)


def _toy_inst(*, q: int = 10) -> RoutingInstance:
    st = StationData(
        node="S",
        power_kw=350.0,
        eta=0.95,
        price_cents_per_grid_kwh=20,
        compatible=True,
    )
    return RoutingInstance(
        name="toy_q_charge",
        nodes=["S"],
        arcs=[],
        origin="S",
        destination="S",
        deadline_steps=1000,
        E_truck_cap=400,
        E_truck_min=50,
        E_truck_init=300,
        E_trailer_cap=None,
        E_trailer_min=None,
        E_trailer_init=None,
        stations={"S": st},
        active_stations={"S"},
        power_source="A",
        refrigeration_on=True,
        aux_w=2000.0,
        tru_mean_w=1000.0,
        wait_max_steps=5,
        time_step_min=5,
        energy_quantum_kwh=q,
    )


def test_charge_can_have_zero_discrete_gain_despite_positive_continuous():
    """
    Example at q=10:
      E0=300, charge +10, stationary drain 0.25 → continuous 309.75 → floor 300.
    """
    inst = _toy_inst(q=10)
    step = charge_continuous_vs_discrete(inst, E_truck=300, delta_e=10, node="S")
    assert step.E_after_cont > 300.0
    assert step.E_after_disc == 300
    assert step.rounding_loss_kwh > 0.0
    assert "zero_discrete_gain" in step.note

    # Live discrete transition agrees
    lab = Label(
        node="S",
        t=0,
        E_truck=300,
        E_trailer=None,
        cost=0,
        pred_id=None,
        action={"type": "START"},
        label_id=0,
        can_charge=True,
    )
    tr = apply_charge(inst, lab, 10, 1)
    assert tr.ok
    assert tr.label is not None
    assert tr.label.E_truck == 300


def test_floor_never_rounds_up():
    assert _floor_to_quantum(309.75, 10) == 300
    assert _floor_to_quantum(310.0, 10) == 310
    assert _floor_to_quantum(309.999, 10) == 300


def test_wait_also_floors_conservatively():
    inst = _toy_inst(q=10)
    step = wait_continuous_vs_discrete(inst, E_truck=305, steps=1)
    assert step.E_after_disc <= int(step.E_after_cont)
    assert step.E_after_disc % 10 == 0


def test_quantization_policy_does_not_claim_novel_algorithm():
    pol = summarize_quantization_policy()
    assert pol["novel_algorithm_claim"] is False
    assert pol["adopted_correction"] is None
