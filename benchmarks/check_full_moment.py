"""Independent V45 frozen inventory and mathematical gate consumers."""

from benchmarks.check_neighborhood_late_error import require_inventory as inventory
from benchmarks.check_neighborhood_late_error import require_model
from benchmarks.check_neighborhood_residual import audit_state, require_frozen_input

ROUTES = ("R0", "CL44", "LIN-H", "NN-L", "NN-H")


def require_inventory(rows):
    return inventory(rows, routes=ROUTES)


__all__ = ["audit_state", "require_frozen_input", "require_inventory", "require_model"]
