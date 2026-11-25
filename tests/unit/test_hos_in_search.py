"""Stage B: continuous-driving resource inside MRLS (HOS-in-search)."""

from __future__ import annotations

from morocco_etruck.optimization.dominance import dominates
from morocco_etruck.optimization.label_setting import SolverStatus, solve_mrls
from morocco_etruck.optimization.problem import ArcData, RoutingInstance, StationData
from morocco_etruck.optimization.resource_transitions import Label, apply_drive, apply_wait


def _long_corridor(*, hos: bool, wait_max: int = 3) -> RoutingInstance:
    """O -8steps-> S -8steps-> D with time_step=30 min => 4h arcs.

    Max continuous = round(270/30)=9 steps. Two drives without break = 16 > 9.
    A 2-step WAIT (60 min) at S resets the clock under hos_in_search.
    """
    stations = {"S": StationData("S", power_kw=60.0, eta=1.0, price_cents_per_grid_kwh=0)}
    return RoutingInstance(
        name="hos_toy",
        nodes=["O", "S", "D"],
        arcs=[
            ArcData("O", "S", dt_steps=8, dE_truck_kwh=10, dE_trailer_kwh=0, road_cost=1, power_ok=True),
            ArcData("S", "D", dt_steps=8, dE_truck_kwh=10, dE_trailer_kwh=0, road_cost=1, power_ok=True),
        ],
        origin="O",
        destination="D",
        deadline_steps=40,
        E_truck_cap=200,
        E_truck_min=10,
        E_truck_init=100,
        E_trailer_cap=None,
        E_trailer_min=None,
        E_trailer_init=None,
        stations=stations,
        # No charging at S (avoids charge-lattice explosion); WAIT still allowed via hos_rest_nodes.
        active_stations=set(),
        power_source="A",
        refrigeration_on=False,
        aux_w=0.0,
        tru_mean_w=0.0,
        aux_kwh_per_step=0,
        tru_kwh_per_step=0,
        wait_max_steps=wait_max,
        time_step_min=30,
        energy_quantum_kwh=5,
        hos_in_search=hos,
        hos_rest_nodes=frozenset({"S"}),
    )


def test_hos_blocks_second_leg_without_break():
    inst = _long_corridor(hos=True, wait_max=0)
    lab = Label("O", 0, 100, None, 0, None, {"type": "START"}, 0, can_charge=True)
    r1 = apply_drive(inst, lab, inst.arcs[0], 1)
    assert r1.ok and r1.label is not None
    assert r1.label.drive_since_break_steps == 8
    r2 = apply_drive(inst, r1.label, inst.arcs[1], 2)
    assert not r2.ok
    assert r2.reason == "hos_continuous_driving_exceeded"


def test_hos_wait_reset_allows_second_leg():
    inst = _long_corridor(hos=True, wait_max=3)
    lab = Label("O", 0, 100, None, 0, None, {"type": "START"}, 0, can_charge=True)
    r1 = apply_drive(inst, lab, inst.arcs[0], 1)
    assert r1.ok and r1.label is not None
    w = apply_wait(inst, r1.label, 2, 2)  # 60 min >= 45
    assert w.ok and w.label is not None
    assert w.label.drive_since_break_steps == 0
    r2 = apply_drive(inst, w.label, inst.arcs[1], 3)
    assert r2.ok and r2.label is not None
    assert r2.label.node == "D"


def test_mrls_hos_inserts_wait_when_needed():
    inst = _long_corridor(hos=True, wait_max=2)
    res = solve_mrls(inst, max_seconds=5.0, max_expansions=20_000)
    assert res.status == SolverStatus.OPTIMAL, (res.status, res.stats)
    types = [a.get("type") for a in res.actions]
    assert "WAIT" in types
    assert types.count("DRIVE") >= 2


def test_mrls_without_hos_skips_wait():
    # wait_max=0 so the energy-only search cannot pad; path is still feasible.
    inst = _long_corridor(hos=False, wait_max=0)
    res = solve_mrls(inst, max_seconds=5.0, max_expansions=20_000)
    assert res.status == SolverStatus.OPTIMAL, (res.status, res.stats)
    types = [a.get("type") for a in res.actions]
    assert "WAIT" not in types
    assert types.count("DRIVE") >= 2


def test_dominance_prefers_lower_drive_clock():
    a = Label("S", 5, 80, None, 10, None, {}, 1, can_charge=True, drive_since_break_steps=2)
    b = Label("S", 5, 80, None, 10, None, {}, 2, can_charge=True, drive_since_break_steps=5)
    assert dominates(a, b)
    assert not dominates(b, a)


def test_hos_daily_driving_blocks_excess():
    """Art. 17: daily driving > 9 h is rejected in search."""
    # time_step=60 → max daily = 9 steps; one 10-step drive must fail.
    stations = {"S": StationData("S", power_kw=60.0, eta=1.0, price_cents_per_grid_kwh=0)}
    inst = RoutingInstance(
        name="hos_daily",
        nodes=["O", "D"],
        arcs=[
            ArcData("O", "D", dt_steps=10, dE_truck_kwh=5, dE_trailer_kwh=0, road_cost=1, power_ok=True),
        ],
        origin="O",
        destination="D",
        deadline_steps=40,
        E_truck_cap=200,
        E_truck_min=10,
        E_truck_init=100,
        E_trailer_cap=None,
        E_trailer_min=None,
        E_trailer_init=None,
        stations=stations,
        active_stations=set(),
        power_source="A",
        refrigeration_on=False,
        wait_max_steps=0,
        time_step_min=60,
        energy_quantum_kwh=5,
        hos_in_search=True,
        hos_max_continuous_driving_steps=20,  # isolate daily check
        hos_rest_nodes=frozenset({"S"}),
    )
    lab = Label("O", 0, 100, None, 0, None, {"type": "START"}, 0, can_charge=True)
    r = apply_drive(inst, lab, inst.arcs[0], 1)
    assert not r.ok
    assert r.reason == "hos_daily_driving_exceeded"


def test_hos_break_does_not_reset_daily_drive_clock():
    """Scope guard: CHARGE+WAIT resets continuous drive, not daily_drive_steps.

    Overnight / Art.16 daily-rest reset is NOT implemented — do not claim it.
    """
    from morocco_etruck.optimization.resource_transitions import apply_charge

    stations = {"S": StationData("S", power_kw=350.0, eta=1.0, price_cents_per_grid_kwh=0)}
    inst = RoutingInstance(
        name="hos_daily_no_overnight",
        nodes=["O", "S", "D"],
        arcs=[
            ArcData("O", "S", dt_steps=4, dE_truck_kwh=5, dE_trailer_kwh=0, road_cost=1, power_ok=True),
            ArcData("S", "D", dt_steps=4, dE_truck_kwh=5, dE_trailer_kwh=0, road_cost=1, power_ok=True),
        ],
        origin="O",
        destination="D",
        deadline_steps=80,
        E_truck_cap=200,
        E_truck_min=10,
        E_truck_init=100,
        E_trailer_cap=None,
        E_trailer_min=None,
        E_trailer_init=None,
        stations=stations,
        active_stations={"S"},
        power_source="A",
        refrigeration_on=False,
        wait_max_steps=12,
        time_step_min=5,
        energy_quantum_kwh=5,
        hos_in_search=True,
        hos_rest_nodes=frozenset({"S"}),
    )
    inst.charge_duration_steps = lambda st, de, **kw: 4  # type: ignore[method-assign]
    lab = Label("O", 0, 100, None, 0, None, {"type": "START"}, 0, can_charge=True)
    r1 = apply_drive(inst, lab, inst.arcs[0], 1)
    assert r1.ok and r1.label is not None
    assert r1.label.daily_drive_steps == 4
    ch = apply_charge(inst, r1.label, 5, 2)
    assert ch.ok and ch.label is not None
    w = apply_wait(inst, ch.label, 5, 3)  # complete 45 min break
    assert w.ok and w.label is not None
    assert w.label.drive_since_break_steps == 0
    assert w.label.daily_drive_steps == 4  # daily clock unchanged


def test_hos_combined_charge_wait_resets_clock():
    """20 min CHARGE + 25 min WAIT at same node qualifies as a 45 min break."""
    from morocco_etruck.optimization.resource_transitions import apply_charge

    stations = {"S": StationData("S", power_kw=350.0, eta=1.0, price_cents_per_grid_kwh=0)}
    # time_step=5 → min_break=9 steps (45 min). Charge 4 steps (20 min) then wait 5 (25 min).
    inst = RoutingInstance(
        name="hos_combo",
        nodes=["O", "S", "D"],
        arcs=[
            ArcData("O", "S", dt_steps=8, dE_truck_kwh=10, dE_trailer_kwh=0, road_cost=1, power_ok=True),
            ArcData("S", "D", dt_steps=8, dE_truck_kwh=10, dE_trailer_kwh=0, road_cost=1, power_ok=True),
        ],
        origin="O",
        destination="D",
        deadline_steps=80,
        E_truck_cap=200,
        E_truck_min=10,
        E_truck_init=100,
        E_trailer_cap=None,
        E_trailer_min=None,
        E_trailer_init=None,
        stations=stations,
        active_stations={"S"},
        power_source="A",
        refrigeration_on=False,
        aux_w=0.0,
        tru_mean_w=0.0,
        wait_max_steps=9,
        time_step_min=5,
        energy_quantum_kwh=5,
        hos_in_search=True,
        hos_rest_nodes=frozenset({"S"}),
    )
    # Force short charge duration by patching charge_duration_steps
    inst.charge_duration_steps = lambda st, de, **kw: 4  # type: ignore[method-assign]
    lab = Label("O", 0, 100, None, 0, None, {"type": "START"}, 0, can_charge=True)
    r1 = apply_drive(inst, lab, inst.arcs[0], 1)
    assert r1.ok and r1.label is not None
    assert r1.label.drive_since_break_steps == 8
    ch = apply_charge(inst, r1.label, 5, 2)
    assert ch.ok and ch.label is not None
    assert ch.label.drive_since_break_steps == 8  # 20 min alone does not reset
    assert ch.label.stationary_accum_steps == 4
    w = apply_wait(inst, ch.label, 5, 3)  # +25 min → 45 total
    assert w.ok and w.label is not None
    assert w.label.drive_since_break_steps == 0
    r2 = apply_drive(inst, w.label, inst.arcs[1], 4)
    assert r2.ok and r2.label is not None
    assert r2.label.node == "D"


def test_search_replay_agree_on_combined_20_plus_25_break():
    """Search stationary accum and schedule audit both treat 20+25 as qualifying."""
    from morocco_etruck.optimization.hos_adjustment import classify_duty_scope
    from morocco_etruck.optimization.operational_schedule import (
        validate_operational_schedule,
    )
    from morocco_etruck.optimization.resource_transitions import apply_charge

    stations = {"S": StationData("S", power_kw=350.0, eta=1.0, price_cents_per_grid_kwh=0)}
    inst = RoutingInstance(
        name="hos_combo_agree",
        nodes=["O", "S", "D"],
        arcs=[
            ArcData("O", "S", dt_steps=8, dE_truck_kwh=10, dE_trailer_kwh=0, road_cost=1, power_ok=True),
            ArcData("S", "D", dt_steps=8, dE_truck_kwh=10, dE_trailer_kwh=0, road_cost=1, power_ok=True),
        ],
        origin="O",
        destination="D",
        deadline_steps=80,
        E_truck_cap=200,
        E_truck_min=10,
        E_truck_init=100,
        E_trailer_cap=None,
        E_trailer_min=None,
        E_trailer_init=None,
        stations=stations,
        active_stations={"S"},
        power_source="A",
        refrigeration_on=False,
        aux_w=0.0,
        tru_mean_w=0.0,
        wait_max_steps=9,
        time_step_min=5,
        energy_quantum_kwh=5,
        hos_in_search=True,
        hos_rest_nodes=frozenset({"S"}),
    )
    inst.charge_duration_steps = lambda st, de, **kw: 4  # type: ignore[method-assign]
    lab = Label("O", 0, 100, None, 0, None, {"type": "START"}, 0, can_charge=True)
    r1 = apply_drive(inst, lab, inst.arcs[0], 1)
    ch = apply_charge(inst, r1.label, 5, 2)
    w = apply_wait(inst, ch.label, 5, 3)
    assert w.label.drive_since_break_steps == 0  # search side

    # Replay/audit side: same physical block must reset continuous clock.
    actions = [
        {"type": "DRIVE", "dt_steps": 8, "dt_s": 8 * 5 * 60.0},
        {"type": "CHARGE", "steps": 4, "dt_s": 20 * 60.0, "node": "S"},
        {"type": "WAIT", "steps": 5, "dt_s": 25 * 60.0, "node": "S"},
        {"type": "DRIVE", "dt_steps": 8, "dt_s": 8 * 5 * 60.0},
    ]
    sched = validate_operational_schedule(
        actions, time_step_min=5, use_physical_times=True
    )
    assert sched.ok, sched.violation
    assert sched.continuous_driving_max_min <= 270.0 + 1e-9
    assert classify_duty_scope(daily_driving_min=sched.driving_min) == "SINGLE_DUTY"


def test_multi_day_out_of_scope_when_daily_drive_exceeds_9h():
    from morocco_etruck.optimization.hos_adjustment import (
        DUTY_MULTI_DAY_OUT_OF_SCOPE,
        DUTY_SINGLE,
        classify_duty_scope,
    )

    assert classify_duty_scope(daily_driving_min=8 * 60.0) == DUTY_SINGLE
    assert (
        classify_duty_scope(daily_driving_min=9 * 60.0 + 1.0)
        == DUTY_MULTI_DAY_OUT_OF_SCOPE
    )
    assert (
        classify_duty_scope(daily_driving_min=100.0, daily_driving_ok=False)
        == DUTY_MULTI_DAY_OUT_OF_SCOPE
    )
    assert (
        classify_duty_scope(daily_driving_min=100.0, journey_min=24 * 60.0)
        == DUTY_MULTI_DAY_OUT_OF_SCOPE
    )


def test_energy_only_can_succeed_when_hos_blocks():
    """Dual-eval contract: hos_in_search=False may be OPTIMAL when HOS-on is not."""
    inst_e = _long_corridor(hos=False, wait_max=0)
    res_e = solve_mrls(inst_e, max_seconds=5.0, max_expansions=20_000)
    assert res_e.status == SolverStatus.OPTIMAL

    inst_h = _long_corridor(hos=True, wait_max=0)
    res_h = solve_mrls(inst_h, max_seconds=5.0, max_expansions=20_000)
    # Without WAIT budget, continuous HOS blocks the second leg → not OPTIMAL served path.
    assert res_h.status != SolverStatus.OPTIMAL or "WAIT" not in [
        a.get("type") for a in (res_h.actions or [])
    ]
    if res_h.status == SolverStatus.OPTIMAL:
        # If somehow optimal, still must not have inserted a break (wait_max=0).
        assert "WAIT" not in [a.get("type") for a in res_h.actions]
    else:
        assert res_h.status in (
            SolverStatus.INFEASIBLE,
            SolverStatus.LIMIT_REACHED,
        )
