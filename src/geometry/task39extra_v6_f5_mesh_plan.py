"""Frozen 5 nm F5 axis variants for the p6 direct comparison.

The historical run did not archive coordinate vectors.  These coordinates
were replayed from the exact mesh-builder/config Git blobs recorded with the
baseline, then matched against its actual cell and material counts.  The
two accepted y variants share those x/z arrays and are selected explicitly by
the input's mesh-plan identity.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping

BASELINE_SOURCE_SHA = "1828bc675f2862025e0eaed0beccf15982eb09e6"
MESH_BUILDER_GIT_BLOB_OID = "578bd2a7013ec9d93adac24c701d15a0a4df1205"
CONFIG_3D_GIT_BLOB_OID = "b2f50c18e298c88eaa45af43851296db25bd2b03"

F5_Y2_PLAN_ID = "task39extra.v6.f5.p6-direct.axes.same-xz-y2.v1"
F5_AXIS_PLAN_IDS = frozenset({F5_Y2_PLAN_ID})

F5_X_VALUES_NM = (
    0.0,
    3.3,
    6.6,
    9.899999999999999,
    13.2,
    16.5,
    19.9,
    23.3,
    26.7,
    30.1,
    33.5,
    36.8,
    40.1,
    43.4,
    46.7,
    50.0,
)
F5_Y2_VALUES_NM = (0.0, 12.5, 25.0)
F5_Z_VALUES_NM = (
    -10.0,
    -6.666666666666666,
    -3.333333333333333,
    0.0,
    4.0,
    8.0,
    12.0,
    16.0,
    20.0,
    24.0,
    28.0,
    32.0,
    36.0,
    40.0,
    44.0,
    48.0,
    52.0,
    56.0,
    60.0,
    64.0,
    68.0,
    72.0,
    76.0,
    80.0,
    84.0,
    88.0,
    92.0,
    96.0,
    100.0,
    104.0,
    108.0,
    112.0,
    116.0,
    120.0,
    123.33333333333333,
    126.66666666666667,
    130.0,
)


def _axis_sha256(values: tuple[float, ...]) -> str:
    import numpy as np

    return hashlib.sha256(np.asarray(values, dtype="<f8").tobytes()).hexdigest()


F5_AXIS_SHA256 = {
    "x": _axis_sha256(F5_X_VALUES_NM),
    "y2": _axis_sha256(F5_Y2_VALUES_NM),
    "z": _axis_sha256(F5_Z_VALUES_NM),
}


def f5_axis_plan_sha256(plan_id: str) -> str:
    if plan_id != F5_Y2_PLAN_ID:
        raise ValueError(f"unsupported F5 axis plan identity: {plan_id!r}")
    y_name, y_values = "y2", F5_Y2_VALUES_NM
    payload = {
        "schema": "task39extra.v6.f5.p6-direct-axis-plan.v1",
        "plan_id": plan_id,
        "baseline_source_sha": BASELINE_SOURCE_SHA,
        "mesh_builder_git_blob_oid": MESH_BUILDER_GIT_BLOB_OID,
        "config_3d_git_blob_oid": CONFIG_3D_GIT_BLOB_OID,
        "axis_hashes_le_f64": {
            "x": F5_AXIS_SHA256["x"],
            y_name: F5_AXIS_SHA256[y_name],
            "z": F5_AXIS_SHA256["z"],
        },
        "mesh_axis_cell_counts": [
            len(F5_X_VALUES_NM) - 1,
            len(y_values) - 1,
            len(F5_Z_VALUES_NM) - 1,
        ],
    }
    encoded = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("ascii")
    return hashlib.sha256(encoded).hexdigest()


def validate_frozen_f5_axes(
    discretization: Mapping[str, object],
) -> dict[str, tuple[float, ...]]:
    """Validate the exact baseline x/z arrays and the approved two-layer y grid."""

    plan_id = discretization.get("mesh_plan_id")
    if plan_id != F5_Y2_PLAN_ID:
        raise ValueError("input does not select the frozen F5 two-layer-y mesh plan")
    expected = {"x": F5_X_VALUES_NM, "y": F5_Y2_VALUES_NM, "z": F5_Z_VALUES_NM}
    if discretization.get("mesh_plan_sha256") != f5_axis_plan_sha256(str(plan_id)):
        raise ValueError("F5 frozen mesh-plan SHA differs")
    counts = tuple(discretization.get("mesh_axis_cell_counts") or ())
    expected_counts = tuple(len(expected[axis]) - 1 for axis in ("x", "y", "z"))
    if counts != expected_counts:
        raise ValueError("F5 axis cell counts differ from the selected frozen plan")

    resolved: dict[str, tuple[float, ...]] = {}
    for axis in ("x", "y", "z"):
        raw = discretization.get(f"mesh_axis_{axis}_values")
        if not isinstance(raw, (list, tuple)) or len(raw) != len(expected[axis]):
            raise ValueError(f"F5 mesh_axis_{axis}_values differ from the frozen plan")
        values = tuple(float(value) for value in raw)
        if not all(math.isfinite(value) for value in values):
            raise ValueError(f"F5 mesh_axis_{axis}_values contain non-finite values")
        if values != expected[axis]:
            raise ValueError(f"F5 mesh_axis_{axis}_values differ from the frozen plan")
        if any(right <= left for left, right in zip(values, values[1:])):
            raise ValueError(f"F5 mesh_axis_{axis}_values are not strictly increasing")
        resolved[axis] = values
    return resolved


__all__ = [
    "BASELINE_SOURCE_SHA",
    "CONFIG_3D_GIT_BLOB_OID",
    "F5_AXIS_PLAN_IDS",
    "F5_AXIS_SHA256",
    "F5_Y2_PLAN_ID",
    "F5_X_VALUES_NM",
    "F5_Y2_VALUES_NM",
    "F5_Z_VALUES_NM",
    "MESH_BUILDER_GIT_BLOB_OID",
    "f5_axis_plan_sha256",
    "validate_frozen_f5_axes",
]
