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


__all__ = [
    "TASK035B_R5_SLAB_BISECT_PROFILE",
    "TASK035B_R5_SLAB_BISECT_Z_VALUES_NM",
]
