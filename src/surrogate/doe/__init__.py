"""Task005 discrete illumination DOE utilities.

The modules in this package are deliberately separate from the Maxwell
solver.  They consume immutable compact records and produce hash-bound DOE
metadata, finite-difference diagnostics, and Fisher summaries.
"""

from .design import (
    ANGLE_CANDIDATES,
    FORWARD_SOLVER_SHA,
    MODEL_ID,
    ROUTE_ID,
    build_m0_artifacts,
)

__all__ = [
    "ANGLE_CANDIDATES", "FORWARD_SOLVER_SHA", "MODEL_ID", "ROUTE_ID",
    "build_m0_artifacts",
]
