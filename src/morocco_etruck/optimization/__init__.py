"""Custom multi-resource label-setting routing (Task 03A)."""

from morocco_etruck.optimization.label_setting import SolverStatus, solve_mrls
from morocco_etruck.optimization.problem import RoutingInstance

__all__ = ["RoutingInstance", "SolverStatus", "solve_mrls"]
