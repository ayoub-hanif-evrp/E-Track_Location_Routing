"""Conservative same-(node, time) dominance for discrete MRLS."""

from __future__ import annotations

from morocco_etruck.optimization.resource_transitions import Label


def dominates(a: Label, b: Label) -> bool:
    """
    Return True if label a dominates label b.

    Requires same node and same time. a is better-or-equal in cost and energies,
    with at least one strict improvement.
    """
    if a.node != b.node or a.t != b.t:
        return False
    cost_ok = a.cost <= b.cost
    truck_ok = a.E_truck >= b.E_truck
    # Remaining charge opportunity is a resource (True better than False)
    charge_ok = a.can_charge or (not b.can_charge)
    charge_strict = a.can_charge and (not b.can_charge)
    if a.E_trailer is None and b.E_trailer is None:
        trailer_ok = True
        trailer_strict = False
    elif a.E_trailer is not None and b.E_trailer is not None:
        trailer_ok = a.E_trailer >= b.E_trailer
        trailer_strict = a.E_trailer > b.E_trailer
    else:
        return False
    if not (cost_ok and truck_ok and trailer_ok and charge_ok):
        return False
    strict = (a.cost < b.cost) or (a.E_truck > b.E_truck) or trailer_strict or charge_strict
    return strict


class DominanceStore:
    """Pareto archive keyed by (node, t)."""

    def __init__(self, enabled: bool = True) -> None:
        self.enabled = enabled
        self._store: dict[tuple[str, int], list[Label]] = {}
        self.dominated_count = 0

    def accept(self, lab: Label) -> bool:
        """
        Insert lab if not dominated; remove labels that lab dominates.
        Returns True if lab should be expanded / kept.
        """
        key = (lab.node, lab.t)
        if not self.enabled:
            bucket = self._store.setdefault(key, [])
            # Exact duplicate state+cost skip to limit explosion without dominance
            for existing in bucket:
                if (
                    existing.E_truck == lab.E_truck
                    and existing.E_trailer == lab.E_trailer
                    and existing.cost == lab.cost
                    and existing.can_charge == lab.can_charge
                ):
                    self.dominated_count += 1
                    return False
            bucket.append(lab)
            return True

        bucket = self._store.setdefault(key, [])
        for existing in list(bucket):
            if dominates(existing, lab):
                self.dominated_count += 1
                return False
        # Remove newly dominated
        kept: list[Label] = []
        for existing in bucket:
            if dominates(lab, existing):
                self.dominated_count += 1
            else:
                kept.append(existing)
        kept.append(lab)
        self._store[key] = kept
        return True
