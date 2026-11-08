"""Conservative dominance unit tests."""

from __future__ import annotations

from morocco_etruck.optimization.dominance import DominanceStore, dominates
from morocco_etruck.optimization.resource_transitions import Label


def _L(node="n", t=0, E=50, cost=10, trailer=None, can_charge=True, lid=0):
    return Label(node, t, E, trailer, cost, None, {"type": "X"}, lid, can_charge)


def test_dominates_requires_same_node_time():
    assert not dominates(_L(t=0), _L(t=1))
    assert not dominates(_L(node="a"), _L(node="b"))


def test_dominates_cost_and_energy():
    a = _L(E=60, cost=5)
    b = _L(E=50, cost=10)
    assert dominates(a, b)
    assert not dominates(b, a)


def test_earlier_time_does_not_dominate():
    # Different times → no dominance even if otherwise better
    a = _L(t=0, E=60, cost=5)
    b = _L(t=1, E=50, cost=10)
    assert not dominates(a, b)


def test_store_rejects_dominated():
    store = DominanceStore(enabled=True)
    assert store.accept(_L(E=50, cost=10, lid=1))
    assert not store.accept(_L(E=40, cost=20, lid=2))
    assert store.dominated_count >= 1


def test_can_charge_resource():
    a = _L(E=50, cost=10, can_charge=True)
    b = _L(E=50, cost=10, can_charge=False)
    assert dominates(a, b)
    assert not dominates(b, a)
