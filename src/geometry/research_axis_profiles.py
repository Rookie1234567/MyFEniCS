"""Frozen research-only tensor-axis profiles.

These constants are intentionally not a general arbitrary-coordinate API.
Every consumer must still verify the fixed geometry, nominal mesh size,
tensor counts, material planes, and persisted axis/mesh identity.
"""

from __future__ import annotations


TASK035B_R5_SLAB_BISECT_PROFILE = "h14_max-R5_slab_bisect"
TASK035B_R5_SLAB_BISECT_Z_VALUES_NM = (
    -10.0,
    0.0,
    6.666666666666667,
    13.333333333333334,
    26.666666666666668,
    40.0,
    53.333333333333336,
    66.66666666666667,
    80.0,
    93.33333333333334,
    106.66666666666667,
    120.0,
    130.0,
)

# Review V2 fixed-DoF response-guided discriminator.  Relative to the
# qualified h13 axis, only the top two internal slab planes move:
# 96 -> 93 1/3 nm and 108 -> 106 2/3 nm.  The lower/middle h13 resolution,
# material interfaces, exterior boundaries, tensor topology, and DoF count
# therefore remain unchanged.  The selected coordinates make the two highest
# in-slab intervals coincide with the h14 response authority without reviving
# the failed bottom-slab R5 bisection.
TASK035B_H13_TOP_PHASE_REDISTRIBUTION_PROFILE = (
    "h13_top2_phase_redistribution_v1"
)
TASK035B_H13_TOP_PHASE_REDISTRIBUTION_Z_VALUES_NM = (
    -10.0,
    0.0,
    12.0,
    24.0,
    36.0,
    48.0,
    60.0,
    72.0,
    84.0,
    93.33333333333334,
    106.66666666666667,
    120.0,
    130.0,
)

# Review V2 A2 bounded discriminator.  This is the exact reverse, on the
# unchanged h14 tensor topology, of the two-plane perturbation already measured
# as a controlled negative on h13.  Relative to the qualified h14 control only
# 93 1/3 -> 96 nm and 106 2/3 -> 108 nm move.  Interfaces, exterior
# boundaries, cell count, and therefore the p5-trace/p6-interior DoF count stay
# fixed.  It is one named research point, not an arbitrary-coordinate API.
TASK035B_H14_EXACT_REVERSE_TOP2_PROFILE = (
    "h14_exact_reverse_h13_top2_v1"
)
TASK035B_H14_EXACT_REVERSE_TOP2_Z_VALUES_NM = (
    -10.0,
    0.0,
    13.333333333333334,
    26.666666666666668,
    40.0,
    53.333333333333336,
    66.66666666666667,
    80.0,
    96.0,
    108.0,
    120.0,
    130.0,
)


__all__ = [
    "TASK035B_H13_TOP_PHASE_REDISTRIBUTION_PROFILE",
    "TASK035B_H13_TOP_PHASE_REDISTRIBUTION_Z_VALUES_NM",
    "TASK035B_H14_EXACT_REVERSE_TOP2_PROFILE",
    "TASK035B_H14_EXACT_REVERSE_TOP2_Z_VALUES_NM",
    "TASK035B_R5_SLAB_BISECT_PROFILE",
    "TASK035B_R5_SLAB_BISECT_Z_VALUES_NM",
]
